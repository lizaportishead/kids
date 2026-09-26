import { fetchHtml } from '../lib/http.mjs';
import { normalize } from '../lib/normalize.mjs';
import { stripHtml } from '../lib/text.mjs';

// nashemesto.rs — «Наше Место», детское пространство с двумя филиалами:
// Врачар (Сазонова 88) и Новый Белград (Михаила Пупина 10Z). Сайт на Тильде.
// На сайте это две площадки, поэтому каждое занятие получает place/address
// своего филиала, а source.id — «nashemesto-vracar» / «nashemesto-nb».
//
// Где расписание:
// 1) Внутренние страницы кружков (/chess, /lego, /3d-modelirovanie, /teatrhm) —
//    блок «РАСПИСАНИЕ ЗАНЯТИЙ» в zero-блоке. Его текстовые элементы
//    (`<div class='tn-atom'>`) в исходнике идут в порядке карточек:
//      [заголовок секции] [ГРУППА 6-9 ЛЕТ] ДЕНЬ  ВРЕМЯ[<br>ВРЕМЯ]  ФИЛИАЛ<br>адрес
//    Время «18:00<br>19:00» — это две группы (два начала), «16:30-17:30» — начало
//    и конец. День и время бывают в одном элементе («СУББОТА 17:30-19:00<br>
//    ПОНЕДЕЛЬНИК 18:00-19:30»). Карточку закрывает строка с филиалом.
//    Заголовок секции есть только у LEGO («LEGO WEDO 2.0 И LEGO SPIKE ESSENTIAL»,
//    «LEGO SPIKE PRIME»): возраст и длительность для него берём из текста страницы
//    («10–16 лет — LEGO SPIKE Prime, длительность занятия 90 минут»).
// 2) Главная, «Развлекательные проекты» — карточки t772 (Мафия, DND, Настолки):
//    «ДЛЯ ДЕТЕЙ ОТ 8 ДО 14 ЛЕТ<br>Новый Белград, суббота - 13:30-15:00<br>Врачар, …».
//
// Не берём: вокал и логопеда (ведут на чужие телеграмы, расписания нет), лагеря
// (не разовые занятия). Меню «РАСПИСАНИЕ» (/#rec2168578151) ведёт на удалённый
// блок — отдельной страницы расписания у сайта нет.
//
// Тильда отвечает 403, если дёргать страницы подряд без пауз, — между запросами
// ждём.

const BASE = 'https://nashemesto.rs';
const FETCH_GAP_MS = 2500;

const LOCATIONS = {
  vracar: { re: /^врачар/i, id: 'nashemesto-vracar', place: 'Наше Место (Врачар)', address: 'Сазонова 88, Врачар, Белград' },
  nb: { re: /^нов(ый|и) белград|^нови београд/i, id: 'nashemesto-nb', place: 'Наше Место (Новый Белград)', address: 'Михаила Пупина 10Z, Новый Белград, Белград' }
};

// category: undefined — оставить автоопределение по названию; null — «Другое».
const PAGES = [
  { path: '/chess', title: 'Шахматы', category: 'games' },
  { path: '/lego', title: 'Робототехника LEGO', category: 'robotics' },
  { path: '/3d-modelirovanie', title: '3D-моделирование и печать', category: 'science' },
  // Театральная студия — занятие, а не спектакль (см. category.mjs), поэтому «Другое».
  { path: '/teatrhm', title: 'Театральная студия «Академия ХМ»', category: null }
];

const HOME_TITLES = {
  'мафия': { title: 'Игра «Мафия»', category: 'games' },
  'dnd': { title: 'D&D — настольная ролевая игра', category: 'games', dur: 120 },
  'настольные игры': { title: 'Настольные игры', category: 'games' }
};

const LABELS = { games: 'Шахматы и игры', robotics: 'Робототехника', science: 'Наука и логика' };

