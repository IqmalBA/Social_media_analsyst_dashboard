"""
Uji pengaman AI tanpa internet: "AI palsu" sengaja memberi jawaban benar DAN bohong.
Lulus berarti jawaban bohong ditolak kode dan tidak pernah sampai ke dashboard.

Jalankan: python test_ai.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import test_etl as T                                         # noqa: E402

result = []


def check(name, condition, detail=""):
    result.append(condition)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + ("" if condition else f" -> {detail}"))


CAPTION = ["Latte art bareng Tara Senandika di Rimbun Roastery #KopiRimbun",
           "Taraa! Menu baru udah datang di semua gerai",
           "Es Kopi Pandan bareng Wening Asmara: Hujan, Tetap Hangat",
           "Bagas lagi ngelawak soal antre, pesan lewat Rimbun App ya",
           "Promo es kopi akhir pekan",
           "Kak Tara nyeduh biji baru di Roastery"]


def fake_ai(A):
    def call(prompt, system, schema, key):
        if schema is A.CONTENT_SCHEMA:
            out = []
            for it in json.loads(prompt):
                t, s = it["teks"], []
                if "Tara " in t:
                    s.append({"nama": "Tara Senandika", "bukti": "Tara"})
                if "Taraa" in t:             # BOHONG: "Taraa!" = seruan "ta-da!", bukan nama orang
                    s.append({"nama": "Tara Senandika", "bukti": "Taraa"})
                    s.append({"nama": "Wening Asmara", "bukti": "Taraa! Menu baru"})  # dan bukan Wening
                if "Wening" in t:
                    s.append({"nama": "Wening Asmara", "bukti": "Wening Asmara"})
                if "Es Kopi Pandan" in t:    # BOHONG: kutipan tidak memuat nama Bagas
                    s.append({"nama": "Bagas Jenggala", "bukti": "Es Kopi Pandan"})
                if "Promo es kopi" in t:     # BOHONG: kutipan tidak ada di caption
                    s.append({"nama": "Wening Asmara", "bukti": "Wening datang"})
                out.append({"id": it["id"], "topik": "Promos & deals" if "romo" in t
                            else "Lifestyle & moments", "sebutan": s})
            out.append({"id": "999", "topik": "Lainnya", "sebutan": []})       # BOHONG: id karangan
            out.append({"id": "1", "topik": "Topik Karangan", "sebutan": []})  # BOHONG: kategori
            return out, "palsu"
        call.n = getattr(call, "n", 0) + 1
        facts = json.loads(prompt.split("FAKTA:\n")[1].split("\n\nJawaban")[0])
        if call.n == 1:                   # BOHONG: angka karangan -> harus diulang
            return {"poin": ["Total engagements naik 999% [P1]."]}, "palsu"
        if "posts" in facts:
            return {"poin": [f"There were {facts['posts']} posts with total "
                             f"engagements of {facts['total engagements']} [P1]."]}, "palsu"
        b = facts["by brand"][0]            # BOHONG: rujukan [P99] tidak ada
        return {"poin": [f"{b['brand']} memimpin dengan {b['total interactions']} "
                         f"interactions [P99]."]}, "palsu"
    return call


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        db = str(Path(folder) / "uji.db")
        env = {**os.environ, "EMPLIFI_DB": db, "PYTHONIOENCODING": "utf-8"}
        rows = []
        for i in range(18):
            r = T.row(f"C{i}", 1000 + i, "Tower A - Camp A - Sub A",
                        link=f"https://www.instagram.com/p/X{i}/")
            r.update({"Date": datetime(2026, 11, 1) + timedelta(hours=i * 12),
                      "Content": CAPTION[i % 6], "Profile name": "Kopi Rimbun", "Engagements": 100 + i,
                      "Collaborators": None})
            rows.append(r)
        for i, (prof, text) in enumerate([("Kopi Senja", "Promo Kopi Senja diskon gede"),
                                          ("Teh Lembah", "Teh Lembah konser gratis")]):
            r = T.row(f"K{i}", 1, None, link=f"https://www.instagram.com/p/K{i}/")
            r.update({"Date": datetime(2026, 11, 6), "Content": text, "Profile name": prof,
                      "Total interactions": 500 * (i + 1), "Collaborators": None})
            rows.append(r)
        k, log = T.etl(T.make_excel(folder, "feed", rows),
                       datetime(2026, 11, 14, 9, tzinfo=timezone.utc), env)
        check("data uji masuk", k == 0, log[-300:])

        os.environ["EMPLIFI_DB"] = db
        import ai_analysis as A
        from db_sqlite import open_db, prepare
        A.PAUSE_SECONDS = 0
        conn = open_db(db)
        prepare(conn)
        fake = fake_ai(A)

        print("\nA1. Analisis per postingan")
        A.analyze_content(conn, "kunci-uji", fake)
        ent = {cid: {e["nama"] for e in json.loads(js)} for cid, js in
               conn.execute("SELECT content_id, entitas FROM ai_konten")}
        check("Tara terdeteksi dengan kutipan sah", "Tara Senandika" in ent["C0"]
            and "Tara Senandika" in ent["C5"], ent)
        check("'Taraa!' (seruan) TIDAK dianggap nama orang", ent["C1"] == set(), ent["C1"])
        check("Bagas dengan kutipan 'Es Kopi Pandan' ditolak", ent["C2"] == {"Wening Asmara"}, ent["C2"])
        check("kutipan yang tidak ada di caption ditolak", ent["C4"] == set(), ent["C4"])
        check("id karangan tidak disimpan",
            conn.execute("SELECT COUNT(*) FROM ai_konten WHERE content_id='999'").fetchone()[0] == 0)
        check("kategori di luar daftar ditolak",
            conn.execute("SELECT COUNT(*) FROM ai_konten WHERE topik NOT IN (%s)"
                         % ",".join("?" * len(A.TOPICS)), A.TOPICS).fetchone()[0] == 0)
        check("tidak dianalisis ulang jika caption sama", A.content_queue(conn) == [])

        print("\nA2. Ringkasan naratif")
        A.build_summary(conn, "kunci-uji", fake)
        rk = dict(conn.execute("SELECT cakupan, teks FROM ai_ringkasan"))
        check("ringkasan akun sendiri tersimpan setelah angka karangan ditolak",
            "sendiri" in rk and "999" not in rk["sendiri"], rk)
        check("ringkasan dengan rujukan [P99] palsu tidak disimpan", "kompetitor" not in rk, rk)
        check("cek angka: angka di luar fakta terdeteksi",
            A.check_summary(["Naik 12%."], '{"a": "13%"}', set()) != [])
        check("cek angka: angka dari fakta diterima",
            A.check_summary(["There were 1,547 engagements [P1]."], '{"a": "1,547", "k": "P1"}',
                                {"P1"}) == [])
        test_f = json.dumps({"text": "Latte art bareng Tara Senandika di Rimbun Roastery #KopiRimbun",
                            "tagline": "Hujan, Tetap Hangat", "posts": "14"}, ensure_ascii=False)
        check("hashtag asli diterima",
            A.check_summary(["Posts used #KopiRimbun [P1]."], test_f, {"P1"}) == [])
        check("hashtag yang diubah/diterjemahkan ditolak",
            A.check_summary(["Posts used #CoffeeRimbun."], test_f, set()) != [])
        check("tagline asli dalam kutipan diterima",
            A.check_summary(['The tagline "Hujan, Tetap Hangat" appeared.'], test_f, set()) == [])
        check("tagline yang diterjemahkan ditolak",
            A.check_summary(['The tagline "Rain, Still Warm" appeared.'], test_f, set()) != [])
        check("kutipan isi postingan yang diterjemahkan ditolak",
            A.check_summary(['A post said "Latte art with Tara Senandika at Rimbun Roastery".'], test_f, set()) != [])
        check("keamanan: tautan di kalimat AI ditolak",
            A.check_summary(["Claim your prize at https://bit.ly/x [P1]."], test_f, {"P1"}) != [])
        check("keamanan: markdown link di kalimat AI ditolak",
            A.check_summary(["Read [this](javascript:alert(1))."], test_f, set()) != [])
        check("keamanan: HTML di kalimat AI ditolak",
            A.check_summary(["<img src=x onerror=alert(1)> posts."], test_f, set()) != [])
        check("keamanan: alamat situs di kalimat AI ditolak",
            A.check_summary(["Visit promo-gratis.com now."], test_f, set()) != [])
        n_start = conn.execute("SELECT COUNT(*) FROM ai_ringkasan").fetchone()[0]
        A.build_summary(conn, "kunci-uji", fake)
        check("ringkasan tidak dibuat ulang jika fakta sama",
            conn.execute("SELECT COUNT(*) FROM ai_ringkasan WHERE cakupan='sendiri'").fetchone()[0] == 1,
            n_start)

        print("\nA3. Kompetitor dipisah dari akun sendiri")
        facts = A.build_facts(conn)["fakta"]
        check("jumlah postingan akun sendiri tidak memuat kompetitor",
            facts["sendiri"]["posts"] == "14", facts["sendiri"]["posts"])
        check("brand kompetitor dikenali",
            {b["brand"] for b in facts["kompetitor"]["by brand"]}
            == {"Kopi Senja", "Teh Lembah", "Kopi Rimbun (own accounts)"})
        conn.close()

    print("\nA4. Tanpa kunci API: dilewati dengan aman")
    os.environ.pop("GEMINI_API_KEY", None)
    check("main() selesai tanpa error", A.main() == 0)

    print(f"\n=== RINGKASAN AI: Lulus {sum(result)}/{len(result)} ===")
    return 0 if all(result) else 1


if __name__ == "__main__":
    sys.exit(main())
