"""
Mengambil SEMUA alamat http(s) per konten dari Excel Emplifi:
  - hyperlink tersembunyi di balik teks sel (mis. "View on platform")
  - rumus =HYPERLINK("url", "teks")
  - alamat yang tertulis langsung di sel
Disimpan ke tabel emplifi_link. View dashboard memilih kolom yang benar.
"""

import re

from openpyxl import load_workbook

FORMULA_PATTERN = re.compile(r'HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def get_links(path, sheet="Content"):
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

        result = {}
        for row in ws.iter_rows(min_row=2):
            id_value = row[idx_id].value if idx_id < len(row) else None
            if id_value is None or str(id_value).strip() == "":
                continue
            content_id = str(id_value).strip()
            for i, sel in enumerate(row):
                name = header[i] if i < len(header) else None
                if not name:
                    continue
                url = None
                if sel.hyperlink is not None and sel.hyperlink.target:
                    url = sel.hyperlink.target
                elif isinstance(sel.value, str):
                    matches = FORMULA_PATTERN.search(sel.value)
                    url = matches.group(1) if matches else sel.value
                if url and URL_PATTERN.match(str(url).strip()):
                    result.setdefault(content_id, {})[name] = str(url).strip()
        return result
    finally:
        wb.close()


def save_links(conn, path, file_name):
    """Dipanggil ETL di dalam transaksi. Gagal membaca link tidak menggagalkan import."""
    try:
        data = get_links(path)
    except Exception as error:
        print("Peringatan: link postingan tidak bisa dibaca:", error)
        return 0
    row = [(file_name, cid, column, url)
             for cid, url_column in data.items() for column, url in url_column.items()]
    conn.executemany("""
        INSERT INTO emplifi_link (source_file, content_id, kolom, url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (source_file, content_id, kolom) DO UPDATE SET url = excluded.url;
    """, row)
    return len(row)
