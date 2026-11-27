/**
 * PENGIRIM LAPORAN EMPLIFI -> GITHUB
 *
 * Dipasang di script.google.com dengan akun Gmail yang menerima laporan Emplifi.
 * Setiap jam: mencari email laporan FEED Emplifi yang belum dikirim, lalu
 * mengirim LINK DOWNLOAD-nya ke GitHub agar diproses otomatis.
 * Isi email dan akses Gmail TIDAK pernah dikirim ke mana pun.
 *
 * Pengaturan (Project Settings -> Script Properties):
 *   GITHUB_TOKEN = token GitHub "emplifi-pengirim"
 *   GITHUB_REPO  = username/emplifi-dashboard
 */

const PENGIRIM = 'hello@emplifi.io';
const HOST_LAPORAN = 'sbks-reporting.svc.emplifi.io';
const HARI_DICARI = 7;

function kirimLaporanBaru() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');
  const repo = props.getProperty('GITHUB_REPO');
  if (!token || !repo) {
    throw new Error('Isi GITHUB_TOKEN dan GITHUB_REPO di Project Settings -> Script Properties.');
  }

  const sudah = JSON.parse(props.getProperty('SUDAH_DIKIRIM') || '[]');
  const baru = [];
  GmailApp.search('from:' + PENGIRIM + ' newer_than:' + HARI_DICARI + 'd', 0, 50)
    .forEach(function (thread) {
      thread.getMessages().forEach(function (pesan) {
        if (pesan.getFrom().toLowerCase().indexOf(PENGIRIM) === -1) return;
        if (pesan.getSubject().toLowerCase().indexOf('feed') === -1) return;
        if (sudah.indexOf(pesan.getId()) !== -1) return;
        baru.push(pesan);
      });
    });

  // Terlama dulu, agar urutan versi data benar.
  baru.sort(function (a, b) { return a.getDate() - b.getDate(); });

  let jumlahKirim = 0;
  baru.forEach(function (pesan) {
    const link = cariLinkDownload(pesan.getBody());
    if (!link) {
      console.warn('Link "Download report" tidak ditemukan: ' + pesan.getSubject());
      sudah.push(pesan.getId());
      return;
    }
    const respon = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
      method: 'post',
      contentType: 'application/json',
      muteHttpExceptions: true,
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify({
        event_type: 'laporan_emplifi',
        client_payload: {
          link: link,
          tanggal: pesan.getDate().toUTCString(),
          id: pesan.getId(),
          subjek: pesan.getSubject()
        }
      })
    });
    if (respon.getResponseCode() !== 204) {
      throw new Error('GitHub menolak (' + respon.getResponseCode() + '): ' + respon.getContentText());
    }
    console.log('Dikirim ke GitHub: ' + pesan.getSubject() + ' (' + pesan.getDate() + ')');
    jumlahKirim++;
    sudah.push(pesan.getId());
  });

  props.setProperty('SUDAH_DIKIRIM', JSON.stringify(sudah.slice(-300)));
  console.log(jumlahKirim ? jumlahKirim + ' laporan baru dikirim.' : 'Tidak ada laporan baru.');
}

function cariLinkDownload(html) {
  const pola = /<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let cocok;
  while ((cocok = pola.exec(html)) !== null) {
    const teks = cocok[2].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
    if (teks.indexOf('download report') === -1) continue;
    const url = cocok[1].replace(/&amp;/g, '&').trim();
    const host = (url.match(/^https:\/\/([^\/?#:]+)/i) || [])[1];
    if (host && host.toLowerCase() === HOST_LAPORAN) return url;
  }
  return null;
}

/** Jalankan SEKALI untuk memasang jadwal setiap jam. */
function pasangJadwal() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'kirimLaporanBaru') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('kirimLaporanBaru').timeBased().everyHours(1).create();
  console.log('Jadwal terpasang: setiap jam.');
}
