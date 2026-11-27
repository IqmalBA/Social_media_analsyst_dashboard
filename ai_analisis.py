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

from db_sqlite import buka, sekarang, siapkan
from konfigurasi import lokasi_database
from brand_watch import (ENTITAS, KOMPETITOR_SENDIRI, TOPIK, bukti_valid, normal, pihak_profil,
                          pola_kata)

MODEL = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
UKURAN_BATCH = 25
MAKS_PANGGILAN = int(os.environ.get("AI_MAKS_PANGGILAN", "15"))   # per run (kuota gratis)
JEDA_DETIK = float(os.environ.get("AI_JEDA_DETIK", "7"))           # batas per menit
MAKS_TEKS = 1500
RINGKASAN_KOMPETITOR = False      # True jika tab Competitors dimunculkan kembali di dashboard


class AIGagal(Exception):
    pass


# =========================
# PANGGILAN GEMINI
# =========================

def panggil_gemini(prompt, sistem, skema, kunci):
    """Mengembalikan (json, nama_model). Model berikutnya dicoba jika model tidak tersedia."""
    terakhir = None
    for model in MODEL:
        for coba in range(3):
            try:
                r = requests.post(
                    URL.format(model=model), timeout=180,
                    headers={"x-goog-api-key": kunci, "Content-Type": "application/json"},
                    json={"systemInstruction": {"parts": [{"text": sistem}]},
                          "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                          "generationConfig": {"temperature": 0,
                                               "responseMimeType": "application/json",
                                               "responseSchema": skema}})
            except requests.RequestException as e:
                terakhir = f"jaringan: {e}"
                time.sleep(10)
                continue
            if r.status_code == 429 or r.status_code >= 500:      # kuota per menit / server sibuk
                terakhir = f"{model}: HTTP {r.status_code}"
                time.sleep(30 * (coba + 1))
                continue
            if r.status_code in (400, 404) and "model" in r.text.lower():
                terakhir = f"{model}: tidak tersedia"
                break                                              # coba model berikutnya
            if r.status_code != 200:
                raise AIGagal(f"{model}: HTTP {r.status_code} {r.text[:300]}")
            try:
                teks = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(teks), model
            except (KeyError, IndexError, ValueError) as e:
                terakhir = f"{model}: jawaban tidak terbaca ({e})"
                time.sleep(5)
    raise AIGagal(terakhir or "tidak ada model yang bisa dipakai")


# =========================
# 1. ANALISIS PER POSTINGAN
# =========================

SISTEM_KONTEN = f"""Kamu analis media sosial sebuah brand di Indonesia. Untuk SETIAP postingan:
- "topik": pilih SATU kategori dari daftar yang paling sesuai dengan pokok isi postingan.
- "sebutan": daftar nama yang DISEBUT SECARA EKSPLISIT di teks. Pilihan nama:
{chr(10).join(f'  * "{n}" = {e["keterangan"]}' for n, e in ENTITAS.items())}
  Aturan:
  * Hanya isi jika nama itu tertulis di teks (nama, panggilan, atau @akunnya).
{chr(10).join(f'  * "{n}": {e["aturan"]}' for n, e in ENTITAS.items() if e.get("aturan"))}
  * Jangan menebak dari tema kampanye, foto, atau hashtag yang tidak memuat namanya.
  * "bukti": SALIN PERSIS potongan teks (3-80 karakter) yang memuat nama tersebut.
- Jika tidak ada yang disebut, "sebutan" = [].
Jawab untuk semua id yang diberikan."""

SKEMA_KONTEN = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "topik": {"type": "STRING", "enum": TOPIK},
            "sebutan": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {"nama": {"type": "STRING", "enum": list(ENTITAS)},
                               "bukti": {"type": "STRING"}},
                "required": ["nama", "bukti"]}},
        },
        "required": ["id", "topik", "sebutan"],
    },
}


def hash_teks(teks):
    return hashlib.sha256(normal(teks).encode("utf-8")).hexdigest()[:16]