const DAYS = ['понедельник', 'вторник', 'сред', 'четверг', 'пятниц', 'суббот', 'воскресень'];
// Слова дней, диапазоны и одиночные времена — по порядку, как в тексте.
const TOKEN_RE = /(понедельник|вторник|сред[аеу]|четверг|пятниц[аеуы]|суббот[аеуы]|воскресень[еяю])|(\d{1,2}[:.]\d{2})\s*[-–—]\s*(\d{1,2}[:.]\d{2})|(\d{1,2}[:.]\d{2})/gi;
const ATOM_RE = /<div[^>]*class=["']tn-atom["'][^>]*>([\s\S]*?)<\/div>/gi;

export async function collectNashemesto(source, now = new Date()) {
  const events = [];
  let first = true;
  const get = async (path) => {
    if (!first) await sleep(FETCH_GAP_MS);
    first = false;
    return fetchHtml(BASE + path, { label: 'nashemesto' });
  };

  for (const page of PAGES) {
    const html = await get(page.path);
    const plain = stripHtml(html).replace(/\s+/g, ' ');
    const pageAge = ageOf(plain);
    const pageDur = (plain.match(/длительность занятия\s*(\d{2,3})\s*минут/i) || [])[1];
    const price = priceOf(plain);
    const desc = metaDescription(html) || page.title;
    const image = ogImage(html);

    for (const card of parseZeroCards(html)) {
      const section = card.section ? sectionInfo(card.section, plain) : null;
      const age = card.age || (section && section.age) || pageAge;
      const title = section && section.name ? page.title + ' ' + section.name : page.title;
      const fullTitle = card.age ? title + ' (' + card.age[0] + '–' + card.age[1] + ' лет)' : title;
      for (const slot of card.slots) {
        const dur = slot.dur || (section && section.dur) || (pageDur ? Number(pageDur) : null);
        events.push(build(source, card.loc, {
          title: fullTitle, desc, wd: [slot.wd], time: slot.time, dur, age, price,
          url: BASE + page.path, image, category: page.category
        }, now));
      }
    }
  }

  const home = await get('/');
  for (const card of parseHomeCards(home)) {
    const meta = HOME_TITLES[card.title.toLowerCase()];
    if (!meta) continue;
    const ageText = card.age ? card.age[0] + '–' + card.age[1] + ' лет' : '';
    const desc = meta.title + ' для детей' + (ageText ? ' ' + ageText : '') + ' в «Наше Место». Запись — в телеграме @NMesto.';
    for (const row of card.rows) {
      for (const slot of row.slots) {
        events.push(build(source, row.loc, {
          title: meta.title, desc, wd: [slot.wd], time: slot.time, dur: slot.dur || meta.dur, age: card.age,
          price: null, url: card.url || source.url, image: null, category: meta.category
        }, now));
      }
    }
  }
  return events.filter(Boolean);
}

function build(source, loc, r, now) {
  const src = { ...source, id: loc.id, place: loc.place, address: loc.address };
  const ev = normalize(src, {
    title: r.title,
    desc: r.desc,
    short: r.desc.slice(0, 150),
    wd: r.wd,
    time: r.time,
    dur: r.dur ? durLabel(r.dur) : null,
    age: r.age,
    price: r.price,
    url: r.url
  }, now);
  if (!ev) return null;
  if (r.category !== undefined) {
    ev.category = r.category;
    ev.categoryLabel = r.category ? LABELS[r.category] : null;
  }
  if (r.image) {
    ev.imageRemote = r.image;
    ev.imageKey = 'nashemesto-' + r.url.split('/').pop();
  }
  return ev;
}

// Zero-блок → карточки { loc, section, age, slots:[{wd,time,dur}] }.
function parseZeroCards(html) {
  const cards = [];
  let section = null;
  let age = null;
  let day = -1;
  let slots = [];
  for (const m of html.matchAll(ATOM_RE)) {
    const lines = stripHtml(m[1]).split('\n').map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
    if (!lines.length) continue;
    const loc = locationOf(lines[0]);
    if (loc) {
      if (slots.length) cards.push({ loc, section, age, slots });
      slots = []; age = null; day = -1;
      continue;
    }
    const text = lines.join(' | ');
    const group = text.match(/^группа\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*лет/i);
    if (group) { age = [Number(group[1]), Number(group[2])]; continue; }
    if (/^расписание/i.test(text)) continue;
    const found = scanSlots(text, day);
    if (found.hadToken) {
      day = found.day;
      slots.push(...found.slots);
    } else if (text.length < 80) {
      section = text; // заголовок секции («LEGO SPIKE PRIME»)
    }
  }
  return cards;
}

// Карточки t772 на главной → { title, url, age, rows:[{ loc, slots }] }.
function parseHomeCards(html) {
  const cards = [];
  const re = /class=["']t-card__title[^"']*["'][^>]*>\s*<a[^>]*href=["']([^"']*)["'][^>]*>([\s\S]*?)<\/a>[\s\S]*?class=["']t-card__descr[^"']*["'][^>]*>([\s\S]*?)<\/div>/gi;
  for (const m of html.matchAll(re)) {
    const title = stripHtml(m[2]).replace(/\s+/g, ' ').trim();
    const lines = stripHtml(m[3]).split('\n').map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
    const card = { title, url: m[1], age: null, rows: [] };
    for (const line of lines) {
      const loc = locationOf(line);
      if (loc) {
        const { slots } = scanSlots(line, -1);
        if (slots.length) card.rows.push({ loc, slots });
      } else if (!card.age) {
        card.age = ageOf(line);
      }
    }
    if (card.rows.length) cards.push(card);
  }
  return cards;
}

// Проходит по тексту слева направо: слово дня задаёт текущий день, каждое
// время после него — отдельный слот. «16:30-17:30» — начало и длительность.
function scanSlots(text, day) {
  const slots = [];
  let hadToken = false;
  for (const m of text.matchAll(TOKEN_RE)) {
    hadToken = true;
    if (m[1]) { day = dayIndex(m[1]); continue; }
    if (day < 0) continue;
    if (m[2]) slots.push({ wd: day, time: normTime(m[2]), dur: diffMinutes(m[2], m[3]) });
    else slots.push({ wd: day, time: normTime(m[4]), dur: null });
  }
  return { slots, day, hadToken };
}

// Секция LEGO: «LEGO WEDO 2.0 И LEGO SPIKE ESSENTIAL» → возраст и длительность
// из строк страницы «5–10 лет — LEGO WeDo 2.0, длительность занятия 60 минут».
function sectionInfo(section, plain) {
  const info = { name: null, age: null, dur: null };
  const kits = [];
  const re = /(\d{1,2})\s*[–—-]\s*(\d{1,2})\s*лет\s*[—–-]\s*(LEGO[A-Za-z0-9. ]+?),\s*длительность занятия\s*(\d{2,3})\s*минут/gi;
  for (const m of plain.matchAll(re)) {
    const kit = m[3].replace(/^LEGO\s*/i, '').trim();
    if (section.toLowerCase().includes(kit.toLowerCase())) kits.push({ kit, min: Number(m[1]), max: Number(m[2]), dur: Number(m[4]) });
  }
  if (kits.length) {
    info.name = kits.map((k) => k.kit).join(' и ');
    info.age = [Math.min(...kits.map((k) => k.min)), Math.max(...kits.map((k) => k.max))];
    info.dur = Math.max(...kits.map((k) => k.dur));
  }
  return info;
}

function locationOf(line) {
  for (const loc of Object.values(LOCATIONS)) if (loc.re.test(line)) return loc;
  return null;
}

function ageOf(text) {
  const m = text.match(/от\s*(\d{1,2})\s*до\s*(\d{1,2})\s*лет/i);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

function priceOf(plain) {
  const m = plain.match(/от\s*(\d{3,5})\s*rsd/i);
  return m ? 'от ' + m[1] + ' RSD' : null;
}

function metaDescription(html) {
  const m = html.match(/<meta[^>]*name=["']description["'][^>]*content=["']([^"']*)["']/i);
  return m ? stripHtml(m[1]).trim() : null;
}

// og:image со static.tildacdn.com — оригинал (до мегабайта), берём уменьшенную
// копию с thb.tildacdn.com, как Тильда сама делает для превью.
function ogImage(html) {
  const m = html.match(/<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']*)["']/i);
  if (!m) return null;
  return m[1].replace(/^https:\/\/static\.tildacdn\.com\/([^/]+)\/([^/]+)$/, 'https://thb.tildacdn.com/$1/-/resize/504x/$2');
}

function dayIndex(word) {
  const w = String(word || '').toLowerCase();
  return DAYS.findIndex((d) => w.startsWith(d));
}

function durLabel(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return m + ' минут';
  const hw = h === 1 ? 'час' : h < 5 ? 'часа' : 'часов';
  return h + ' ' + hw + (m ? ' ' + m + ' минут' : '');
}

const normTime = (t) => {
  const [h, m] = t.replace('.', ':').split(':');
  return h.padStart(2, '0') + ':' + m;
};

const diffMinutes = (a, b) => {
  const [ah, am] = a.replace('.', ':').split(':').map(Number);
  const [bh, bm] = b.replace('.', ':').split(':').map(Number);
  const d = (bh * 60 + bm) - (ah * 60 + am);
  return d > 0 ? d : null;
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
