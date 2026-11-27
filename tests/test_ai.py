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

hasil = []


def cek(nama, kondisi, detail=""):
    hasil.append(kondisi)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + ("" if kondisi else f" -> {detail}"))


CAPTION = ["Latte art bareng Tara Senandika di Rimbun Roastery #KopiRimbun",
           "Taraa! Menu baru udah datang di semua gerai",
           "Es Kopi Pandan bareng Wening Asmara: Hujan, Tetap Hangat",
           "Bagas lagi ngelawak soal antre, pesan lewat Rimbun App ya",
           "Promo es kopi akhir pekan",
           "Kak Tara nyeduh biji baru di Roastery"]


def ai_palsu(A):
    def panggil(prompt, sistem, skema, kunci):
        if skema is A.SKEMA_KONTEN:
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
        panggil.n = getattr(panggil, "n", 0) + 1
        fakta = json.loads(prompt.split("FAKTA:\n")[1].split("\n\nJawaban")[0])
        if panggil.n == 1:                   # BOHONG: angka karangan -> harus diulang
            return {"poin": ["Total engagements naik 999% [P1]."]}, "palsu"
        if "posts" in fakta:
            return {"poin": [f"There were {fakta['posts']} posts with total "
                             f"engagements of {fakta['total engagements']} [P1]."]}, "palsu"
        b = fakta["by brand"][0]            # BOHONG: rujukan [P99] tidak ada
        return {"poin": [f"{b['brand']} memimpin dengan {b['total interactions']} "
                         f"interactions [P99]."]}, "palsu"
    return panggil


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        db = str(Path(folder) / "uji.db")
        env = {**os.environ, "EMPLIFI_DB": db, "PYTHONIOENCODING": "utf-8"}
        rows = []
        for i in range(18):
            r = T.baris(f"C{i}", 1000 + i, "Tower A - Camp A - Sub A",
                        link=f"https://www.instagram.com/p/X{i}/")
            r.update({"Date": datetime(2026, 11, 1) + timedelta(hours=i * 12),
                      "Content": CAPTION[i % 6], "Profile name": "Kopi Rimbun", "Engagements": 100 + i,
                      "Collaborators": None})
            rows.append(r)
        for i, (prof, teks) in enumerate([("Kopi Senja", "Promo Kopi Senja diskon gede"),
                                          ("Teh Lembah", "Teh Lembah konser gratis")]):
            r = T.baris(f"K{i}", 1, None, link=f"https://www.instagram.com/p/K{i}/")
            r.update({"Date": datetime(2026, 11, 6), "Content": teks, "Profile name": prof,
                      "Total interactions": 500 * (i + 1), "Collaborators": None})
            rows.append(r)
        k, log = T.etl(T.buat_excel(folder, "feed", rows),
                       datetime(2026, 11, 14, 9, tzinfo=timezone.utc), env)
        cek("data uji masuk", k == 0, log[-300:])

        os.environ["EMPLIFI_DB"] = db
        import ai_analisis as A
        from db_sqlite import buka, siapkan
        A.JEDA_DETIK = 0
        conn = buka(db)
        siapkan(conn)
        palsu = ai_palsu(A)

        print("\nA1. Analisis per postingan")
        A.analisis_konten(conn, "kunci-uji", palsu)
        ent = {cid: {e["nama"] for e in json.loads(js)} for cid, js in
               conn.execute("SELECT content_id, entitas FROM ai_konten")}
        cek("Tara terdeteksi dengan kutipan sah", "Tara Senandika" in ent["C0"]
            and "Tara Senandika" in ent["C5"], ent)
        cek("'Taraa!' (seruan) TIDAK dianggap nama orang", ent["C1"] == set(), ent["C1"])
        cek("Bagas dengan kutipan 'Es Kopi Pandan' ditolak", ent["C2"] == {"Wening Asmara"}, ent["C2"])
        cek("kutipan yang tidak ada di caption ditolak", ent["C4"] == set(), ent["C4"])
        cek("id karangan tidak disimpan",
            conn.execute("SELECT COUNT(*) FROM ai_konten WHERE content_id='999'").fetchone()[0] == 0)
        cek("kategori di luar daftar ditolak",
            conn.execute("SELECT COUNT(*) FROM ai_konten WHERE topik NOT IN (%s)"
                         % ",".join("?" * len(A.TOPIK)), A.TOPIK).fetchone()[0] == 0)
        cek("tidak dianalisis ulang jika caption sama", A.antrean_konten(conn) == [])

        print("\nA2. Ringkasan naratif")
        A.buat_ringkasan(conn, "kunci-uji", palsu)
        rk = dict(conn.execute("SELECT cakupan, teks FROM ai_ringkasan"))
        cek("ringkasan akun sendiri tersimpan setelah angka karangan ditolak",
            "sendiri" in rk and "999" not in rk["sendiri"], rk)
        cek("ringkasan dengan rujukan [P99] palsu tidak disimpan", "kompetitor" not in rk, rk)
        cek("cek angka: angka di luar fakta terdeteksi",
            A.periksa_ringkasan(["Naik 12%."], '{"a": "13%"}', set()) != [])
        cek("cek angka: angka dari fakta diterima",
            A.periksa_ringkasan(["There were 1,547 engagements [P1]."], '{"a": "1,547", "k": "P1"}',
                                {"P1"}) == [])
        f_uji = json.dumps({"text": "Latte art bareng Tara Senandika di Rimbun Roastery #KopiRimbun",
                            "tagline": "Hujan, Tetap Hangat", "posts": "14"}, ensure_ascii=False)
        cek("hashtag asli diterima",
            A.periksa_ringkasan(["Posts used #KopiRimbun [P1]."], f_uji, {"P1"}) == [])
        cek("hashtag yang diubah/diterjemahkan ditolak",
            A.periksa_ringkasan(["Posts used #CoffeeRimbun."], f_uji, set()) != [])
        cek("tagline asli dalam kutipan diterima",
            A.periksa_ringkasan(['The tagline "Hujan, Tetap Hangat" appeared.'], f_uji, set()) == [])
        cek("tagline yang diterjemahkan ditolak",
            A.periksa_ringkasan(['The tagline "Rain, Still Warm" appeared.'], f_uji, set()) != [])
        cek("kutipan isi postingan yang diterjemahkan ditolak",
            A.periksa_ringkasan(['A post said "Latte art with Tara Senandika at Rimbun Roastery".'], f_uji, set()) != [])
        cek("keamanan: tautan di kalimat AI ditolak",
            A.periksa_ringkasan(["Claim your prize at https://bit.ly/x [P1]."], f_uji, {"P1"}) != [])
        cek("keamanan: markdown link di kalimat AI ditolak",
            A.periksa_ringkasan(["Read [this](javascript:alert(1))."], f_uji, set()) != [])
        cek("keamanan: HTML di kalimat AI ditolak",
            A.periksa_ringkasan(["<img src=x onerror=alert(1)> posts."], f_uji, set()) != [])
        cek("keamanan: alamat situs di kalimat AI ditolak",
            A.periksa_ringkasan(["Visit promo-gratis.com now."], f_uji, set()) != [])
        n_awal = conn.execute("SELECT COUNT(*) FROM ai_ringkasan").fetchone()[0]
        A.buat_ringkasan(conn, "kunci-uji", palsu)
        cek("ringkasan tidak dibuat ulang jika fakta sama",
            conn.execute("SELECT COUNT(*) FROM ai_ringkasan WHERE cakupan='sendiri'").fetchone()[0] == 1,
            n_awal)

        print("\nA3. Kompetitor dipisah dari akun sendiri")
        fakta = A.susun_fakta(conn)["fakta"]
        cek("jumlah postingan akun sendiri tidak memuat kompetitor",
            fakta["sendiri"]["posts"] == "14", fakta["sendiri"]["posts"])
        cek("brand kompetitor dikenali",
            {b["brand"] for b in fakta["kompetitor"]["by brand"]}
            == {"Kopi Senja", "Teh Lembah", "Kopi Rimbun (own accounts)"})
        conn.close()

    print("\nA4. Tanpa kunci API: dilewati dengan aman")
    os.environ.pop("GEMINI_API_KEY", None)
    cek("main() selesai tanpa error", A.main() == 0)

    print(f"\n=== RINGKASAN AI: Lulus {sum(hasil)}/{len(hasil)} ===")
    return 0 if all(hasil) else 1


if __name__ == "__main__":
    sys.exit(main())
