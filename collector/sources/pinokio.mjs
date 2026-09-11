import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { iso } from '../lib/text.mjs';

// pinokio.rs/repertoar/ — сайт «Позориште лутака Пинокио» (театр кукол в Новом
// Белграде) на WordPress + Elementor. Репертуар — вертикальный список из
// повторяющихся секций: у каждого спектакля своя пара колонок
// `.expire-date` (h2 «12.09.») и `.expire-time` (p «12:00»), следом секция
// с названием спектакля и секция с иконочным списком «возраст + длительность»
// и кнопкой «КУПИ КАРТУ».
//
// Только разовые датированные показы — ровно то, что нужно разделу «Афиша»
// (date задан, wd нет). Год в дате не указан — достраиваем ближайший будущий.
//
// Со страницы каждого спектакля (URL строим из названия — слаг у WordPress
// кириллический) подтягиваем аккуратный регистр названия из <title>, синопсис
// после заголовка «Опис представе» и афишу (og:image).
const PAGE_DELAY_MS = 400;

export async function collectPinokio(source, now = new Date()) {
  const html = await fetchText(source.url);

  const events = [];
  for (const block of html.split('expire-date').slice(1)) {
    const slot = parseBlock(block);
    if (!slot) continue;

    const detail = await fetchDetail(slot.title).catch((err) => {
      console.error('pinokio: страница «' + slot.title + '» не загрузилась: ' + (err.message || err));
      return null;
    });
    if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);

    const title = (detail && detail.title) || titleCase(slot.title);
    const desc = (detail && detail.desc) || title;
    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: resolveDate(slot.day, slot.month, now),
      time: slot.time,
      dur: slot.dur,
      age: slot.age,
      price: null,
      url: (detail && detail.url) || source.url
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    if (detail && detail.image) {
      ev.imageRemote = detail.image;
      ev.imageKey = 'pinokio-' + slugOf(title);
    }
    events.push(ev);
  }
  return events;
}

// Блок одного спектакля: дата в первом <h2>, время в колонке `.expire-time`,
// название — первый заголовок-<p>, не совпадающий со временем; возраст и
// длительность — тексты иконочного списка («4+ год.», «45'»).
function parseBlock(block) {
  const mDate = block.match(/>(\d{1,2})\.(\d{1,2})\.\s*</);
  if (!mDate) return null;
  const mTime = block.match(/expire-time[\s\S]*?elementor-heading-title[^>]*>\s*(\d{1,2}:\d{2})/);

  const headings = [...block.matchAll(/elementor-heading-title elementor-size-default">([^<]+?)<\/p>/g)]
    .map((m) => decode(m[1]).trim())
    .filter(Boolean);
  const title = headings.find((h) => !/^\d{1,2}:\d{2}$/.test(h));
  if (!title || title.length < 3) return null;

  const listTexts = [...block.matchAll(/elementor-icon-list-text">([^<]+)</g)].map((m) => decode(m[1]).trim());
  const ageText = listTexts.find((t) => /\d/.test(t) && /год|лет|\+|бебе/i.test(t)) || listTexts[0] || '';
  const durText = listTexts.find((t) => /['`′’]|мин/.test(t)) || '';

  return {
    day: Number(mDate[1]),
    month: Number(mDate[2]),
    time: mTime ? mTime[1].padStart(5, '0') : '10:00',
    title,
    age: parseAgeText(ageText),
    dur: parseDurText(durText)
  };
}

// «4+ год.» → [4, 16]; «5-10 год.» → [5, 10]; «Представа за бебе / 0+ год.» → [0, 16].
function parseAgeText(text) {
  const s = String(text || '');
  let m = s.match(/(\d{1,2})\s*[-–—]\s*(\d{1,2})/);
  if (m) return [Number(m[1]), Number(m[2])];
  m = s.match(/(\d{1,2})\s*\+/);
  if (m) return [Number(m[1]), 16];
  if (/бебе/i.test(s)) return [0, 3];
  return null;
}

// «45'» / «45′» → «45 минут»; «60'» → «60 минут» (normalize сам не трогает).
function parseDurText(text) {
  const m = String(text || '').match(/(\d{1,3})/);
  return m ? m[1] + ' минут' : null;
}

// Год в репертуаре не пишут — берём ближайшую будущую дату (как resolveYear
// в lib/text.mjs: прошедшее максимум на 3 дня считаем этим годом).
function resolveDate(day, month, now) {
  const y = now.getFullYear();
  const cand = new Date(y, month - 1, day);
  const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 3);
  return iso(cand < cutoff ? new Date(y + 1, month - 1, day) : cand);
}

// --- страница спектакля ----------------------------------------------------

async function fetchDetail(rawTitle) {
  const url = 'https://pinokio.rs/' + encodeURIComponent(rawTitle.trim().toLowerCase().replace(/\s+/g, '-')) + '/';
  const html = await fetchText(url);

  const titleTag = decode((html.match(/<title>([^<]*)<\/title>/) || [])[1] || '')
    .split(/\s+[-–—]\s+/)[0].trim();

  // Синопсис — первый <p> после заголовка «Опис представе». На сайте два
  // шаблона страницы спектакля (<h3>…</h3> и <h2><span>…</span></h2> + врезка
  // Drupal-поля), поэтому до <p> допускаем немного произвольной разметки.
  let descr = (html.match(/Опис представе[\s\S]{0,320}?<p[^>]*>([\s\S]*?)<\/p>/) || [])[1] || '';
  descr = decode(descr.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
  if (descr.length < 40) {
    descr = decode((html.match(/<meta name="description" content="([^"]*)"/) || [])[1] || '').trim();
  }

  const og = (html.match(/<meta property="og:image" content="([^"]+)"/) || [])[1] || '';

  return {
    url,
    title: titleTag && titleTag.length >= 3 ? titleTag : null,
    desc: descr && descr.length >= 40 ? descr : null,
    image: og && /^https?:\/\//.test(og) ? og : null
  };
}

// --- утилиты -------------------------------------------------------------------

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'sr,ru;q=0.8,en;q=0.6', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('pinokio ' + url + ': HTTP ' + res.status);
  return res.text();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// «ЦРВЕНКАПА» → «Црвенкапа» (запасной вариант, если страница спектакля не открылась).
function titleCase(s) {
  return String(s).toLowerCase().replace(/(^|[\s(«"„-])([\p{L}])/gu, (_, p, c) => p + c.toUpperCase());
}

function slugOf(title) {
  const map = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', ђ: 'dj', е: 'e', ж: 'zh', з: 'z', и: 'i', ј: 'j', к: 'k', л: 'l', љ: 'lj', м: 'm', н: 'n', њ: 'nj', о: 'o', п: 'p', р: 'r', с: 's', т: 't', ћ: 'c', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', џ: 'dz', ш: 'sh', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya', ё: 'e' };
  return String(title).toLowerCase().replace(/[Ѐ-ӿ]/g, (c) => (c in map ? map[c] : c))
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&ldquo;|&rdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;/g, '–')
  .replace(/&mdash;/g, '—')
  .replace(/&#8211;/g, '–');
