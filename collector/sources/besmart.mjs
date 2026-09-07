import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { parseAge, stripHtml } from '../lib/text.mjs';

// besmartserbia.com/lessons — Tilda-каталог «Список занятий» (блок t-catalog).
// Карточки подгружаются скриптом из store-API Тильды, поэтому парсим не HTML
// страницы, а JSON фида: /api/getproductslist/ со storepartuid и recid каталога
// (значения — в inline-скрипте t_catalog_init на странице, ключи options
// `storepart` и `recid`). На store.tildaapi.com Тильда отвечает
// {"redirectto":"one"} — тогда меняем корневую зону эндпоинта
// (store.tildaapi.com → store.tildaapi.one) и повторяем запрос.
//
// У каждого продукта описание (descr) — HTML с преамбулой
// «Возраст: … Посещение: … Язык: … Расписание: <день(и)>, ЧЧ:ММ [- ЧЧ:ММ]»,
// затем текст курса после <br><br>. Возраст и расписание вытаскиваем из
// преамбулы регулярками, тело — в описание. Занятия почти все идут по
// абонементу еженедельно, поэтому отдаём их как события с массивом wd
// (так же, как Enter, MathLine, ЛаборатоРиЯ). Дубли-черновики («Copy: …»)
// и продлёнку пропускаем.

const STORE_UID = '464557862312';
const REC_ID = '2695793803';
const DEFAULT_ENDPOINT = 'store.tildaapi.com';

const DAY = '(?:понедельник|вторник|среда|среду|четверг|пятниц[ауеы]|суббот[ауеы]|воскресень[ея])';
const JOIN = '(?:\\s+и\\s+|\\s*[,/]\\s*)';
const SLOT_RE = new RegExp('(' + DAY + '(?:' + JOIN + DAY + ')*)\\s*,?\\s*(\\d{1,2}:\\d{2})(?:\\s*[-–—]\\s*(\\d{1,2}:\\d{2}))?', 'gi');
const DAY_RE = new RegExp(DAY, 'gi');
const EVERY_RE = new RegExp('кажд[а-яё]*\\s+(' + DAY + ')', 'i');
// «Copy: …» — черновик-дубль в Тильде; продлёнка — это отдельная площадка.
const SKIP_TITLE_RE = /^\s*copy\b|^\s*копия\b|продл[её]нк/i;

export async function collectBesmart(source, now = new Date()) {
  const feed = await fetchFeed(DEFAULT_ENDPOINT);
  const products = Array.isArray(feed && feed.products) ? feed.products : [];

  const events = [];
  for (const p of products) {
    const title = decode((p.title || '').trim());
    if (title.length < 6 || SKIP_TITLE_RE.test(title)) continue;

    const descrHtml = String(p.descr || '');
    const schedText = decode((descrHtml.match(/Расписание:\s*<\/strong>\s*<strong[^>]*>([^<]*)<\/strong>/i) || [])[1] || '');
    const plain = stripHtml(descrHtml).replace(/\s+/g, ' ').trim();

    const slots = parseSchedule(schedText, plain);
    if (!slots.length) continue; // нет разобранного дня недели («набор с января», «каждый день в будни»)

    const bodyHtml = descrHtml.split(/<br\s*\/?>\s*<br\s*\/?>/i).slice(1).join(' ');
    const desc = (stripHtml(bodyHtml) || title).replace(/\s+/g, ' ').trim();
    const ageText = decode((descrHtml.match(/Возраст:\s*<\/strong>\s*<strong[^>]*>([^<]*)<\/strong>/i) || [])[1] || '');
    const age = parseAge(ageText) || parseAge(title) || null;
    const price = formatPrice(p.price);
    const url = p.url || source.url;

    for (const slot of slots) {
      const raw = {
        title,
        desc,
        short: desc.slice(0, 150),
        wd: slot.wd,
        time: slot.time || '17:00',
        dur: slot.dur ? slot.dur + ' минут' : null,
        age,
        price,
        url
      };
      const ev = normalize(source, raw, now);
      if (ev) events.push(ev);
    }
  }
  return events;
}

