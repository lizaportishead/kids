import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { iso, addDays } from '../lib/text.mjs';

// pozoristancepuz.com — «Позориште Пуж» (Белград, Радослава Грујића 21), детский
// театр Бранка Коцкице. Сайт на самописной CMS, сербская кириллица; отдельной
// страницы репертуара нет — расписание живёт на главной, в блоке `#repertoar`:
// «Овог викенда» и «Идућег викенда», т.е. ближайшие ~две недели.
//
// Каждый показ — `<article class='this_week|next_week'>`: `.time_up` «Субота 19.
// септембар» (года нет), `<h3><a href='slug'>НАЗВАНИЕ</a></h3>`, `.time_down`
// «у 12 часова» или «у 12 и 17 часова» (тогда два показа за день).
//
// Со страницы спектакля (`/predstave/<slug>`) берём аккуратное название, «О чему
// се ради» и фото из галереи (если есть; иначе — виньетка из «Ове сезоне»). Ссылку
// на билет берём с puz.tickets.rs: его список серверный, у каждого показа своя
// `/event/<slug>_<id>`, сопоставляем по дате и часу; нет совпадения — ссылка на
// страницу спектакля.
//
// Возраст сайт не публикует («Све наше представе су искључиво за децу — и одрасле»),
// поэтому по умолчанию 3+; у «Комшинице Јуце и Ромеа» указано «5-12 година».
// Цена и длительность не публикуются. Только разовые датированные показы.
const BASE = 'https://www.pozoristancepuz.com';
const TICKETS = 'https://puz.tickets.rs';
const PAGE_DELAY_MS = 400;

const MONTHS_CYR = ['јануар', 'фебруар', 'март', 'април', 'мај', 'јун', 'јул', 'август', 'септембар', 'октобар', 'новембар', 'децембар'];
const MONTHS_LAT = ['januar', 'februar', 'mart', 'april', 'maj', 'jun', 'jul', 'avgust', 'septembar', 'oktobar', 'novembar', 'decembar'];

export async function collectPuz(source, now = new Date()) {
  const today = iso(now);
  const home = await fetchText(BASE + '/');
  const block = (home.match(/<div id='repertoar'[\s\S]*?<\/section>\s*<\/div>/) || [home])[0];

  const rows = [];
  for (const article of block.split(/<article class='(?:this|next)_week/).slice(1)) {
    for (const row of parseArticle(article.split('</article>')[0], now)) {
      if (row.date >= today) rows.push(row);
    }
  }
  if (!rows.length) return [];

  const tickets = await fetchTickets().catch((err) => {
    console.error('puz: список puz.tickets.rs не загрузился: ' + (err.message || err));
    return new Map();
  });
  const vignettes = await fetchVignettes().catch(() => new Map());

  const details = new Map();
  const events = [];
  for (const row of rows) {
    if (!details.has(row.slug)) {
      details.set(row.slug, await fetchDetail(row.slug).catch((err) => {
        console.error('puz: страница «' + row.title + '» не загрузилась: ' + (err.message || err));
        return null;
      }));
      if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);
    }
    const detail = details.get(row.slug);

    const title = (detail && detail.title) || sentenceCase(row.title);
    const desc = (detail && detail.desc) || title;
    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: row.date,
      time: row.time,
      age: (detail && detail.age) || [3, 16],
      price: null,
      url: tickets.get(row.date + ' ' + row.time) || BASE + '/predstave/' + row.slug
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    const image = (detail && detail.image) || vignettes.get(row.slug);
    if (image) {
      ev.imageRemote = image;
      ev.imageKey = 'puz-' + row.slug;
    }
    events.push(ev);
  }
  return events;
}

// Один блок дня → 1–2 показа. «Субота 19. септембар» + «у 12 и 17 часова».
function parseArticle(article, now) {
  const up = decode((article.match(/class='time_up'>([^<]*)</) || [])[1] || '');
  const mDate = up.toLowerCase().match(/(\d{1,2})\.?\s+([а-я]+)/);
  const mTitle = article.match(/<h3><a href='([^']+)'[^>]*>([^<]+)<\/a><\/h3>/);
  if (!mDate || !mTitle) return [];
  const mi = MONTHS_CYR.findIndex((m) => mDate[2].startsWith(m.slice(0, 3)));
  if (mi === -1) return [];
  const date = resolveYear(mi, Number(mDate[1]), now);

  const down = decode((article.match(/class='time_down'>([^<]*)</) || [])[1] || '');
  const times = [...down.replace(/\s+часова?.*$/i, '').matchAll(/(\d{1,2})(?:[:.](\d{2}))?/g)]
    .map((m) => String(m[1]).padStart(2, '0') + ':' + (m[2] || '00'));

  const slug = mTitle[1].replace(/^.*\/predstave\//, '').replace(/[?#].*$/, '');
  return times.map((time) => ({ date, time, slug, title: decode(mTitle[2]).trim() }));
}

