"""
Demo data generator - FICTIONAL brand "Kopi Rimbun".

Builds Emplifi-style Feed reports (3 accounts, 4 platforms, ~90 days), runs them
through the real ETL (10 daily reports, so the UPSERT/date protection is exercised),
then adds pre-generated AI results that pass the same validation as production.

All brands, people, posts, links, and numbers are fictional. Any resemblance to
real brands, accounts, or people is coincidental. Post links point to example.com.

    python demo/generate_demo_data.py
"""

import os
import random
import string
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from openpyxl import Workbook

BASE = Path(__file__).resolve().parent.parent
TUJUAN = BASE / "demo" / "emplifi_demo.db"
ETL = BASE / "etl_emplifi.py"
rnd = random.Random(20251)

# ---------------------------------------------------------------------------
# AKUN (fiktif)
# ---------------------------------------------------------------------------
AKUN = {
    "Kopi Rimbun":     {"platform": {"Instagram": 0.40, "TikTok": 0.35, "Facebook": 0.25},
                        "skala": 1.0, "handle": "kopirimbun.demo", "rata": 2.2},
    "Rimbun App":      {"platform": {"Instagram": 0.55, "TikTok": 0.45},
                        "skala": 0.55, "handle": "rimbunapp.demo", "rata": 1.3},
    "Rimbun Roastery": {"platform": {"Instagram": 0.70, "YouTube": 0.30},
                        "skala": 0.30, "handle": "rimbunroastery.demo", "rata": 0.6},
}
FORMAT = {  # platform -> (content type, media type, bobot)
    "Instagram": [("Post", "Photo", 0.45), ("Post", "Carousel", 0.25), ("Reel", "Video", 0.30)],
    "TikTok":    [("Video", "Video", 1.0)],
    "Facebook":  [("Post", "Photo", 0.6), ("Post", "Video", 0.25), ("Post", "Link", 0.15)],
    "YouTube":   [("Video", "Video", 0.6), ("Short", "Video", 0.4)],
}
MULT_PLATFORM = {"Instagram": 1.0, "TikTok": 1.9, "Facebook": 0.45, "YouTube": 0.35}