def periksa_konten(jawaban, batch):
    """Pemeriksaan kode atas jawaban AI. Mengembalikan {content_id: (topik, entitas)}."""
    hasil = {}
    if not isinstance(jawaban, list):
        return hasil
    for item in jawaban:
        if not isinstance(item, dict) or str(item.get("id")) not in batch:
            continue                                  # id karangan -> dibuang
        cid, teks = batch[str(item["id"])]
        topik = item.get("topik") if item.get("topik") in TOPIK else None
        if topik is None:
            continue
        entitas, sudah = [], set()
        for s in item.get("sebutan") or []:
            if not isinstance(s, dict):
                continue
            nama, bukti = s.get("nama"), str(s.get("bukti") or "")
            if nama not in sudah and bukti_valid(nama, bukti, teks):
                entitas.append({"nama": nama, "bukti": bukti.strip()[:120]})
                sudah.add(nama)
        hasil[cid] = (topik, entitas)
    return hasil


def antrean_konten(conn):
    """Postingan ber-caption yang belum dianalisis atau caption-nya berubah (terbaru dulu)."""
    sudah = dict(conn.execute("SELECT content_id, teks_hash FROM ai_konten;").fetchall())
    antre = []
    for cid, teks in conn.execute(
            "SELECT content_id, caption FROM v_content "
            "WHERE caption IS NOT NULL AND trim(caption) != '' ORDER BY posted_at DESC;"):
        if sudah.get(cid) != hash_teks(teks):
            antre.append((cid, teks))
    return antre


def analisis_konten(conn, kunci, panggil=panggil_gemini):
    antre = antrean_konten(conn)
    print(f"Postingan menunggu analisis AI: {len(antre)}")
    disimpan, panggilan = 0, 0
    for i in range(0, len(antre), UKURAN_BATCH):
        if panggilan >= MAKS_PANGGILAN:
            print(f"Batas {MAKS_PANGGILAN} panggilan per run tercapai; sisanya di run berikutnya.")
            break
        potong = antre[i:i + UKURAN_BATCH]
        batch = {str(n + 1): (cid, teks) for n, (cid, teks) in enumerate(potong)}
        prompt = json.dumps([{"id": k, "teks": t[:MAKS_TEKS]} for k, (_, t) in batch.items()],
                            ensure_ascii=False)
        if panggilan:
            time.sleep(JEDA_DETIK)
        panggilan += 1
        try:
            jawaban, model = panggil(prompt, SISTEM_KONTEN, SKEMA_KONTEN, kunci)
        except AIGagal as e:                      # kuota habis / layanan bermasalah
            print(f"AI berhenti untuk run ini: {e}")
            break
        hasil = periksa_konten(jawaban, batch)
        waktu = sekarang()
        conn.execute("BEGIN;")
        conn.executemany(
            "INSERT OR REPLACE INTO ai_konten (content_id, teks_hash, topik, entitas, model, dibuat) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            [(cid, hash_teks(t), *hasil[cid][:1], json.dumps(hasil[cid][1], ensure_ascii=False),
              model, waktu) for cid, t in potong if cid in hasil])
        conn.execute("COMMIT;")
        disimpan += sum(1 for cid, _ in potong if cid in hasil)
    print(f"Hasil AI per postingan tersimpan: {disimpan}")
    return disimpan


# =========================
# 2. FAKTA (DIHITUNG SISTEM) + RINGKASAN AI
# =========================

def angka(x, desimal=0):
    """Format bahasa Inggris (dashboard berbahasa Inggris): 12,345 / 12.5."""
    if x is None:
        return "-"
    return f"{x:,.{desimal}f}"


def persen(x):
    return "-" if x is None else f"{angka(x * 100)}%"


def sebutan_per_konten(conn):
    """{content_id: set(nama)} dari kata kunci jelas + hasil AI yang lolos pemeriksaan."""
    teks = {cid: normal(" ".join(str(v or "") for v in (cap, lab, kol)))
            for cid, cap, lab, kol in conn.execute(
                "SELECT content_id, caption, labels_raw, kolaborator FROM v_content;")}
    hasil = {cid: set() for cid in teks}
    for nama, e in ENTITAS.items():
        pola = pola_kata(e["kata_kunci"])
        for cid, t in teks.items():
            if pola and re.search(pola, t):
                hasil[cid].add(nama)
    for cid, js in conn.execute("SELECT content_id, entitas FROM ai_konten;"):
        for s in json.loads(js or "[]"):
            if cid in hasil:
                hasil[cid].add(s["nama"])
    return hasil


