"""
Analisis AI (Google Gemini, versi gratis) untuk bagian "What happens" & Brand watch.

Dijalankan otomatis oleh GitHub Actions setelah data baru masuk (dan sekali sehari
untuk menuntaskan antrean). Jika GEMINI_API_KEY tidak ada atau AI gagal, skrip
berhenti dengan aman: data utama dan dashboard TIDAK terpengaruh.

Yang dikerjakan:
  1. Per postingan  : kategori topik + siapa yang disebut (aplikasi brand, ambassador).
  2. Ringkasan      : 3-5 kalimat "what happens" 7 hari terakhir (akun sendiri,
                      dan kompetitor jika datanya ada).

Pengaman agar hasil AI akurat (dicek oleh KODE, bukan oleh AI):
  - Kategori topik wajib salah satu dari daftar tetap (tidak bisa mengarang kategori).
  - Setiap sebutan nama wajib disertai kutipan yang BENAR-BENAR ada di caption dan
    memuat nama itu. Jika tidak, sebutan dibuang.
  - Angka di ringkasan dihitung oleh sistem, AI hanya menyusun kalimat. Setiap angka
    di kalimat AI wajib sama persis dengan angka di fakta; rujukan [P1] wajib ada.
    Jika satu saja tidak cocok -> diulang sekali, lalu dibuang bila masih salah.
  - Yang dikirim ke AI hanya caption postingan dan angka engagement/interaksi;
    reach & impressions (data internal) tidak dikirim.
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import date, timedelta

import requests

from db_sqlite import open_db, now, prepare
from settings import database_path
from brand_watch import (ENTITIES, OWN_COMPETITOR_LABEL, TOPICS, valid_evidence, normalize, profile_party,
                          word_pattern)

MODEL = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BATCH_SIZE = 25
MAX_CALLS = int(os.environ.get("AI_MAKS_PANGGILAN", "15"))   # per run (kuota gratis)
PAUSE_SECONDS = float(os.environ.get("AI_JEDA_DETIK", "7"))           # batas per menit
MAX_TEXT = 1500
COMPETITOR_SUMMARY = False      # True jika tab Competitors dimunculkan kembali di dashboard


class AIFailed(Exception):
    pass


# =========================
# PANGGILAN GEMINI
# =========================

def call_gemini(prompt, system, schema, key):
    """Mengembalikan (json, nama_model). Model berikutnya dicoba jika model tidak tersedia."""
    last = None
    for model in MODEL:
        for attempt in range(3):
            try:
                r = requests.post(
                    URL.format(model=model), timeout=180,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json={"systemInstruction": {"parts": [{"text": system}]},
                          "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                          "generationConfig": {"temperature": 0,
                                               "responseMimeType": "application/json",
                                               "responseSchema": schema}})
            except requests.RequestException as e:
                last = f"jaringan: {e}"
                time.sleep(10)
                continue
            if r.status_code == 429 or r.status_code >= 500:      # kuota per menit / server sibuk
                last = f"{model}: HTTP {r.status_code}"
                time.sleep(30 * (attempt + 1))
                continue
            if r.status_code in (400, 404) and "model" in r.text.lower():
                last = f"{model}: tidak tersedia"
                break                                              # coba model berikutnya
            if r.status_code != 200:
                raise AIFailed(f"{model}: HTTP {r.status_code} {r.text[:300]}")
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text), model
            except (KeyError, IndexError, ValueError) as e:
                last = f"{model}: jawaban tidak terbaca ({e})"
                time.sleep(5)
    raise AIFailed(last or "tidak ada model yang bisa dipakai")


# =========================
# 1. ANALISIS PER POSTINGAN
# =========================

CONTENT_SYSTEM_PROMPT = f"""Kamu analis media sosial sebuah brand di Indonesia. Untuk SETIAP postingan:
- "topik": pilih SATU kategori dari daftar yang paling sesuai dengan pokok isi postingan.
- "sebutan": daftar nama yang DISEBUT SECARA EKSPLISIT di teks. Pilihan nama:
{chr(10).join(f'  * "{n}" = {e["keterangan"]}' for n, e in ENTITIES.items())}
  Aturan:
  * Hanya isi jika nama itu tertulis di teks (nama, panggilan, atau @akunnya).
{chr(10).join(f'  * "{n}": {e["aturan"]}' for n, e in ENTITIES.items() if e.get("aturan"))}
  * Jangan menebak dari tema kampanye, foto, atau hashtag yang tidak memuat namanya.
  * "bukti": SALIN PERSIS potongan teks (3-80 karakter) yang memuat nama tersebut.