# ---------------------------------------------------------------------------
# TEMA KONTEN: caption ditulis manual, label, pengali engagement, porsi komentar negatif.
# "aktif" = rentang hari (0-89) campaign berjalan; None = sepanjang waktu.
# ---------------------------------------------------------------------------
TEMA = {
    "pandan": dict(akun=["Kopi Rimbun", "Rimbun App"], pillar="Produk",
        kampanye="Retail - Menu Musim Hujan - Es Kopi Pandan", aktif=(10, 55), er=1.4, neg=0.03,
        caption=[
            "Hujan-hujan gini enaknya yang manis tapi tetep seger 🌧️ Es Kopi Pandan udah balik di semua gerai ya! #KopiRimbun #EsKopiPandan",
            "Yang kemarin nanya-nanya, iya, Es Kopi Pandan comeback 💚 Cuma sampai akhir bulan, jangan sampe kelewat.",
            "Pandan + espresso + susu segar. Udah, itu aja sih resepnya 😌 Kamu tim less sugar atau normal? #EsKopiPandan",
            "POV: hari pertama Es Kopi Pandan rilis dan antrean udah sampe depan pintu 😅 makasih yaa semuanya 🙏",
            "Pesan lewat Rimbun App, ambil di gerai tanpa antre. Es Kopi Pandan juga bisa ya 👀 #RimbunApp",
        ]),
    "gajian": dict(akun=["Kopi Rimbun", "Rimbun App"], pillar="Promo",
        kampanye="Retail - Promo Gajian - Diskon Tanggal Tua", aktif=None, er=1.1, neg=0.06,
        caption=[
            "Tanggal tua tapi ngopi tetep jalan ☕ Diskon 30% semua minuman kopi, 25-28 tiap bulan. #PromoGajian",
            "Gajian udah, ngopi belum? 😏 Pakai kode RIMBUNGAJIAN di aplikasi, potongan sampai 20rb.",
            "Promo gajian balik lagi! Beli 2 gratis 1 khusus pembelian lewat Rimbun App ✨ Ajak temen sekantor sekalian.",
            "Reminder buat yang suka lupa: promo gajian berakhir besok jam 23.59 ⏰",
        ]),
    "app": dict(akun=["Rimbun App"], pillar="Produk",
        kampanye="Digital - Rimbun App - Fitur Pre-order", aktif=(30, 89), er=0.9, neg=0.10,
        caption=[
            "Fitur baru: pre-order dari rumah, kopinya udah siap pas kamu sampai 🚶‍♂️☕ Update aplikasinya sekarang ya.",
            "Sekarang bisa pilih jam ambil pesanan sendiri. Kecil, tapi ngaruh banget buat yang ngejar meeting jam 9 😮‍💨",
            "Poin Rimbun bisa dituker jadi minuman gratis, cek menu 'Tukar Poin' di aplikasi 🎁 #RimbunApp",
            "Udah coba bayar pakai QRIS di aplikasi? Lebih cepat, nggak perlu nyari kembalian lagi 😄",
        ]),
    "maintenance": dict(akun=["Rimbun App"], pillar="Info",
        kampanye="Corporate - Layanan Pelanggan - Pemeliharaan Sistem", aktif=(62, 64), er=0.6, neg=0.48,
        caption=[
            "Mohon maaf, Rimbun App sedang dalam pemeliharaan sistem pukul 22.00-02.00 WIB. Pesanan di gerai tetap bisa ya 🙏",
            "Update: sebagian pengguna masih mengalami gagal login setelah pemeliharaan. Tim kami sedang menangani, terima kasih atas kesabarannya.",
            "Kendala login sudah teratasi. Bagi yang poinnya belum masuk, DM kami nomor pesanan kamu ya 🙏",
        ]),
    "barista": dict(akun=["Kopi Rimbun"], pillar="Lifestyle",
        kampanye="Community - Barista Rimbun - Behind the Bar", aktif=None, er=1.3, neg=0.02,
        caption=[
            "Kenalan sama Mas Dimas, barista gerai Tebet yang hafal pesanan pelanggan tetapnya 😂 Siapa yang pernah dilayanin dia?",
            "Behind the bar: 1 jam sebelum gerai buka itu ngapain aja sih? Spill di video ya 👇",
            "Latte art level: masih belajar vs udah 3 tahun di bar 😆 #BaristaRimbun",
            "Shoutout buat tim gerai Bandung yang tetap senyum walau order online lagi rame-ramenya 🙌",
        ]),
    "petani": dict(akun=["Kopi Rimbun", "Rimbun Roastery"], pillar="Edukasi",
        kampanye="Brand - Dari Kebun - Cerita Petani", aktif=None, er=0.95, neg=0.02,
        caption=[
            "Kopi yang kamu minum pagi ini dipetik di lereng Gunung Puntang, 1.400 mdpl ⛰️ Kenalan sama Pak Asep, petaninya.",
            "Kenapa harga kopi spesialti lebih mahal? Salah satunya karena dipetik merah satu per satu. Thread singkat ↓",
            "Dari ceri ke cangkir: proses natural butuh 3-4 minggu penjemuran. Sabar dikit demi rasa buah yang keluar 🍒",
        ]),
    "seduh": dict(akun=["Rimbun Roastery"], pillar="Edukasi",
        kampanye="Brand - Seduh di Rumah - Tutorial", aktif=None, er=1.0, neg=0.03,
        caption=[
            "Seduh V60 di rumah: 15 gram kopi, 250 ml air 92°C, total 3 menit. Gampang kan? Full tutorial di video.",
            "Kesalahan paling sering pas bikin kopi tubruk di rumah (dan cara benerinnya) ☕",
            "French press tanpa ampas? Bisa. Kuncinya di ukuran gilingan 👀",
            "Biji baru: Aceh Gayo natural. Notes: nangka, cokelat susu, sedikit rempah. Ready di toko online ya.",
        ]),
    "giveaway": dict(akun=["Kopi Rimbun", "Rimbun App"], pillar="Engagement",
        kampanye="Community - Giveaway - Tumbler Edisi Terbatas", aktif=(40, 47), er=2.6, neg=0.04,
        caption=[
            "GIVEAWAY 🎉 5 tumbler edisi terbatas buat 5 orang beruntung! Caranya: follow, like, tag 3 teman ngopimu di komentar.",
            "Masih ada 2 hari buat ikut giveaway tumbler! Jangan lupa tag temen yang paling sering kamu traktir 😆",
            "Pemenang giveaway tumbler udah diumumkan di story ya. Selamat buat yang menang! 🥳",
        ]),
    "gerai": dict(akun=["Kopi Rimbun"], pillar="Info",
        kampanye="Retail - Gerai Baru - Grand Opening", aktif=(70, 80), er=1.2, neg=0.05,
        caption=[
            "Rimbun ke-24 resmi buka di Bintaro! 🎊 3 hari pertama ada free upsize untuk semua minuman.",
            "Gerai baru, suasana baru. Area kerjanya luas dan colokannya banyak, cocok buat WFC 💻",
            "Jam operasional gerai Bintaro: 07.00-22.00 setiap hari. Sampai ketemu! 👋",
        ]),
    "wening": dict(akun=["Kopi Rimbun"], pillar="Produk", kolab="Wening Asmara",
        kampanye="Retail - Menu Musim Hujan - Wening Asmara", aktif=(15, 89), er=1.9, neg=0.03,
        caption=[
            "Wening Asmara nyobain Es Kopi Pandan pertama kalinya, reaksinya bisa ditebak 😆 #KopiRimbun",
            "Playlist hujan versi Wening Asmara + segelas kopi pandan. Lagu mana yang paling pas? 🎶",
            "Behind the scene shooting bareng @weningasmara.demo kemarin, ternyata dia tim less sugar 🤫",
            "Wening Asmara bakal live akustik di gerai Kemang Sabtu ini 🎤 Datang lebih awal ya!",
        ]),
    "bagas": dict(akun=["Rimbun App"], pillar="Engagement", kolab="Bagas Jenggala",
        kampanye="Digital - Rimbun App - Antre Bareng Bagas", aktif=(25, 89), er=1.7, neg=0.05,
        caption=[
            "Bagas Jenggala vs antrean kopi jam 8 pagi. Siapa yang menang? 😂 Pre-order lewat Rimbun App aja.",
            "Kata Bagas Jenggala: 'ngantre itu cardio'. Kata kami: pakai Rimbun App biar nggak perlu cardio 🏃",
            "Episode baru #AntreBarengBagas udah tayang! Kali ini Bagas nyobain tukar poin pertama kali 🎁",
        ]),
    "tara": dict(akun=["Rimbun Roastery"], pillar="Edukasi", kolab="Tara Senandika",
        kampanye="Brand - Seduh di Rumah - Bareng Kak Tara", aktif=None, er=1.3, neg=0.02,
        caption=[
            "Kak Tara Senandika bagi trik rahasia biar V60 kamu nggak pahit ☕ Simpan dulu postingan ini!",
            "Tara Senandika, juara barista nasional tahun lalu, cerita kenapa dia selalu nimbang air 💧",
            "Q&A bareng Kak Tara: grinder manual atau elektrik buat pemula? Jawabannya di video 👇",
        ]),
    "ringan": dict(akun=["Kopi Rimbun", "Rimbun App", "Rimbun Roastery"], pillar="Lifestyle",
        kampanye=None, aktif=None, er=1.05, neg=0.03,
        caption=[
            "Senin pagi checklist: ✅ bangun ✅ ngopi ❌ semangat 😂",
            "Kopi pertama hari ini kamu minum jam berapa? 👇",
            "Tipe orang pas ngantre kopi: 1. udah tau mau pesen apa 2. baru mikir pas di kasir. Kamu yang mana? 😆",
            "Weekend plan: ngopi, baca buku, ngopi lagi ☕📖",
            "Rate kopi kamu hari ini dari 1-10 👀",
        ]),
}
# Potongan untuk merangkai caption agar tidak ada yang kembar
TAMBAHAN = {
    "pandan": dict(pembuka=["Akhirnya!", "Musim hujan = musim pandan 🌿", "Spoiler dikit…", "Taraa! 🎉", ""],
                   cta=["Udah nyobain belum?", "Tag temen yang wajib nyobain 👇", "Cek gerai terdekat ya!",
                        "Mau versi hot atau iced? Tulis di komentar ☕"],
                   tag=["#KopiRimbun", "#EsKopiPandan", "#MenuMusimHujan", "#NgopiDulu", "#KopiSusuLokal"]),
    "gajian": dict(pembuka=["Tanggal tua mode on 🫠", "Info penting buat dompet kamu 💸", "Psst…", ""],
                   cta=["Berlaku di semua gerai.", "S&K berlaku ya.", "Jangan lupa update aplikasinya.",
                        "Siapa yang langsung checkout? 🙋"],
                   tag=["#PromoGajian", "#KopiRimbun", "#RimbunApp", "#HematNgopi", "#PromoKopi"]),
    "app": dict(pembuka=["Update kecil, efeknya besar ✨", "Fitur yang paling banyak kalian minta akhirnya datang!",
                         "Rimbun App versi terbaru udah rilis 📲", ""],
                cta=["Coba sekarang dan kasih tau pendapatmu!", "Update di Play Store / App Store ya.",
                     "Ada saran fitur lain? Komen aja 👇", ""],
                tag=["#RimbunApp", "#NgopiPraktis", "#PreOrder", "#KopiRimbun"]),
    "maintenance": dict(pembuka=[""], cta=["", "Terima kasih atas pengertiannya 🙏"],
                        tag=["#RimbunApp", "#InfoLayanan", ""]),
    "barista": dict(pembuka=["Cerita dari balik bar ☕", "Tim gerai kita emang beda 😎", ""],
                    cta=["Sapa mereka kalau mampir ya!", "Barista favorit kamu siapa? 👇", ""],
                    tag=["#BaristaRimbun", "#BehindTheBar", "#KopiRimbun", "#OrangKopi"]),
    "petani": dict(pembuka=["Dari kebun, untuk kamu 🌱", "Cerita di balik secangkir kopi:", ""],
                   cta=["Baca selengkapnya di caption slide terakhir.", "Dukung petani kopi lokal 🤎", ""],
                   tag=["#DariKebun", "#KopiLokal", "#PetaniKopi", "#KopiRimbun", "#SpecialtyCoffee"]),
    "seduh": dict(pembuka=["Seduh di rumah, rasa kayak di kafe ☕", "Tutorial singkat hari ini:", ""],
                  cta=["Simpan postingan ini biar nggak lupa 📌", "Mau tutorial alat apa lagi? Komen ya.", ""],
                  tag=["#SeduhDiRumah", "#ManualBrew", "#RimbunRoastery", "#HomeBrewing", "#V60"]),
    "giveaway": dict(pembuka=["", "Waktunya bagi-bagi 🎁"],
                     cta=["Periode s.d. Minggu 23.59 WIB.", "Pemenang diumumkan di story.", ""],
                     tag=["#GiveawayRimbun", "#KopiRimbun", "#Giveaway", "#TumblerRimbun"]),
    "gerai": dict(pembuka=["Hai, Bintaro! 👋", "Tempat ngopi baru di selatan Jakarta ✨", "Taraa! ✨", ""],
                  cta=["Share ke temen yang tinggal di Bintaro!", "Lokasinya ada di Maps: Kopi Rimbun Bintaro.", ""],
                  tag=["#KopiRimbun", "#GeraiBaru", "#NgopiBintaro", "#WFC"]),
    "ringan": dict(pembuka=[""], cta=["", "Jawab di komentar 👇", "Jujur aja 😆"],
                   tag=["#KopiRimbun", "#NgopiDulu", "#CoffeeTime", ""]),
    "wening": dict(pembuka=["", "Kolaborasi yang ditunggu-tunggu 💚"],
                   cta=["", "Kamu tim Wening yang mana? 👇"],
                   tag=["#KopiRimbun", "#EsKopiPandan", "#WeningXRimbun"]),
    "bagas": dict(pembuka=["", "Episode baru!"], cta=["", "Tag temen yang suka telat ngantor 😆"],
                  tag=["#RimbunApp", "#AntreBarengBagas", "#KopiRimbun"]),
    "tara": dict(pembuka=["", "Kelas seduh singkat ☕"], cta=["", "Mau dibahas alat apa lagi?"],
                 tag=["#RimbunRoastery", "#SeduhDiRumah", "#BarengKakTara"]),
}