def _data(conn):
    baris = conn.execute("""
        SELECT v.content_id, v.post_date, v.profile_name, v.platform, v.caption,
               v.engagements, v.total_interactions, v.komentar_negatif, v.komentar_positif,
               v.komentar_netral, v.content_url, a.topik
        FROM v_content v LEFT JOIN ai_konten a ON a.content_id = v.content_id;
    """).fetchall()
    kolom = ["cid", "tgl", "profil", "platform", "caption", "eng", "inter", "neg", "pos",
             "net", "url", "topik"]
    return [dict(zip(kolom, b)) for b in baris]


def _num(v):
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _ringkas_teks(t, n=110):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def susun_fakta(conn, hari=7):
    """Fakta untuk 'hari' terakhir (berakhir di tanggal posting terbaru) vs periode sebelumnya."""
    data = _data(conn)
    tanggal = [d["tgl"] for d in data if d["tgl"]]
    if not tanggal:
        return {}
    akhir = date.fromisoformat(max(tanggal))
    awal = akhir - timedelta(days=hari - 1)
    awal_lalu, akhir_lalu = awal - timedelta(days=hari), awal - timedelta(days=1)
    sebut = sebutan_per_konten(conn)
    for d in data:
        d["brand"] = pihak_profil(d["profil"])
        d["tgl"] = date.fromisoformat(d["tgl"]) if d["tgl"] else None

    def di(d, a, b):
        return d["tgl"] is not None and a <= d["tgl"] <= b

    periode = f"{awal:%d-%m-%Y} s.d. {akhir:%d-%m-%Y}"
    rujukan, fakta = {}, {}

    def tandai(d):
        kode = f"P{len(rujukan) + 1}"
        rujukan[kode] = d["cid"]
        return kode

    # ----- akun sendiri -----
    kini = [d for d in data if d["brand"] is None and di(d, awal, akhir)]
    lalu = [d for d in data if d["brand"] is None and di(d, awal_lalu, akhir_lalu)]
    if kini:
        eng = sum(_num(d["eng"]) for d in kini)
        eng_lalu = sum(_num(d["eng"]) for d in lalu)
        rata = eng / len(kini)
        f = {"period": periode,
             "posts": angka(len(kini)),
             "posts in previous period": angka(len(lalu)),
             "total engagements": angka(eng),
             "average engagements per post": angka(rata)}
        if eng_lalu:
            f["change in total engagements vs previous period"] = persen(eng / eng_lalu - 1)
        kom = sum(_num(d["neg"]) + _num(d["pos"]) + _num(d["net"]) for d in kini)
        if kom >= 20:
            f["negative comment share"] = persen(sum(_num(d["neg"]) for d in kini) / kom)
        topik = {}
        for d in kini:
            if d["topik"]:
                topik.setdefault(d["topik"], []).append(_num(d["eng"]))
        f["top topics"] = [
            {"topic": t, "posts": angka(len(v)), "average engagements": angka(sum(v) / len(v))}
            for t, v in sorted(topik.items(), key=lambda x: -len(x[1]))[:4]]
        f["names mentioned"] = []
        for nama in ENTITAS:
            v = [_num(d["eng"]) for d in kini if nama in sebut.get(d["cid"], ())]
            if v:
                f["names mentioned"].append({
                    "name": nama, "posts": angka(len(v)),
                    "average engagements": angka(sum(v) / len(v)),
                    "vs average of all posts": f"{angka(sum(v) / len(v) / rata, 1)}×"
                    if rata else "-"})
        f["top posts by engagements"] = [
            {"code": tandai(d), "account": d["profil"], "platform": d["platform"],
             "date": f"{d['tgl']:%d-%m-%Y}", "engagements": angka(_num(d["eng"])),
             "text": _ringkas_teks(d["caption"])}
            for d in sorted(kini, key=lambda d: -_num(d["eng"]))[:3]]
        fakta["sendiri"] = f

    # ----- kompetitor (hanya jika ada akun kompetitor di laporan) -----
    kini_k = [d for d in data if d["brand"] and di(d, awal, akhir)]
    if kini_k:
        platform = sorted({d["platform"] for d in kini_k})
        banding = kini_k + [d for d in data if d["brand"] is None and di(d, awal, akhir)
                            and d["platform"] in platform]
        per = {}
        for d in banding:
            per.setdefault(d["brand"] or KOMPETITOR_SENDIRI, []).append(d)
        total = sum(_num(d["inter"]) for d in banding)
        f = {"period": periode, "platforms compared": platform,
             "note": "compared using Total interactions (public data)",
             "by brand": [
                 {"brand": b, "posts": angka(len(v)),
                  "total interactions": angka(sum(_num(d["inter"]) for d in v)),
                  "interactions per post": angka(sum(_num(d["inter"]) for d in v) / len(v)),
                  "interaction share": persen(sum(_num(d["inter"]) for d in v) / total) if total else "-",
                  "top topics": sorted({d["topik"] for d in v if d["topik"]},
                                            key=lambda t: -sum(1 for d in v if d["topik"] == t))[:2]}
                 for b, v in sorted(per.items(), key=lambda x: -sum(_num(d["inter"]) for d in x[1]))],
             "top competitor posts by interactions": [
                 {"code": tandai(d), "brand": d["brand"], "account": d["profil"],
                  "platform": d["platform"], "date": f"{d['tgl']:%d-%m-%Y}",
                  "interactions": angka(_num(d["inter"])), "text": _ringkas_teks(d["caption"])}
                 for d in sorted(kini_k, key=lambda d: -_num(d["inter"]))[:3]]}
        fakta["kompetitor"] = f
    return {"fakta": fakta, "rujukan": rujukan, "awal": awal.isoformat(), "akhir": akhir.isoformat()}