// Строка расписания: «понедельник и четверг 17:00», «суббота, 11:30 - 13:00»,
// «четверг 18:00 (начинающие), суббота 17:00 (продолжающие)» → список слотов
// { wd:[0..6], time, dur }. Несколько дней с одним временем склеиваются в
// один слот с массивом wd; разные пары день+время дают отдельные слоты.
function parseSchedule(sched, plain) {
  const slots = [];
  for (const m of (sched || '').matchAll(SLOT_RE)) {
    const wd = uniqSorted((m[1].match(DAY_RE) || []).map(dayIndex).filter((i) => i >= 0));
    if (!wd.length) continue;
    slots.push({ wd, time: normTime(m[2]), dur: m[3] ? diffMinutes(m[2], m[3]) : null });
  }
  if (!slots.length) {
    // «каждую субботу» без времени в самой строке — время/длительность ищем
    // в тексте курса («…каждую субботу с 10:00 до 14:00»).
    const every = (sched || '').match(EVERY_RE);
    const i = every ? dayIndex(every[1]) : -1;
    if (i >= 0) {
      const rng = plain.match(/с\s*(\d{1,2}:\d{2})\s*(?:до|[-–—])\s*(\d{1,2}:\d{2})/i);
      const one = plain.match(/(\d{1,2}:\d{2})/);
      slots.push({
        wd: [i],
        time: rng ? normTime(rng[1]) : (one ? normTime(one[1]) : null),
        dur: rng ? diffMinutes(rng[1], rng[2]) : null
      });
    }
  }
  return slots;
}

function dayIndex(word) {
  const w = String(word || '').toLowerCase();
  if (w.startsWith('понедельник')) return 0;
  if (w.startsWith('вторник')) return 1;
  if (w.startsWith('сред')) return 2;
  if (w.startsWith('четверг')) return 3;
  if (w.startsWith('пятниц')) return 4;
  if (w.startsWith('суббот')) return 5;
  if (w.startsWith('воскресень')) return 6;
  return -1;
}

async function fetchFeed(endpoint, depth = 0) {
  const qs = new URLSearchParams({
    storepartuid: STORE_UID,
    recid: REC_ID,
    c: String(Date.now()),
    getallparts: 'true',
    getoptions: 'true',
    slice: '1',
    size: '200'
  });
  const url = 'https://' + endpoint + '/api/getproductslist/?' + qs.toString();
  const res = await fetch(url, {
    headers: { 'user-agent': UA, accept: 'application/json,text/plain,*/*', referer: 'https://besmartserbia.com/' }
  });
  if (!res.ok) throw new Error('besmart ' + endpoint + ': HTTP ' + res.status);
  const data = await res.json();
  // Тильда просит уйти в другую корневую зону (com → one): подменяем последний
  // сегмент хоста и повторяем (не больше двух раз, чтобы не зациклиться).
  if (data && data.redirectto && depth < 2) {
    const parts = endpoint.split('.');
    parts[parts.length - 1] = String(data.redirectto);
    return fetchFeed(parts.join('.'), depth + 1);
  }
  return data;
}

function formatPrice(v) {
  const n = Math.round(Number(v));
  return Number.isFinite(n) && n > 0 ? n + ' RSD' : null;
}

const normTime = (t) => {
  const [h, m] = t.split(':');
  return h.padStart(2, '0') + ':' + m;
};

const diffMinutes = (a, b) => {
  const [ah, am] = a.split(':').map(Number);
  const [bh, bm] = b.split(':').map(Number);
  const d = (bh * 60 + bm) - (ah * 60 + am);
  return d > 0 ? d : null;
};

const uniqSorted = (arr) => [...new Set(arr)].sort((a, b) => a - b);

const decode = (s) => String(s || '')
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&ndash;/g, '–')
  .replace(/&mdash;/g, '—')
  .replace(/\s+/g, ' ')
  .trim();
