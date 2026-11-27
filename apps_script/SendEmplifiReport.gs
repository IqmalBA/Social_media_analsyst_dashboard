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

const SENDER = 'hello@emplifi.io';
const REPORT_HOST = 'sbks-reporting.svc.emplifi.io';
const DAYS_TO_SEARCH = 7;

function sendNewReports() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');
  const repo = props.getProperty('GITHUB_REPO');
  if (!token || !repo) {
    throw new Error('Isi GITHUB_TOKEN dan GITHUB_REPO di Project Settings -> Script Properties.');
  }

  const alreadySent = JSON.parse(props.getProperty('SUDAH_DIKIRIM') || '[]');
  const newMessages = [];
  GmailApp.search('from:' + SENDER + ' newer_than:' + DAYS_TO_SEARCH + 'd', 0, 50)
    .forEach(function (thread) {
      thread.getMessages().forEach(function (message) {
        if (message.getFrom().toLowerCase().indexOf(SENDER) === -1) return;
        if (message.getSubject().toLowerCase().indexOf('feed') === -1) return;
        if (alreadySent.indexOf(message.getId()) !== -1) return;
        newMessages.push(message);
      });
    });

  // Terlama dulu, agar urutan versi data benar.
  newMessages.sort(function (a, b) { return a.getDate() - b.getDate(); });

  let sentCount = 0;
  newMessages.forEach(function (message) {
    const link = findDownloadLink(message.getBody());
    if (!link) {
      console.warn('Link "Download report" tidak ditemukan: ' + message.getSubject());
      alreadySent.push(message.getId());
      return;
    }
    const response = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
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
          tanggal: message.getDate().toUTCString(),
          id: message.getId(),
          subjek: message.getSubject()
        }
      })
    });
    if (response.getResponseCode() !== 204) {
      throw new Error('GitHub menolak (' + response.getResponseCode() + '): ' + response.getContentText());
    }
    console.log('Dikirim ke GitHub: ' + message.getSubject() + ' (' + message.getDate() + ')');
    sentCount++;
    alreadySent.push(message.getId());
  });

  props.setProperty('SUDAH_DIKIRIM', JSON.stringify(alreadySent.slice(-300)));
  console.log(sentCount ? sentCount + ' laporan newMessages dikirim.' : 'Tidak ada laporan newMessages.');
}

function findDownloadLink(html) {
  const pattern = /<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = pattern.exec(html)) !== null) {
    const text = match[2].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
    if (text.indexOf('download report') === -1) continue;
    const url = match[1].replace(/&amp;/g, '&').trim();
    const host = (url.match(/^https:\/\/([^\/?#:]+)/i) || [])[1];
    if (host && host.toLowerCase() === REPORT_HOST) return url;
  }
  return null;
}

/** Jalankan SEKALI untuk memasang jadwal setiap jam. */
function installSchedule() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'sendNewReports') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('sendNewReports').timeBased().everyHours(1).create();
  console.log('Jadwal terpasang: setiap jam.');
}
