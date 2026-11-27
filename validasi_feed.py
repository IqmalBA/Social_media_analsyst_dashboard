
from pathlib import Path
import hashlib
import sys
import pandas as pd

KOLOM_WAJIB = {
    "Content ID",
    "Date",
    "Profile name",
    "Platform",
    "Content type",
    "Media type",
    "Total interactions",
    # "Total impressions" tidak wajib: laporan akun publik (kompetitor) tidak memilikinya.
}


def sha256_file(path):
    hasher = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):
            hasher.update(chunk)

    return hasher.hexdigest()


def validasi_feed(path_file):
    path = Path(path_file)

    if not path.is_file():
        raise ValueError(
            f"File tidak ditemukan: {path}"
        )

    if path.suffix.lower() != ".xlsx":
        raise ValueError(
            "File harus berformat .xlsx"
        )

    with pd.ExcelFile(path) as excel:
        if "Content" not in excel.sheet_names:
            raise ValueError(
                "Bukan laporan Feed. "
                "Sheet Content tidak ditemukan."
            )

        data = pd.read_excel(
            excel,
            sheet_name="Content",
            dtype={"Content ID": "string"}
        )

    kolom_hilang = KOLOM_WAJIB - set(data.columns)

    if kolom_hilang:
        raise ValueError(
            f"Kolom wajib hilang: {sorted(kolom_hilang)}"
        )

    if data.empty:
        raise ValueError("Data Excel kosong")

    ids = data["Content ID"].astype("string").str.strip()

    jumlah_kosong = int(
        (ids.isna() | ids.eq("")).sum()
    )

    jumlah_duplikat = int(
        ids.duplicated().sum()
    )

    if jumlah_kosong > 0:
        raise ValueError(
            f"Ada {jumlah_kosong} Content ID kosong"
        )

    if jumlah_duplikat > 0:
        raise ValueError(
            f"Ada {jumlah_duplikat} Content ID duplikat"
        )

    print("\n=== VALIDASI FEED EMPLIFI ===")
    print("Nama file    :", path.name)
    print("Jumlah baris :", len(data))
    print("Jumlah kolom :", len(data.columns))
    print("Content ID   : Valid")
    print("SHA256       :", sha256_file(path))
    print("STATUS       : VALID")
    print("Database belum diubah.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Cara pakai: python validasi_feed.py '
            '"input\\nama_file.xlsx"'
        )
        sys.exit(2)

    try:
        validasi_feed(sys.argv[1])

    except (ValueError, OSError) as error:
        print("\nVALIDASI GAGAL:", error)
        sys.exit(1)