def rangkai_caption(tema, terpakai_global):
    """Gabungkan pembuka + inti + ajakan + hashtag; ulangi bila kebetulan kembar."""
    t, inti = TAMBAHAN[tema], TEMA[tema]["caption"]
    for _ in range(25):
        dasar = rnd.choice(inti)
        bagian = [rnd.choice(t["pembuka"]) if rnd.random() < 0.4 else "", dasar]
        if rnd.random() < 0.6:
            bagian.append(rnd.choice(t["cta"]))
        if "#" not in dasar and rnd.random() < 0.75:
            tag = [x for x in t["tag"] if x]
            bagian.append(" ".join(rnd.sample(tag, k=min(len(tag), rnd.randint(1, 3)))))
        teks = " ".join(x for x in bagian if x).strip()
        if rnd.random() < 0.3:
            teks = teks.replace(". ", ".\n\n", 1)        # sebagian caption berparagraf
        if teks not in terpakai_global:
            terpakai_global.add(teks)
            return teks
    return None


BOBOT_TEMA = {"pandan": 1.4, "gajian": 1.0, "app": 1.0, "maintenance": 2.5, "barista": 0.9,
              "petani": 0.7, "seduh": 0.9, "giveaway": 2.0, "gerai": 1.6, "ringan": 1.3,
              "wening": 0.9, "bagas": 0.8, "tara": 0.8}