- Jika tidak ada yang disebut, "sebutan" = [].
Jawab untuk semua id yang diberikan."""

CONTENT_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "topik": {"type": "STRING", "enum": TOPICS},
            "sebutan": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {"nama": {"type": "STRING", "enum": list(ENTITIES)},
                               "bukti": {"type": "STRING"}},
                "required": ["nama", "bukti"]}},
        },
        "required": ["id", "topik", "sebutan"],
    },
}


def hash_text(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def check_content(answer, batch):
    """Pemeriksaan kode atas jawaban AI. Mengembalikan {content_id: (topik, entitas)}."""
    result = {}
    if not isinstance(answer, list):
        return result
    for item in answer:
        if not isinstance(item, dict) or str(item.get("id")) not in batch:
            continue                                  # id karangan -> dibuang
        cid, text = batch[str(item["id"])]
        topic = item.get("topik") if item.get("topik") in TOPICS else None
        if topic is None:
            continue
        entity, done = [], set()
        for s in item.get("sebutan") or []:
            if not isinstance(s, dict):
                continue
            name, evidence = s.get("nama"), str(s.get("bukti") or "")
            if name not in done and valid_evidence(name, evidence, text):
                entity.append({"nama": name, "bukti": evidence.strip()[:120]})
                done.add(name)
        result[cid] = (topic, entity)
    return result


def content_queue(conn):
    """Postingan ber-caption yang belum dianalisis atau caption-nya berubah (terbaru dulu)."""
    done = dict(conn.execute("SELECT content_id, teks_hash FROM ai_konten;").fetchall())
    queue = []
    for cid, text in conn.execute(
            "SELECT content_id, caption FROM v_content "
            "WHERE caption IS NOT NULL AND trim(caption) != '' ORDER BY posted_at DESC;"):
        if done.get(cid) != hash_text(text):
            queue.append((cid, text))
    return queue


def analyze_content(conn, key, call=call_gemini):
    queue = content_queue(conn)
    print(f"Postingan menunggu analisis AI: {len(queue)}")
    saved, calls = 0, 0
    for i in range(0, len(queue), BATCH_SIZE):
        if calls >= MAX_CALLS:
            print(f"Batas {MAX_CALLS} panggilan per run tercapai; sisanya di run berikutnya.")
            break
        truncate = queue[i:i + BATCH_SIZE]
        batch = {str(n + 1): (cid, text) for n, (cid, text) in enumerate(truncate)}
        prompt = json.dumps([{"id": k, "teks": t[:MAX_TEXT]} for k, (_, t) in batch.items()],
                            ensure_ascii=False)
        if calls:
            time.sleep(PAUSE_SECONDS)
        calls += 1
        try:
            answer, model = call(prompt, CONTENT_SYSTEM_PROMPT, CONTENT_SCHEMA, key)
        except AIFailed as e:                      # kuota habis / layanan bermasalah
            print(f"AI berhenti untuk run ini: {e}")
            break
        result = check_content(answer, batch)
        timestamp = now()
        conn.execute("BEGIN;")
        conn.executemany(
            "INSERT OR REPLACE INTO ai_konten (content_id, teks_hash, topik, entitas, model, dibuat) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            [(cid, hash_text(t), *result[cid][:1], json.dumps(result[cid][1], ensure_ascii=False),
              model, timestamp) for cid, t in truncate if cid in result])
        conn.execute("COMMIT;")
        saved += sum(1 for cid, _ in truncate if cid in result)
    print(f"Hasil AI per postingan tersimpan: {saved}")
    return saved


# =========================
# 2. FAKTA (DIHITUNG SISTEM) + RINGKASAN AI
# =========================

def number(x, decimals=0):
    """Format bahasa Inggris (dashboard berbahasa Inggris): 12,345 / 12.5."""
    if x is None:
        return "-"
    return f"{x:,.{decimals}f}"


def percent(x):
    return "-" if x is None else f"{number(x * 100)}%"


def mentions_per_content(conn):
    """{content_id: set(nama)} dari kata kunci jelas + hasil AI yang lolos pemeriksaan."""
    text = {cid: normalize(" ".join(str(v or "") for v in (cap, lab, col)))
            for cid, cap, lab, col in conn.execute(
                "SELECT content_id, caption, labels_raw, kolaborator FROM v_content;")}
    result = {cid: set() for cid in text}
    for name, e in ENTITIES.items():
        pattern = word_pattern(e["kata_kunci"])
        for cid, t in text.items():
            if pattern and re.search(pattern, t):
                result[cid].add(name)
    for cid, js in conn.execute("SELECT content_id, entitas FROM ai_konten;"):
        for s in json.loads(js or "[]"):
            if cid in result:
                result[cid].add(s["nama"])
    return result


def _data(conn):
    row = conn.execute("""
        SELECT v.content_id, v.post_date, v.profile_name, v.platform, v.caption,
               v.engagements, v.total_interactions, v.komentar_negatif, v.komentar_positif,
               v.komentar_netral, v.content_url, a.topik
        FROM v_content v LEFT JOIN ai_konten a ON a.content_id = v.content_id;
    """).fetchall()
    column = ["cid", "tgl", "profil", "platform", "caption", "eng", "inter", "neg", "pos",
             "net", "url", "topik"]
    return [dict(zip(column, b)) for b in row]


def _num(v):
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _summarize_text(t, n=110):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def build_facts(conn, days=7):
    """Fakta untuk 'hari' terakhir (berakhir di tanggal posting terbaru) vs periode sebelumnya."""
    data = _data(conn)
    date_value = [d["tgl"] for d in data if d["tgl"]]
    if not date_value:
        return {}
    end = date.fromisoformat(max(date_value))
    start = end - timedelta(days=days - 1)
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
    mention = mentions_per_content(conn)
    for d in data:
        d["brand"] = profile_party(d["profil"])
        d["tgl"] = date.fromisoformat(d["tgl"]) if d["tgl"] else None

    def within(d, a, b):
        return d["tgl"] is not None and a <= d["tgl"] <= b

    period = f"{start:%d-%m-%Y} s.d. {end:%d-%m-%Y}"
    refs, facts = {}, {}

    def mark(d):
        code = f"P{len(refs) + 1}"
        refs[code] = d["cid"]
        return code

    # ----- akun sendiri -----
    current = [d for d in data if d["brand"] is None and within(d, start, end)]
    previous = [d for d in data if d["brand"] is None and within(d, prev_start, prev_end)]
    if current:
        eng = sum(_num(d["eng"]) for d in current)
        prev_eng = sum(_num(d["eng"]) for d in previous)
        average = eng / len(current)
        f = {"period": period,
             "posts": number(len(current)),
             "posts in previous period": number(len(previous)),
             "total engagements": number(eng),
             "average engagements per post": number(average)}
        if prev_eng:
            f["change in total engagements vs previous period"] = percent(eng / prev_eng - 1)
        comm = sum(_num(d["neg"]) + _num(d["pos"]) + _num(d["net"]) for d in current)
        if comm >= 20:
            f["negative comment share"] = percent(sum(_num(d["neg"]) for d in current) / comm)
        topic = {}
        for d in current:
            if d["topik"]:
                topic.setdefault(d["topik"], []).append(_num(d["eng"]))
        f["top topics"] = [
            {"topic": t, "posts": number(len(v)), "average engagements": number(sum(v) / len(v))}
            for t, v in sorted(topic.items(), key=lambda x: -len(x[1]))[:4]]
        f["names mentioned"] = []
        for name in ENTITIES:
            v = [_num(d["eng"]) for d in current if name in mention.get(d["cid"], ())]
            if v:
                f["names mentioned"].append({
                    "name": name, "posts": number(len(v)),
                    "average engagements": number(sum(v) / len(v)),
                    "vs average of all posts": f"{number(sum(v) / len(v) / average, 1)}×"
                    if average else "-"})
        f["top posts by engagements"] = [
            {"code": mark(d), "account": d["profil"], "platform": d["platform"],
             "date": f"{d['tgl']:%d-%m-%Y}", "engagements": number(_num(d["eng"])),
             "text": _summarize_text(d["caption"])}
            for d in sorted(current, key=lambda d: -_num(d["eng"]))[:3]]
        facts["sendiri"] = f

    # ----- kompetitor (hanya jika ada akun kompetitor di laporan) -----
    curr_k = [d for d in data if d["brand"] and within(d, start, end)]
    if curr_k:
        platform = sorted({d["platform"] for d in curr_k})
        comparison = curr_k + [d for d in data if d["brand"] is None and within(d, start, end)
                            and d["platform"] in platform]
        per = {}
        for d in comparison:
            per.setdefault(d["brand"] or OWN_COMPETITOR_LABEL, []).append(d)
        total = sum(_num(d["inter"]) for d in comparison)
        f = {"period": period, "platforms compared": platform,
             "note": "compared using Total interactions (public data)",
             "by brand": [
                 {"brand": b, "posts": number(len(v)),
                  "total interactions": number(sum(_num(d["inter"]) for d in v)),
                  "interactions per post": number(sum(_num(d["inter"]) for d in v) / len(v)),
                  "interaction share": percent(sum(_num(d["inter"]) for d in v) / total) if total else "-",
                  "top topics": sorted({d["topik"] for d in v if d["topik"]},
                                            key=lambda t: -sum(1 for d in v if d["topik"] == t))[:2]}
                 for b, v in sorted(per.items(), key=lambda x: -sum(_num(d["inter"]) for d in x[1]))],
             "top competitor posts by interactions": [
                 {"code": mark(d), "brand": d["brand"], "account": d["profil"],
                  "platform": d["platform"], "date": f"{d['tgl']:%d-%m-%Y}",
                  "interactions": number(_num(d["inter"])), "text": _summarize_text(d["caption"])}
                 for d in sorted(curr_k, key=lambda d: -_num(d["inter"]))[:3]]}
        facts["kompetitor"] = f
    return {"fakta": facts, "rujukan": refs, "awal": start.isoformat(), "akhir": end.isoformat()}


SUMMARY_SYSTEM_PROMPT = """Kamu menulis ringkasan "what happens in social media" untuk tim brand.
Tulis 3-5 poin, masing-masing SATU kalimat pendek dalam BAHASA INGGRIS yang netral.
Nama brand, akun, kategori topik, dan kutipan isi postingan tetap ditulis seperti di FAKTA.
ATURAN WAJIB:
- Gunakan HANYA informasi dan angka yang tertulis di FAKTA. Salin angka persis seperti tertulis
  (termasuk titik, koma, %, dan ×).
