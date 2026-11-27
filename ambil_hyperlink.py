"""
Mengambil SEMUA alamat http(s) per konten dari Excel Emplifi:
  - hyperlink tersembunyi di balik teks sel (mis. "View on platform")
  - rumus =HYPERLINK("url", "teks")
  - alamat yang tertulis langsung di sel
Disimpan ke tabel emplifi_link. View dashboard memilih kolom yang benar.
"""

import re

from openpyxl import load_workbook

POLA_RUMUS = re.compile(r'HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)
POLA_URL = re.compile(r"^https?://", re.IGNORECASE)


def ambil_link(path, sheet="Content"):
    """{content_id: {nama_kolom: url}}"""
    wb = load_workbook(path, read_only=False, data_only=False)
    try:
        if sheet not in wb.sheetnames:
            return {}
        ws = wb[sheet]
        header = [str(c.value).strip() if c.value is not None else None for c in ws[1]]
        if "Content ID" not in header:
            return {}
        idx_id = header.index("Content ID")

        hasil = {}
        for baris in ws.iter_rows(min_row=2):
            nilai_id = baris[idx_id].value if idx_id < len(baris) else None
            if nilai_id is None or str(nilai_id).strip() == "":
                continue
            content_id = str(nilai_id).strip()
            for i, sel in enumerate(baris):
                nama = header[i] if i < len(header) else None
                if not nama:
                    continue
                url = None
                if sel.hyperlink is not None and sel.hyperlink.target:
                    url = sel.hyperlink.target
                elif isinstance(sel.value, str):
                    cocok = POLA_RUMUS.search(sel.value)
                    url = cocok.group(1) if cocok else sel.value
                if url and POLA_URL.match(str(url).strip()):
                    hasil.setdefault(content_id, {})[nama] = str(url).strip()
        return hasil
    finally:
        wb.close()


def simpan_link(conn, path, file_name):
    """Dipanggil ETL di dalam transaksi. Gagal membaca link tidak menggagalkan import."""
    try:
        data = ambil_link(path)
    except Exception as error:
        print("Peringatan: link postingan tidak bisa dibaca:", error)
        return 0
    baris = [(file_name, cid, kolom, url)
             for cid, kolom_url in data.items() for kolom, url in kolom_url.items()]
    conn.executemany("""
        INSERT INTO emplifi_link (source_file, content_id, kolom, url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (source_file, content_id, kolom) DO UPDATE SET url = excluded.url;
    """, baris)
    return len(baris)