KOLOM = ["Date", "Profile name", "Profile URL", "Platform", "Content type", "Media type",
         "Content ID", "Content", "View on platform", "Link URL", "Labels", "Total interactions",
         "Total impressions", "Paid impressions", "Organic impressions", "Total reach",
         "Paid reach", "Organic reach", "Engagements", "Impressions engagement rate",
         "Reach engagement rate", "Link clicks", "Post clicks", "Video view count",
         "Positive comments", "Negative comments", "Neutral comments", "Total comments", "Sentiment",
         "Collaborators"]


def pilih(bobot):
    return rnd.choices(list(bobot), weights=list(bobot.values()))[0]


def kode(n, huruf=string.ascii_letters + string.digits + "_-"):
    return "".join(rnd.choice(huruf) for _ in range(n))


def id_dan_link(akun, platform, waktu):
    """Emplifi-like Content ID; the post link points to example.com (never a real post)."""
    if platform == "Instagram":
        cid = f"17841{rnd.randint(10**11, 10**12 - 1)}_{rnd.randint(10**16, 10**17 - 1)}"
    elif platform == "TikTok":
        cid = f"7{int(waktu.timestamp()) % 10**9:09d}{rnd.randint(10**8, 10**9 - 1)}"
    elif platform == "Facebook":
        cid = f"10{rnd.randint(10**12, 10**13 - 1)}_{rnd.randint(10**14, 10**15 - 1)}"
    else:
        cid = kode(11)
    return cid, f"https://example.com/demo/{platform.lower()}/{cid}"


