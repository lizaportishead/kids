import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { parseAge, parsePrice } from '../lib/text.mjs';

// enterspace.rs — статичный Tilda-сайт (без API). Разметка собрана из
// абсолютно позиционированных блоков, поэтому текст со страницы вытаскиваем
// построчно (каждый тег как разделитель), а расписание/цену/возраст — регулярками
// по всему тексту, а не по DOM-структуре: так надёжнее переживает правки вёрстки.
const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
const PAGE_DELAY_MS = 800; // сайт банит IP при слишком частых запросах подряд

export async function collectEnterspace(source, now = new Date()) {
  const listHtml = await fetchText(source.url);
  const slugs = [...new Set([...listHtml.matchAll(/href="https:\/\/enterspace\.rs\/classes\/([a-z0-9-]+)"/g)].map((m) => m[1]))];

  const events = [];
  for (const slug of slugs) {
    await sleep(PAGE_DELAY_MS);
    const url = source.url.replace(/\/classes\/?$/, '') + '/classes/' + slug;
    let html;
    try {
      html = await fetchText(url);
    } catch (err) {
      console.error('enterspace: не удалось загрузить ' + url + ': ' + (err.message || err));
      continue;
    }
    events.push(...parseClassPage(html, url, source, now));
  }
  return events;
}

function parseClassPage(html, url, source, now) {
  const titleTag = decode((html.match(/<title>([^<]*)<\/title>/) || [])[1] || '');
  const metaDesc = decode((html.match(/<meta name="description" content="([^"]*)"/) || [])[1] || '');

  const textLines = html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, '\n')
    .split('\n')
    .map((s) => decode(s.trim()))
    .filter(Boolean);
  const flat = textLines.join(' ');

  const navIdx = textLines.indexOf('Контакты');
  const title = (navIdx !== -1 && textLines[navIdx + 1]) || titleTag.split(/[|—–]/)[0].trim();
  let desc = '';
  if (navIdx !== -1) {
    for (let i = navIdx + 2; i < Math.min(navIdx + 6, textLines.length); i++) {
      if (textLines[i] === 'Когда') break;
      if (textLines[i].length > 40) { desc = textLines[i]; break; }
    }
  }
  desc = desc || metaDesc || title;

  const slots = [...new Set([...flat.matchAll(/([А-Яа-яЁё]+),\s*(\d{1,2}):(\d{2})/g)]
    .map((m) => {
      const wd = WEEKDAYS.indexOf(m[1].toLowerCase());
      if (wd === -1) return null;
      return wd + '|' + m[2].padStart(2, '0') + ':' + m[3];
    })
    .filter(Boolean))].map((s) => { const [wd, time] = s.split('|'); return { wd: Number(wd), time }; });
  if (!slots.length) return [];

  const age = parseAge(metaDesc) || parseAge(flat) || null;

  const single = flat.match(/Разовое занятие\s*—\s*([\d\s]+)\s*RSD/i);
  const sub4 = flat.match(/Абонемент на 4 занятия\s*—\s*([\d\s]+)\s*RSD/i);
  let price = null;
  if (single) price = single[1].replace(/\s/g, '') + ' RSD (разовое)';
  if (sub4) price = (price ? price + ', ' : '') + 'абонемент от ' + sub4[1].replace(/\s/g, '') + ' RSD за 4 занятия';
  price = price || parsePrice(flat);

  const range = metaDesc.match(/(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})/);
  const dur = range ? String((Number(range[3]) * 60 + Number(range[4])) - (Number(range[1]) * 60 + Number(range[2]))) + ' минут' : null;

  const img = html.match(/data-original="(https:\/\/static\.tildacdn\.net\/[^"]+\/IMG_\d+[^"]*\.(?:jpg|jpeg|png))"/i);
  const imageRemote = img ? img[1] : null;

  return slots.map(({ wd, time }) => {
    const raw = { title, desc, short: desc.slice(0, 150), wd: [wd], time, dur, price, age, url };
    const ev = normalize(source, raw, now);
    if (!ev) return null;
    if (imageRemote) { ev.imageRemote = imageRemote; ev.imageKey = 'enter-' + slugFromUrl(url) + '-' + wd; }
    return ev;
  }).filter(Boolean);
}

function slugFromUrl(url) { return url.split('/').pop(); }

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'ru,en;q=0.8', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('enterspace ' + url + ': HTTP ' + res.status);
  return res.text();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const decode = (s) => s.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#0?39;|&apos;/g, "'").replace(/&ndash;/g, '–').replace(/&mdash;/g, '—');