- DILARANG menghitung angka baru (tidak menjumlah, mengurangi, membagi, atau membuat persen baru).
- DILARANG menebak penyebab, memberi saran, atau menilai baik/buruk di luar angka.
- Saat membahas postingan tertentu, sebut "code"-nya dalam kurung siku, mis. [P1].
- Jangan menulis tanggal dalam format lain selain yang tertulis di FAKTA.
- JANGAN MENERJEMAHKAN hashtag, tagline, nama campaign, nama akun, atau isi postingan.
  Tulis hashtag persis seperti di FAKTA (mis. #KopiRimbun). Jika mengutip isi postingan
  atau tagline, salin PERSIS dalam bahasa aslinya dan beri tanda kutip ganda "...".
  Jangan memparafrasekan isi postingan ke bahasa Inggris."""

SUMMARY_SCHEMA = {"type": "OBJECT",
                   "properties": {"poin": {"type": "ARRAY", "items": {"type": "STRING"}}},
                   "required": ["poin"]}

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def check_summary(points, facts_text, valid_codes):
    """Daftar masalah (kosong = lolos). Semua angka & kode harus berasal dari fakta."""
    problems = []
    if not isinstance(points, list) or not (1 <= len(points) <= 6):
        return ["jumlah poin tidak sesuai"]
    fact_numbers = set(_NUMBER.findall(_CODE_NUMBER.sub(" ", facts_text)))
    original = json.loads(facts_text) if facts_text.strip().startswith("{") else {}
    original_text = " ".join(_all_text(original)) if original else facts_text
    compact_facts = _compact(original_text)
    fact_hashtags = {h.lower() for h in re.findall(r"#\w+", original_text)}
    for p in points:
        if not isinstance(p, str) or not p.strip():
            problems.append("poin kosong")
            continue
        for code in re.findall(r"\[(P\d+)\]", p):
            if code not in valid_codes:
                problems.append(f"kode {code} tidak ada")
        clean = re.sub(r"\[P\d+\]", " ", p)
        for a in _NUMBER.findall(clean):
            if a not in fact_numbers:
                problems.append(f"angka {a} tidak ada di fakta")
        # Keamanan: caption bisa berisi "perintah" untuk AI (prompt injection). Kalimat AI
        # tidak boleh memuat tautan, alamat web, HTML, atau format markdown link.
        if re.search(r"https?://|www\.|\]\(|<[a-zA-Z/!]|@[A-Za-z0-9.-]+\.[a-z]{2,}"
                     r"|\b[a-z0-9-]+\.(com|id|net|org|io|co|ly|me)\b", clean, re.I):
            problems.append("kalimat memuat tautan/alamat web/HTML")
        # Hashtag & kutipan wajib persis seperti aslinya (tidak diterjemahkan/diubah).
        for h in re.findall(r"#\w+", clean):
            if h.lower() not in fact_hashtags:
                problems.append(f"hashtag {h} tidak persis seperti aslinya")
        for quote in re.findall(r'["\u201c]([^"\u201d]{4,})["\u201d]', clean):
            k = quote.strip().rstrip("…").strip()
            if k and _compact(k) not in compact_facts:
                problems.append(f'kutipan "{k[:40]}" tidak persis seperti teks aslinya')
    return problems


def _compact(t):
    return re.sub(r"\s+", " ", str(t)).strip().lower()


_CODE_NUMBER = re.compile(r'"P\d+"')


def _all_text(x):
    """Semua nilai teks di fakta (tanpa escape JSON), untuk mencocokkan kutipan."""
    if isinstance(x, dict):
        for v in x.values():
            yield from _all_text(v)
    elif isinstance(x, list):
        for v in x:
            yield from _all_text(v)
    elif x is not None:
        yield str(x)


def build_summary(conn, key, call=call_gemini):
    result = build_facts(conn)
    if not result.get("fakta"):
        print("Belum ada data untuk ringkasan.")
        return 0
    count = 0
    for scope, facts in result["fakta"].items():
        if scope == "kompetitor" and not COMPETITOR_SUMMARY:
            continue                                  # tab Competitors sedang disembunyikan
        facts_text = json.dumps(facts, ensure_ascii=False, indent=1)
        valid_codes = {k for k in result["rujukan"] if f'"{k}"' in facts_text}
        last = conn.execute(
            "SELECT fakta FROM ai_ringkasan WHERE cakupan = ? ORDER BY id DESC LIMIT 1;",
            (scope,)).fetchone()
        if last and last[0] == facts_text:
            print(f"Ringkasan {scope}: fakta tidak berubah, tidak perlu dibuat ulang.")
            continue
        title = ("the brand's own accounts" if scope == "sendiri"
                 else "comparison with competitors (public data)")
        prompt = f"Cakupan: {title}.\nFAKTA:\n{facts_text}"
        points, model, problems = None, None, ["belum dicoba"]
        for attempt in range(2):
            try:
                answer, model = call(prompt, SUMMARY_SYSTEM_PROMPT, SUMMARY_SCHEMA, key)
            except AIFailed as e:
                problems = [str(e)]
                break
            points = (answer or {}).get("poin") if isinstance(answer, dict) else None
            problems = check_summary(points, facts_text, valid_codes)
            if not problems:
                break
            prompt += ("\n\nJawaban sebelumnya DITOLAK karena: " + "; ".join(problems[:5])
                       + ". Tulis ulang dan pakai hanya angka yang tertulis di FAKTA.")
            time.sleep(PAUSE_SECONDS)
        if problems:
            print(f"Ringkasan {scope} TIDAK disimpan: {'; '.join(problems[:5])}")
            continue
        refs = {k: result["rujukan"][k] for k in valid_codes}
        conn.execute("BEGIN;")
        conn.execute(
            "INSERT INTO ai_ringkasan (cakupan, periode_awal, periode_akhir, teks, rujukan, fakta, "
            "model, dibuat) VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (scope, result["awal"], result["akhir"], "\n".join(f"- {p.strip()}" for p in points),
             json.dumps(refs), facts_text, model, now()))
        conn.execute("DELETE FROM ai_ringkasan WHERE cakupan = ? AND id NOT IN "
                     "(SELECT id FROM ai_ringkasan WHERE cakupan = ? ORDER BY id DESC LIMIT 30);",
                     (scope, scope))
        conn.execute("COMMIT;")
        count += 1
        print(f"Ringkasan {scope} tersimpan (lolos pemeriksaan angka).")
    return count


def main():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY belum diisi di GitHub Secrets. Analisis AI dilewati "
              "(dashboard tetap berjalan tanpa bagian AI).")
        return 0
    conn = open_db(database_path())
    try:
        prepare(conn)
        analyze_content(conn, key)
        build_summary(conn, key)
    except AIFailed as e:
        print(f"Analisis AI dihentikan: {e}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