def tema_aktif(nama, hari_ke):
    a = TEMA[nama]["aktif"]
    return a is None or a[0] <= hari_ke <= a[1]


def buat_postingan(akhir, hari=90):
    posts, terpakai = [], set()
    for d in range(hari):
        tanggal = akhir - timedelta(days=hari - d)
        akhir_pekan = tanggal.weekday() >= 5
        for akun, info in AKUN.items():
            jumlah = max(0, int(round(rnd.gauss(info["rata"] * (0.8 if akhir_pekan else 1.0), 0.9))))
            for _ in range(jumlah):
                kandidat = {t: BOBOT_TEMA[t] for t, v in TEMA.items()
                            if akun in v["akun"] and tema_aktif(t, d) and t != "maintenance"}
                tema = pilih(kandidat)
                v = TEMA[tema]
                caption = rangkai_caption(tema, terpakai)
                if caption is None:
                    continue
                plat = pilih(info["platform"])
                tipe, media, _ = rnd.choices(FORMAT[plat], weights=[f[2] for f in FORMAT[plat]])[0]
                jam = rnd.choices([7, 8, 11, 12, 13, 16, 18, 19, 20, 21],
                                  weights=[3, 4, 3, 5, 3, 2, 4, 6, 6, 4])[0]
                waktu = tanggal.replace(hour=jam,
                                        minute=rnd.choice([0, 0, 15, 30, 30, 45, rnd.randint(1, 59)]))
                labels = [f"Pillar: {v['pillar']}"]
                if v["kampanye"]:
                    labels.append(v["kampanye"])
                if tema in ("gajian", "app") and rnd.random() < 0.25:     # sebagian berlabel ganda
                    labels.append("Digital - Rimbun App - Cross Promo")
                if rnd.random() < 0.05:                                    # lupa diberi label
                    labels = []
                cid, link = id_dan_link(akun, plat, waktu)
                viral = 4.5 if rnd.random() < 0.025 else (2.2 if tema == "maintenance" else 1.0)
                posts.append(dict(
                    id=cid, link=link, akun=akun, platform=plat, tipe=tipe, media=media,
                    waktu=waktu, caption=caption, tema=tema, labels="; ".join(labels),
                    kolab=v.get("kolab"),
                    er=v["er"], neg=v["neg"],
                    basis=rnd.lognormvariate(9.6, 0.55) * info["skala"] * MULT_PLATFORM[plat]
                    * viral * (1.15 if akhir_pekan else 1.0)))
    # Kejadian gangguan aplikasi: pengumuman -> update kendala -> teratasi
    v = TEMA["maintenance"]
    for (hari_ke, jam, menit), caption in zip([(62, 20, 45), (63, 9, 10), (63, 16, 30)], v["caption"]):
        waktu = (akhir - timedelta(days=hari - hari_ke)).replace(hour=jam, minute=menit)
        plat = "Instagram"
        cid, link = id_dan_link("Rimbun App", plat, waktu)
        posts.append(dict(id=cid, link=link, akun="Rimbun App", platform=plat, tipe="Post",
                          media="Photo", waktu=waktu, caption=caption, tema="maintenance",
                          labels=f"Pillar: {v['pillar']}; {v['kampanye']}", er=v["er"], neg=v["neg"],
                          basis=rnd.lognormvariate(9.6, 0.3) * AKUN["Rimbun App"]["skala"] * 2.4))
    posts.sort(key=lambda p: p["waktu"])
    return posts


