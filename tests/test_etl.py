"""
PENGUJIAN SISTEM EMPLIFI (SQLite)

Menjalankan ETL asli dengan file Excel buatan di DATABASE SEMENTARA.
Database asli tidak disentuh sama sekali.

    python test_upsert.py
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

BASE = Path(__file__).resolve().parent.parent
ETL = BASE / "etl_emplifi.py"

T1 = datetime(2020, 1, 10, 8, 0, tzinfo=timezone.utc)
T0, T2, T3, T4 = (T1 + timedelta(days=d) for d in (-5, 5, 10, 15))
COLUMNS = ["Content ID", "Date", "Profile name", "Platform", "Content type", "Media type",
         "Labels", "Total interactions", "Total impressions", "Paid impressions",
         "Organic impressions", "Total reach", "Paid reach", "Organic reach",
         "Engagements", "Impressions engagement rate", "Reach engagement rate",
         "Link clicks", "Post clicks", "Video view count", "View on platform", "Content",
         "Link URL", "Post detail URL", "Profile URL", "Title",
         "Positive comments", "Negative comments", "Neutral comments", "Total comments", "Sentiment",
         "Collaborators"]

result = []


def row(cid, reach, labels, link=None):
    return {"Content ID": cid, "Date": datetime(2020, 1, 1, 9, 30), "Profile name": "Uji",
            "Platform": "Instagram", "Content type": "Post", "Media type": "Photo",
            "Labels": labels, "Total interactions": 50, "Total impressions": 1000,
            "Paid impressions": 0, "Organic impressions": 1000, "Total reach": reach,
            "Paid reach": 0, "Organic reach": reach, "Engagements": 50,
            "Impressions engagement rate": 0.05, "Reach engagement rate": 50 / reach,
            "Link clicks": 1, "Post clicks": 2, "Video view count": None,
            "View on platform": "View on platform" if link else None, "_link": link,
            "Content": f"Promo es kopi {cid} #KopiRimbun #NgopiDulu",
            "Positive comments": 12, "Negative comments": 3, "Neutral comments": 5,
            "Total comments": 22, "Sentiment": "Positive", "Collaborators": "Wening Asmara, Bagas Jenggala"}


def make_excel(folder, name, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Content"
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r.get(k) for k in COLUMNS])
        if r.get("_link"):                       # hyperlink tersembunyi, seperti Emplifi
            ws.cell(row=ws.max_row, column=COLUMNS.index("View on platform") + 1).hyperlink = r["_link"]
    path = Path(folder) / f"{name}.xlsx"
    wb.save(path)
    return path


def etl(path, timestamp, env):
    p = subprocess.run([sys.executable, str(ETL), str(path), format_datetime(timestamp)],
                       cwd=BASE, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def check(name, condition, detail=""):
    result.append((condition, name, detail))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + ("" if condition else f" -> {detail}"))


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        db = Path(folder) / "uji.db"
        env = {**os.environ, "EMPLIFI_DB": str(db), "PYTHONIOENCODING": "utf-8"}

        def q(sql, *p):
            with closing(sqlite3.connect(db)) as c:     # wajib ditutup (Windows mengunci file)
                return c.execute(sql, p).fetchall()

        def reach(cid):
            r = q("SELECT total_reach, source_email_at FROM emplifi_content WHERE content_id=?", cid)
            return r[0] if r else None

        def label(cid):
            return q("SELECT label_type, tower, campaign, sub_campaign, pillar FROM "
                     "emplifi_content_label WHERE content_id=? ORDER BY label_order", cid)

        print("\nS1. Import pertama")
        f1 = make_excel(folder, "S1", [
            row("C1", 100, "Pillar: Edukasi; Tower A - Camp A - Sub A",
                  link="https://www.instagram.com/p/AAA111/"),
            row("C2", 200, "Tower B - Camp B - Sub B"),
            row("C3", 300, None)])
        k, log = etl(f1, T1, env)
        check("S1 sukses", k == 0, log[-600:])
        check("S1 C1 reach 100", reach("C1") and reach("C1")[0] == 100)
        check("S1 C1 dua label benar", label("C1") == [
            ("PILLAR", None, None, None, "Edukasi"),
            ("TOWER_CAMPAIGN", "Tower A", "Camp A", "Sub A", None)], label("C1"))
        check("S1 C3 tanpa label", label("C3") == [])
        check("S1 waktu posting WIB tersimpan",
            q("SELECT date FROM emplifi_content WHERE content_id='C1'")[0][0] == "2020-01-01 09:30:00")

        print("\nS2. File sama diproses ulang")
        k, log = etl(f1, T1, env)
        check("S2 exit 0 dan dilewati", k == 0 and "SUDAH pernah diproses" in log, log[-300:])
        check("S2 RAW tidak bertambah", q("SELECT COUNT(*) FROM emplifi_raw")[0][0] == 3)

        print("\nS3. Laporan lebih baru")
        f3 = make_excel(folder, "S3", [
            row("C1", 150, "Pillar: Edukasi; Tower A - Camp A - Sub A",
                  link="https://www.instagram.com/p/AAA111/"),
            row("C2", 250, "Pillar: Promo"), row("C4", 400, "Tower C - Camp C - Sub C")])
        k, log = etl(f3, T2, env)
        check("S3 sukses", k == 0, log[-600:])
        check("S3 C1 diperbarui 150", reach("C1")[0] == 150)
        check("S3 C2 label diganti", label("C2") == [("PILLAR", None, None, None, "Promo")], label("C2"))
        check("S3 C3 tidak berubah", reach("C3")[0] == 300)
        check("S3 1 insert 2 update", "(insert)  : 1" in log and "diperbarui     : 2" in log, log[-500:])

        print("\nS4. Laporan LEBIH LAMA datang belakangan")
        k, log = etl(make_excel(folder, "S4", [row("C1", 90, "Tower Z - Z - Z")]), T0, env)
        check("S4 sukses, C1 tetap 150", k == 0 and reach("C1")[0] == 150, log[-400:])
        check("S4 label C1 tidak berubah", len(label("C1")) == 2)

        print("\nS5. Tanggal email sama, isi beda")
        k, log = etl(make_excel(folder, "S5", [row("C1", 999, None)]), T2, env)
        check("S5 C1 tetap 150", k == 0 and reach("C1")[0] == 150, log[-400:])

        print("\nS6. Data angka rusak -> rollback + tercatat gagal")
        broken = row("C5", 600, None); broken["Total reach"] = "bukan angka"
        f6 = make_excel(folder, "S6", [row("C1", 500, None), broken])
        k, log = etl(f6, T3, env)
        check("S6 gagal (exit 1)", k == 1, log[-300:])
        check("S6 C1 tetap 150 (rollback)", reach("C1")[0] == 150)
        check("S6 C5 tidak tersimpan", reach("C5") is None)
        check("S6 RAW tidak tersimpan", q("SELECT COUNT(*) FROM emplifi_raw WHERE source_file='S6.xlsx'")[0][0] == 0)
        log6 = q("SELECT status, pesan FROM import_log WHERE file_name='S6.xlsx'")
        check("S6 kegagalan tercatat di import_log",
            len(log6) == 1 and log6[0][0] == "failed" and "angka" in log6[0][1].lower(), log6)

        print("\nS7. File gagal boleh dicoba ulang setelah diperbaiki")
        f6b = make_excel(folder, "S6b", [row("C5", 600, "Tower X - Camp X - Sub X")])
        k, log = etl(f6b, T3, env)
        check("S7 sukses setelah diperbaiki", k == 0 and reach("C5")[0] == 600, log[-400:])

        print("\nS8. Content ID duplikat")
        k, log = etl(make_excel(folder, "S8", [row("C6", 1, None), row("C6", 2, None)]), T3, env)
        check("S8 ditolak", k != 0 and reach("C6") is None, log[-300:])

        print("\nS9. Label dihapus pada laporan baru")
        k, log = etl(make_excel(folder, "S9", [row("C2", 260, None)]), T4, env)
        check("S9 label C2 terhapus", k == 0 and label("C2") == [], log[-300:])

        print("\nS9b. Data mentah tidak menumpuk")
        n_raw = q("SELECT COUNT(*) FROM emplifi_raw")[0][0]
        n_content = q("SELECT COUNT(*) FROM emplifi_content")[0][0]
        check("S9b 1 baris mentah per konten (versi lama dipangkas)", n_raw == n_content, (n_raw, n_content))
        check("S9b mentah C1 = versi terbaru (S3)",
            q("SELECT source_file FROM emplifi_raw WHERE json_extract(raw_data,'$.\"Content ID\"')='C1'") == [("S3.xlsx",)])

        print("\nS10. View dashboard")
        n_table = q("SELECT COUNT(*) FROM emplifi_content")[0][0]
        n_view = q("SELECT COUNT(*) FROM v_content")[0][0]
        check("S10 v_content tidak menggandakan baris", n_table == n_view, (n_table, n_view))
        url = q("SELECT content_url, kolom_link FROM v_content WHERE content_id='C1'")
        check("S10 link C1 dari 'View on platform'",
            url == [("https://www.instagram.com/p/AAA111/", "View on platform")], url)
        check("S10 konten tanpa link -> kosong",
            q("SELECT content_url FROM v_content WHERE content_id='C4'") == [(None,)])
        cap = q("SELECT caption FROM v_content WHERE content_id='C1'")
        check("S10 teks postingan (caption) tersedia",
            cap == [("Promo es kopi C1 #KopiRimbun #NgopiDulu",)], cap)
        print("\nS11. Pemilihan link yang benar")
        r1 = row("L1", 10, None)                       # hanya link promo di dalam postingan
        r1.update({"Link URL": "https://kopirimbun.example/promo", "Profile URL": "https://www.instagram.com/kopirimbun.demo/"})
        r2 = row("L2", 10, None)                       # Post detail URL domain sosmed
        r2.update({"Post detail URL": "https://www.tiktok.com/@kopirimbun.demo/video/123"})
        r3 = row("L3", 10, None)                       # Post detail URL bukan sosmed
        r3.update({"Post detail URL": "https://app.emplifi.io/post/999"})
        r4 = row("L4", 10, None, link="https://www.instagram.com/p/VIEW4/")   # View on platform menang
        r4.update({"Post detail URL": "https://www.instagram.com/p/LAIN/", "Link URL": "https://x.co/promo"})
        r5 = row("L5", 10, None); r5.update({"Content": "", "Title": "Judul video YouTube"})
        k, log = etl(make_excel(folder, "S11", [r1, r2, r3, r4, r5]), T4 + timedelta(days=1), env)
        url = dict(q("SELECT content_id, content_url FROM v_content WHERE content_id LIKE 'L%'"))
        check("S11 sukses", k == 0, log[-300:])
        check("S11 Link URL & Profile URL TIDAK dipakai", url.get("L1") is None, url.get("L1"))
        check("S11 Post detail URL sosmed dipakai", url.get("L2") == "https://www.tiktok.com/@kopirimbun.demo/video/123", url.get("L2"))
        check("S11 Post detail URL non-sosmed ditolak", url.get("L3") is None, url.get("L3"))
        check("S11 View on platform diutamakan", url.get("L4") == "https://www.instagram.com/p/VIEW4/", url.get("L4"))
        check("S11 caption kosong -> pakai Title",
            q("SELECT caption FROM v_content WHERE content_id='L5'") == [("Judul video YouTube",)])

        sen = q("SELECT komentar_positif, komentar_negatif, komentar_netral, total_komentar, sentimen "
                "FROM v_content WHERE content_id='C1'")
        check("S12 sentimen komentar terbaca", sen == [(12, 3, 5, 22, "Positive")], sen)
        col = q("SELECT kolaborator FROM v_content WHERE content_id='C1'")
        check("S12 kolaborator terbaca", col == [("Wening Asmara, Bagas Jenggala",)], col)

        print("\nS13. Label tidak standar disimpan sebagai 'Label lain'")
        k, log = etl(make_excel(folder, "S13", [row("X1", 70,
            "Menu Musim Hujan; Pillar: Promo; Tower Q - Camp Q - Sub Q; Tower saja; Pillar:")]),
            T4 + timedelta(days=2), env)
        check("S13 laporan sukses (tidak digagalkan)", k == 0, log[-300:])
        lbl = q("SELECT label_type, label_raw FROM emplifi_content_label "
                "WHERE content_id='X1' ORDER BY label_order")
        check("S13 label tersimpan lengkap & berjenis benar", lbl == [
            ("LAINNYA", "Menu Musim Hujan"), ("PILLAR", "Pillar: Promo"),
            ("TOWER_CAMPAIGN", "Tower Q - Camp Q - Sub Q"), ("LAINNYA", "Tower saja"),
            ("LAINNYA", "Pillar:")], lbl)
        check("S13 view memuat label lain",
            q("SELECT labels_lain FROM v_content WHERE content_id='X1'")
            == [("Menu Musim Hujan, Pillar:, Tower saja",)])

        print("\nS14. Laporan akun publik/kompetitor (tanpa impressions & reach)")
        r = row("K1", 1, None)
        r.update({"Profile name": "Kopi Senja", "Total interactions": 777})
        for col in ["Total impressions", "Paid impressions", "Organic impressions", "Total reach",
                    "Paid reach", "Organic reach", "Engagements", "Impressions engagement rate",
                    "Reach engagement rate"]:
            r[col] = None
        f14 = make_excel(folder, "S14", [r])
        wb = load_workbook(f14)                    # hapus kolom impressions sepenuhnya
        ws = wb.active
        ws.delete_cols(COLUMNS.index("Total impressions") + 1)
        wb.save(f14)
        k, log = etl(f14, T4 + timedelta(days=3), env)
        check("S14 laporan tanpa kolom Total impressions tetap diterima", k == 0, log[-300:])
        check("S14 Total interactions tersimpan",
            q("SELECT total_interactions, total_impressions FROM v_content WHERE content_id='K1'")
            == [(777, None)])

        print("\nS15. Database lama (tanpa kolom & tabel baru) diperbarui otomatis")
        old = Path(folder) / "lama.db"
        with closing(sqlite3.connect(old)) as c:
            c.executescript(open(BASE / "db_sqlite.py", encoding="utf-8").read()
                            .split('SCHEMA = """')[1].split('"""')[0]
                            .replace("    total_interactions  INTEGER,"
                                     "               -- tersedia juga untuk akun publik (kompetitor)\n", "")
                            .split("-- Hasil AI per postingan")[0])
            c.commit()
            check("S15 database lama memang tanpa kolom",
                "total_interactions" not in {x[1] for x in c.execute("PRAGMA table_info(emplifi_content)")})
        sys.path.insert(0, str(BASE))
        from db_sqlite import open_db as _open_db, prepare as _prepare
        c = _open_db(old)
        _prepare(c)
        _prepare(c)                                # aman diulang
        column = {x[1] for x in c.execute("PRAGMA table_info(emplifi_content)")}
        table = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = c.execute("SELECT ai_versi FROM v_status").fetchone()[0]
        c.close()
        check("S15 kolom total_interactions & tabel AI ditambahkan",
            "total_interactions" in column and {"ai_konten", "ai_ringkasan"} <= table, (column, table))
        check("S15 v_status memuat ai_versi", version == "0-/0", version)

        print("\nS16. Database lama: caption/sentimen/kolaborator diisi ulang otomatis (cepat)")
        with closing(sqlite3.connect(db)) as c:
            c.execute("UPDATE emplifi_content SET caption = NULL, sentimen = NULL, "
                      "kolaborator = NULL, komentar_positif = NULL;")
            c.execute("PRAGMA user_version = 0;")
            c.commit()
        c = _open_db(db)
        _prepare(c)
        c.close()
        check("S16 caption & sentimen terisi kembali dari data mentah",
            q("SELECT caption IS NOT NULL, sentimen, kolaborator, komentar_positif "
              "FROM v_content WHERE content_id='C1'") == [(1, "Positive", "Wening Asmara, Bagas Jenggala", 12.0)],
            q("SELECT caption, sentimen, kolaborator, komentar_positif FROM v_content "
              "WHERE content_id='C1'"))
        check("S16 tidak diulang setelah selesai", q("PRAGMA user_version") == [(2,)])

        st = q("SELECT last_status, import_sukses FROM v_status")[0]
        check("S10 status terakhir tercatat", st[0] == "success" and st[1] >= 5, st)

    passed = sum(1 for ok, _, _ in result if ok)
    print(f"\n=== RINGKASAN: Lulus {passed}/{len(result)} ===")
    for ok, name, detail in result:
        if not ok:
            print(f"GAGAL: {name}\n  {detail}")
    sys.exit(0 if passed == len(result) else 1)


if __name__ == "__main__":
    main()
