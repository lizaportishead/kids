import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { matchPrice } from '../lib/text.mjs';

// uvcsumice.rs/event/ — сайт Установе «Вождовачки центар "Шумице"» (районный
// культурный центр в Вождовце) на WordPress + тема OVA-EGOV. Архив /event/
// отдаёт карточки `<div class="ovaev-content content-grid">` в порядке
// убывания даты (сначала самые поздние/будущие), постранично
// (`/event/page/N/`). У каждой карточки: `.date-event` (день/месяц-аббревиатура
// /год — есть всегда) и `.time-event` (точное время `18:30 - 19:30` —
// заполнено только у показов/фильмов, у курсов и кружков пусто).
//
// Центр вперемешку публикует разовые бесплатные показы для детей (спектакли,
// мультфильмы, праздники) и многонедельные бесплатные кружки/курсы (школицы,
// «часови»), которые не подходят разделу «Афиша» — это записи на месяцы, а
// не разовое посещение. Кружки узнаём по слову в заголовке (курс/часови/
// школиц) или по еженедельной периодичности в описании страницы показа.
const BASE = 'https://uvcsumice.rs';
const PAGES = 3;
const PAGE_DELAY_MS = 400;
const ADDRESS = 'Устаничка 125/1, Вождовац, Белград';

// \b тут не годится: в JS граница слова завязана на ASCII \w, а кириллица под
// него не подходит — \bкурс\b на кириллическом тексте не сработает.
const RECURRING_TITLE_RE = /курс|часови|школиц/i;
const RECURRING_DESC_RE = /сваке недеље|сваког (?:понедељка|уторка|среде|четвртка|петка|суботе|недеље)|понедељком|уторком|средом|четвртком|петком|суботом|недељом|у трајању од/i;

export async function collectUvcsumice(source, now = new Date()) {
  const today = iso(now);
  const cards = [];
  for (let page = 1; page <= PAGES; page++) {
    const url = page === 1 ? source.url : BASE + '/event/page/' + page + '/';
    const html = await fetchText(url).catch((err) => {
      console.error('uvcsumice: страница ' + page + ' не загрузилась: ' + (err.message || err));
      return null;
    });
    if (!html) break;
    for (const block of html.split('ovaev-content content-grid').slice(1)) {
      const card = parseCard(block);
      if (card) cards.push(card);
    }
    if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);
  }

  const events = [];
  for (const card of cards) {
    if (card.date < today) continue;
    if (RECURRING_TITLE_RE.test(card.rawTitle)) continue;

    const detail = await fetchDetail(card.url).catch((err) => {
      console.error('uvcsumice: страница «' + card.rawTitle + '» не загрузилась: ' + (err.message || err));
      return null;
    });
    if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);
    if (detail && RECURRING_DESC_RE.test(detail.desc)) continue;

    const title = pickTitle(card.rawTitle, detail && detail.desc);
    const desc = (detail && detail.desc) || title;
    const time = card.time || (detail && detail.time) || parseTimeFromText(desc);
    const priceMatch = matchPrice(desc);

    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: card.date,
      time,
      dur: card.dur,
      age: null,
      price: priceMatch ? priceMatch.price : 'бесплатно',
      place: source.place || source.name,
      address: ADDRESS,
      url: card.url
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    const image = (detail && detail.image) || card.image;
    if (image) {
      ev.imageRemote = image;
      ev.imageKey = 'uvcsumice-' + slugOf(title);
    }
    events.push(ev);
  }
  return events;
}