def baris(p, umur):
    tumbuh = 1 - 0.62 * (0.55 ** max(umur, 0))        # angka lifetime naik lalu melandai
    imp = int(p["basis"] * tumbuh)
    reach = int(imp * rnd.uniform(0.62, 0.86))
    eng = int(imp * rnd.uniform(0.012, 0.03) * p["er"])
    porsi_komentar = {"giveaway": 0.20, "maintenance": rnd.uniform(0.35, 0.55)}
    kom = int(eng * porsi_komentar.get(p["tema"], rnd.uniform(0.03, 0.09)))
    neg = int(round(kom * p["neg"] * rnd.uniform(0.6, 1.4)))
    pos = int(round((kom - neg) * rnd.uniform(0.55, 0.8)))
    netral = max(0, kom - neg - pos)
    akun = AKUN[p["akun"]]
    return {
        "Date": p["waktu"], "Profile name": p["akun"], "Platform": p["platform"],
        "Profile URL": f"https://example.com/{p['platform'].lower()}/{akun['handle']}",
        "Content type": p["tipe"], "Media type": p["media"], "Content ID": p["id"],
        "Content": p["caption"], "View on platform": "View on platform",
        "Link URL": "https://example.com/kopirimbun/promo" if p["tema"] == "gajian" else None,
        "Labels": p["labels"] or None, "Total interactions": eng, "Total impressions": imp,
        "Paid impressions": 0, "Organic impressions": imp, "Total reach": reach,
        "Paid reach": 0, "Organic reach": reach, "Engagements": eng,
        "Impressions engagement rate": round(eng / imp, 4) if imp else None,
        "Reach engagement rate": round(eng / reach, 4) if reach else None,
        "Link clicks": int(eng * rnd.uniform(0.01, 0.06)),
        "Post clicks": int(eng * rnd.uniform(0.1, 0.3)),
        "Video view count": int(imp * rnd.uniform(0.35, 0.7)) if p["media"] == "Video" else None,
        "Positive comments": pos, "Negative comments": neg, "Neutral comments": netral,
        "Total comments": kom + rnd.randint(0, 3),
        "Sentiment": "Negative" if neg > pos else ("Positive" if pos else "Neutral"),
        "Collaborators": p.get("kolab"),
        "_link": p["link"],
    }