// Года в датах нет: прошедшую (больше чем на 3 дня) считаем следующим годом —
// как resolveYear в lib/text.mjs.
function resolveYear(monthIndex, day, now) {
  const thisYear = new Date(now.getFullYear(), monthIndex, day);
  if (thisYear < addDays(now, -3)) return iso(new Date(now.getFullYear() + 1, monthIndex, day));
  return iso(thisYear);
}

// --- страница спектакля ----------------------------------------------------

async function fetchDetail(slug) {
  const html = await fetchText(BASE + '/predstave/' + slug);
  const main = (html.match(/<main[\s\S]*?<\/main>/) || [''])[0];

  // Название: текст `<h1>` либо alt картинки-заголовка (у части спектаклей
  // заголовок — PNG). «У изградњи...» — заглушка недоделанной страницы.
  const h1 = (main.match(/<h1[^>]*>([\s\S]*?)<\/h1>/) || [])[1] || '';
  let title = clean(h1.replace(/<img[^>]*>/g, ''));
  if (!title) title = decode((h1.match(/alt='([^']*)'/) || [])[1] || '').trim();
  if (/изградњ/i.test(title)) title = '';

  const body = (main.match(/<h3>О чему се ради<\/h3><div class='tsize'>([\s\S]*?)<\/div>/) || [])[1] || '';
  const desc = clean(body);

  // Возраст — только если на странице указан числом («5-12 година»); общая
  // фраза «за децу и одрасле» его не задаёт.
  const uzrast = clean((main.match(/id='p2_uzrast_text'[^>]*>([\s\S]*?)<\/p>/) || [])[1] || '');
  const mAge = uzrast.match(/(\d{1,2})\s*[-–—]\s*(\d{1,2})/);
  const age = mAge ? [Number(mAge[1]), Number(mAge[2])] : null;

  // Фото — первый кадр галереи; у части спектаклей есть уменьшенная копия «(Medium)».
  const gal = (main.match(/class='p_g_small' src='([^']+)'/) || [])[1] || null;
  return { title, desc, age, image: gal ? absolute(gal) : null };
}

// Виньетки (рисунки Ивы Ћирић) со страницы «Ове сезоне»: запасная обложка для
// спектаклей без галереи.
async function fetchVignettes() {
  const html = await fetchText(BASE + '/predstave/ove-sezone');
  const map = new Map();
  for (const m of html.matchAll(/<article id='predstava-([^']+)'[^>]*>\s*<a[^>]*><img[^>]*src='([^']+)'/g)) {
    map.set(m[1], absolute(m[2]));
  }
  return map;
}

// --- puz.tickets.rs --------------------------------------------------------

// Карточка: `<a href="/event/crvenkapa_27819">…<div class="date-time"> nedelja
// 27.septembar 12h </div>…`. Возвращает «YYYY-MM-DD HH:MM» → ссылка на билеты.
async function fetchTickets() {
  const now = new Date();
  const html = await fetchText(TICKETS + '/venue/pozoriste_puz_112');
  const map = new Map();
  for (const m of html.matchAll(/<a[^>]*href="(\/event\/[^"]+)"[\s\S]*?class="date-time[^"]*">\s*([^<]*?)\s*</g)) {
    const d = m[2].toLowerCase().match(/(\d{1,2})\.\s*([a-z]+)\s+(\d{1,2})(?::(\d{2}))?\s*h/);
    if (!d) continue;
    const mi = MONTHS_LAT.findIndex((x) => d[2].startsWith(x.slice(0, 3)));
    if (mi === -1) continue;
    map.set(resolveYear(mi, Number(d[1]), now) + ' ' + String(d[3]).padStart(2, '0') + ':' + (d[4] || '00'), TICKETS + m[1]);
  }
  return map;
}

// --- утилиты -----------------------------------------------------------------

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'sr,ru;q=0.8,en;q=0.6', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('puz ' + url + ': HTTP ' + res.status);
  return res.text();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// `//www…/public/img/x.jpg` → https://www…; пробелы в путях уже закодированы.
const absolute = (src) => (src.startsWith('//') ? 'https:' + src : src.startsWith('/') ? BASE + src : src);

const clean = (html) => decode(String(html).replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim();

// «КЛОВН СИМА» → «Кловн сима». Имена собственные без словаря не восстановить;
// на практике у большинства спектаклей есть аккуратный `<h1>` на странице.
function sentenceCase(s) {
  return String(s).toLowerCase().replace(/\p{L}/u, (c) => c.toUpperCase());
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;|&#0?34;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&ldquo;|&rdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;|&#8211;/g, '–')
  .replace(/&mdash;/g, '—');