// Одна карточка списка: дата из `.date-event` (день/аббревиатура месяца/год),
// ссылка и заголовок из `.event_title`, картинка из `.event-thumbnail`, время
// (если задано) из `.time-date-child` — там же, через тире, конец показа,
// по которому считаем длительность.
function parseCard(block) {
  const mDay = block.match(/date second_font">\s*(\d+)/);
  const mMonth = block.match(/<span class="month">\s*([^\s<]+)/);
  const mYear = block.match(/<span class="year">\s*(\d+)/);
  if (!mDay || !mMonth || !mYear) return null;
  const month = MONTHS[mMonth[1].toLowerCase()];
  if (!month) return null;

  const mLink = block.match(/event_title">\s*<a href="([^"]+)"[^>]*>\s*([\s\S]*?)\s*<\/a>/);
  if (!mLink) return null;

  const mImg = block.match(/event-thumbnail">[\s\S]*?src="([^"]+)"/);
  const mTime = block.match(/time-date-child">[\s\S]*?<span>\s*(\d{1,2}:\d{2})[^<]*<\/span>\s*(?:<span>\s*(\d{1,2}:\d{2})\s*<\/span>)?/);

  return {
    date: mYear[1] + '-' + String(month).padStart(2, '0') + '-' + mDay[1].padStart(2, '0'),
    url: mLink[1],
    rawTitle: decode(mLink[2]).trim(),
    image: mImg ? mImg[1] : null,
    time: mTime ? mTime[1] : null,
    dur: mTime && mTime[2] ? diffMinutes(mTime[1], mTime[2]) : null
  };
}

const MONTHS = { јан: 1, феб: 2, мар: 3, апр: 4, мај: 5, јун: 6, јул: 7, авг: 8, сеп: 9, окт: 10, нов: 11, дец: 12 };

function diffMinutes(from, to) {
  const [h1, m1] = from.split(':').map(Number);
  const [h2, m2] = to.split(':').map(Number);
  const diff = (h2 * 60 + m2) - (h1 * 60 + m1);
  return diff > 0 && diff < 400 ? diff + ' минут' : null;
}

// У части карточек заголовок — общая фраза «Бесплатна представа за децу у
// „Шумицама“» без названия спектакля; настоящее название спрятано в тексте
// описания в кавычках. Берём первый кавычечный фрагмент, не совпадающий с
// самоупоминанием площадки.
function pickTitle(rawTitle, desc) {
  const fromQuotes = (text) => {
    const quotes = [...String(text || '').matchAll(/„([^“]+)“/g)].map((m) => m[1]);
    return quotes.find((q) => !/шумиц/i.test(q)) || null;
  };
  const specific = fromQuotes(rawTitle) || fromQuotes(desc);
  return sentenceCase(specific || rawTitle);
}

// --- страница показа --------------------------------------------------------

async function fetchDetail(url) {
  const html = await fetchText(url);

  const mBody = html.match(/<div class="single_event">[\s\S]*?<div class="content">([\s\S]*?)<\/div>\s*\n*\s*<!-- end tab-location/);
  const desc = mBody
    ? decode(mBody[1].replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim()
    : '';

  const mTime = html.match(/wrap-time[\s\S]*?general-content">\s*(\d{1,2}:\d{2})/);
  const og = (html.match(/<meta property="og:image" content="([^"]+)"/) || [])[1] || '';

  return {
    desc,
    time: mTime ? mTime[1] : null,
    image: og && /^https?:\/\//.test(og) ? og : null
  };
}

// У части показов без виджета точного времени (напр. праздники) начало есть
// в тексте анонса: «са почетком у 18.30 часова» / «у 11 часова».
function parseTimeFromText(text) {
  const m = String(text || '').match(/почетком у\s*(\d{1,2})(?:[.:](\d{2}))?\s*(?:ч\b|часа|часова)/i);
  return m ? m[1].padStart(2, '0') + ':' + (m[2] || '00') : null;
}

// --- утилиты -----------------------------------------------------------------

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'sr,ru;q=0.8,en;q=0.6', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('uvcsumice ' + url + ': HTTP ' + res.status);
  return res.text();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

function sentenceCase(s) {
  const t = String(s).toLowerCase();
  return t.replace(/\p{L}/u, (c) => c.toUpperCase());
}

function slugOf(title) {
  const map = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', ђ: 'dj', е: 'e', ж: 'zh', з: 'z', и: 'i', ј: 'j', к: 'k', л: 'l', љ: 'lj', м: 'm', н: 'n', њ: 'nj', о: 'o', п: 'p', р: 'r', с: 's', т: 't', ћ: 'c', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', џ: 'dz', ш: 'sh' };
  return String(title).toLowerCase().replace(/[Ѐ-ӿ]/g, (c) => (c in map ? map[c] : c))
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;|&#0?34;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8222;|&bdquo;/g, '„')
  .replace(/&#8220;|&#8221;|&ldquo;|&rdquo;/g, '“')
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;|&#8211;/g, '–')
  .replace(/&mdash;/g, '—');