def tulis_excel(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Content"
    ws.append(KOLOM)
    kol = KOLOM.index("View on platform") + 1
    for r in rows:
        ws.append([r.get(k) for k in KOLOM])
        ws.cell(row=ws.max_row, column=kol).hyperlink = r["_link"]
    wb.save(path)


TOPIK_TEMA = {"pandan": "New menu & products", "gajian": "Promos & deals", "app": "App & ordering",
              "maintenance": "Service updates", "barista": "Community & people",
              "petani": "Coffee education", "seduh": "Coffee education", "giveaway": "Giveaways",
              "gerai": "Stores & openings", "ringan": "Lifestyle & moments",
              "wening": "New menu & products", "bagas": "App & ordering", "tara": "Coffee education"}


def isi_hasil_ai(posts):
    """Pre-generated AI results for the demo (no API key needed). They go through the
    SAME checks as live Gemini output: quotes must exist in the caption and contain
    the name; summary numbers must match the computed facts exactly."""
    import json
    import re
    sys.path.insert(0, str(BASE))
    os.environ["EMPLIFI_DB"] = str(TUJUAN)
    import ai_analisis as A
    from brand_watch import ENTITAS, bukti_valid, normal
    from db_sqlite import buka, sekarang, siapkan

    conn = buka(TUJUAN)
    siapkan(conn)
    ada = {cid: (teks or "") for cid, teks in conn.execute("SELECT content_id, caption FROM v_content")}
    baris = []
    for p in posts:
        if p["id"] not in ada:
            continue
        teks = ada[p["id"]]
        entitas = []
        for nama, e in ENTITAS.items():
            pola = "|".join(re.escape(k) for k in sorted(e["kata_kunci"] + [nama], key=len, reverse=True))
            for m in re.finditer(pola, teks, re.I):
                if bukti_valid(nama, m.group(0), teks):
                    entitas.append({"nama": nama, "bukti": m.group(0)})
                    break
        baris.append((p["id"], A.hash_teks(teks), TOPIK_TEMA[p["tema"]],
                      json.dumps(entitas, ensure_ascii=False), "demo (pre-generated)", sekarang()))
    conn.execute("BEGIN;")
    conn.executemany("INSERT OR REPLACE INTO ai_konten VALUES (?, ?, ?, ?, ?, ?);", baris)
    conn.execute("COMMIT;")

    hasil = A.susun_fakta(conn)
    f = hasil["fakta"]["sendiri"]
    fakta_teks = json.dumps(f, ensure_ascii=False, indent=1)
    kode_sah = {k for k in hasil["rujukan"] if f'"{k}"' in fakta_teks}
    calon = [f"Our accounts published {f['posts']} posts with {f['total engagements']} total "
             f"engagements, an average of {f['average engagements per post']} per post."]
    ubah = f.get("change in total engagements vs previous period")
    if ubah:
        arah = "down" if ubah.startswith("-") else "up"
        calon.append(f"Total engagements were {arah} {ubah.lstrip('-')} compared with the previous period.")
    if f.get("top topics"):
        t = f["top topics"][0]
        calon.append(f"{t['topic']} was the most frequent topic ({t['posts']} posts, "
                     f"{t['average engagements']} average engagements).")
    if f.get("top posts by engagements"):
        t = f["top posts by engagements"][0]
        calon.append(f"The most engaged post came from {t['account']} on {t['platform']} "
                     f"with {t['engagements']} engagements [{t['code']}].")
    nama = [n for n in f.get("names mentioned", []) if n["name"] != "Rimbun App"]
    if nama:
        n = max(nama, key=lambda x: float(x["posts"].replace(",", "")))
        calon.append(f"{n['name']} appeared in {n['posts']} posts, averaging "
                     f"{n['average engagements']} engagements per post.")
    poin = [c for c in calon if not A.periksa_ringkasan([c], fakta_teks, kode_sah)]
    rujukan = {k: hasil["rujukan"][k] for k in kode_sah}
    conn.execute("INSERT INTO ai_ringkasan (cakupan, periode_awal, periode_akhir, teks, rujukan, "
                 "fakta, model, dibuat) VALUES ('sendiri', ?, ?, ?, ?, ?, ?, ?);",
                 (hasil["awal"], hasil["akhir"], "\n".join(f"- {x}" for x in poin),
                  json.dumps(rujukan), fakta_teks, "demo (pre-generated)", sekarang()))
    conn.commit() if conn.in_transaction else None
    conn.execute("VACUUM;")
    conn.close()
    print(f"AI demo: {len(baris)} posts analysed, summary {len(poin)}/{len(calon)} sentences passed validation")


def main():
    TUJUAN.unlink(missing_ok=True)
    akhir = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    posts = buat_postingan(akhir)
    env = {**os.environ, "EMPLIFI_DB": str(TUJUAN), "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        for i, hari in enumerate(range(10, 0, -1)):            # 10 laporan harian terakhir
            tgl = akhir - timedelta(days=hari - 1)
            batas = timedelta(days=95 if i == 0 else 30)         # laporan pertama = riwayat penuh
            isi = [baris(p, (tgl - p["waktu"]).days) for p in posts
                   if timedelta(0) < tgl - p["waktu"] <= batas]
            path = Path(folder) / f"Feed - {tgl:%Y-%m-%d}.xlsx"
            tulis_excel(path, isi)
            email = (tgl + timedelta(hours=1, minutes=12)).replace(tzinfo=timezone.utc)
            h = subprocess.run([sys.executable, str(ETL), str(path), format_datetime(email)],
                               cwd=BASE, env=env, capture_output=True, text=True)
            print(f"Laporan {tgl:%d %b}: {len(isi):4} baris -> {'OK' if h.returncode == 0 else 'GAGAL'}")
            if h.returncode != 0:
                print(h.stdout[-800:], h.stderr[-800:])
                sys.exit(1)
    isi_hasil_ai(posts)
    print(f"\nDemo database: {TUJUAN.relative_to(BASE)} ({TUJUAN.stat().st_size / 1e6:.2f} MB, "
          f"{len(posts)} fictional posts)")


if __name__ == "__main__":
    main()