SISTEM_RINGKASAN = """Kamu menulis ringkasan "what happens in social media" untuk tim brand.
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

SKEMA_RINGKASAN = {"type": "OBJECT",
                   "properties": {"poin": {"type": "ARRAY", "items": {"type": "STRING"}}},
                   "required": ["poin"]}

_ANGKA = re.compile(r"\d+(?:[.,]\d+)*")


def periksa_ringkasan(poin, fakta_teks, kode_sah):
    """Daftar masalah (kosong = lolos). Semua angka & kode harus berasal dari fakta."""
    masalah = []
    if not isinstance(poin, list) or not (1 <= len(poin) <= 6):
        return ["jumlah poin tidak sesuai"]
    angka_fakta = set(_ANGKA.findall(_ANGKA_KODE.sub(" ", fakta_teks)))
    asli = json.loads(fakta_teks) if fakta_teks.strip().startswith("{") else {}
    teks_asli = " ".join(_semua_teks(asli)) if asli else fakta_teks
    fakta_rapat = _rapat(teks_asli)
    hashtag_fakta = {h.lower() for h in re.findall(r"#\w+", teks_asli)}
    for p in poin:
        if not isinstance(p, str) or not p.strip():
            masalah.append("poin kosong")
            continue
        for kode in re.findall(r"\[(P\d+)\]", p):
            if kode not in kode_sah:
                masalah.append(f"kode {kode} tidak ada")
        bersih = re.sub(r"\[P\d+\]", " ", p)
        for a in _ANGKA.findall(bersih):
            if a not in angka_fakta:
                masalah.append(f"angka {a} tidak ada di fakta")
        # Keamanan: caption bisa berisi "perintah" untuk AI (prompt injection). Kalimat AI
        # tidak boleh memuat tautan, alamat web, HTML, atau format markdown link.
        if re.search(r"https?://|www\.|\]\(|<[a-zA-Z/!]|@[A-Za-z0-9.-]+\.[a-z]{2,}"
                     r"|\b[a-z0-9-]+\.(com|id|net|org|io|co|ly|me)\b", bersih, re.I):
            masalah.append("kalimat memuat tautan/alamat web/HTML")
        # Hashtag & kutipan wajib persis seperti aslinya (tidak diterjemahkan/diubah).
        for h in re.findall(r"#\w+", bersih):
            if h.lower() not in hashtag_fakta:
                masalah.append(f"hashtag {h} tidak persis seperti aslinya")
        for kutip in re.findall(r'["\u201c]([^"\u201d]{4,})["\u201d]', bersih):
            k = kutip.strip().rstrip("…").strip()
            if k and _rapat(k) not in fakta_rapat:
                masalah.append(f'kutipan "{k[:40]}" tidak persis seperti teks aslinya')
    return masalah


def _rapat(t):
    return re.sub(r"\s+", " ", str(t)).strip().lower()


_ANGKA_KODE = re.compile(r'"P\d+"')


def _semua_teks(x):
    """Semua nilai teks di fakta (tanpa escape JSON), untuk mencocokkan kutipan."""
    if isinstance(x, dict):
        for v in x.values():
            yield from _semua_teks(v)
    elif isinstance(x, list):
        for v in x:
            yield from _semua_teks(v)
    elif x is not None:
        yield str(x)


def buat_ringkasan(conn, kunci, panggil=panggil_gemini):
    hasil = susun_fakta(conn)
    if not hasil.get("fakta"):
        print("Belum ada data untuk ringkasan.")
        return 0
    jumlah = 0
    for cakupan, fakta in hasil["fakta"].items():
        if cakupan == "kompetitor" and not RINGKASAN_KOMPETITOR:
            continue                                  # tab Competitors sedang disembunyikan
        fakta_teks = json.dumps(fakta, ensure_ascii=False, indent=1)
        kode_sah = {k for k in hasil["rujukan"] if f'"{k}"' in fakta_teks}
        terakhir = conn.execute(
            "SELECT fakta FROM ai_ringkasan WHERE cakupan = ? ORDER BY id DESC LIMIT 1;",
            (cakupan,)).fetchone()
        if terakhir and terakhir[0] == fakta_teks:
            print(f"Ringkasan {cakupan}: fakta tidak berubah, tidak perlu dibuat ulang.")
            continue
        judul = ("the brand's own accounts" if cakupan == "sendiri"
                 else "comparison with competitors (public data)")
        prompt = f"Cakupan: {judul}.\nFAKTA:\n{fakta_teks}"
        poin, model, masalah = None, None, ["belum dicoba"]
        for coba in range(2):
            try:
                jawaban, model = panggil(prompt, SISTEM_RINGKASAN, SKEMA_RINGKASAN, kunci)
            except AIGagal as e:
                masalah = [str(e)]
                break
            poin = (jawaban or {}).get("poin") if isinstance(jawaban, dict) else None
            masalah = periksa_ringkasan(poin, fakta_teks, kode_sah)
            if not masalah:
                break
            prompt += ("\n\nJawaban sebelumnya DITOLAK karena: " + "; ".join(masalah[:5])
                       + ". Tulis ulang dan pakai hanya angka yang tertulis di FAKTA.")
            time.sleep(JEDA_DETIK)
        if masalah:
            print(f"Ringkasan {cakupan} TIDAK disimpan: {'; '.join(masalah[:5])}")
            continue
        rujukan = {k: hasil["rujukan"][k] for k in kode_sah}
        conn.execute("BEGIN;")
        conn.execute(
            "INSERT INTO ai_ringkasan (cakupan, periode_awal, periode_akhir, teks, rujukan, fakta, "
            "model, dibuat) VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (cakupan, hasil["awal"], hasil["akhir"], "\n".join(f"- {p.strip()}" for p in poin),
             json.dumps(rujukan), fakta_teks, model, sekarang()))
        conn.execute("DELETE FROM ai_ringkasan WHERE cakupan = ? AND id NOT IN "
                     "(SELECT id FROM ai_ringkasan WHERE cakupan = ? ORDER BY id DESC LIMIT 30);",
                     (cakupan, cakupan))
        conn.execute("COMMIT;")
        jumlah += 1
        print(f"Ringkasan {cakupan} tersimpan (lolos pemeriksaan angka).")
    return jumlah


def main():
    kunci = os.environ.get("GEMINI_API_KEY", "").strip()
    if not kunci:
        print("GEMINI_API_KEY belum diisi di GitHub Secrets. Analisis AI dilewati "
              "(dashboard tetap berjalan tanpa bagian AI).")
        return 0
    conn = buka(lokasi_database())
    try:
        siapkan(conn)
        analisis_konten(conn, kunci)
        buat_ringkasan(conn, kunci)
    except AIGagal as e:
        print(f"Analisis AI dihentikan: {e}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
