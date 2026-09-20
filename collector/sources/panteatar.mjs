import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { iso } from '../lib/text.mjs';

// panteatar.rs/repertoar — сайт театра «Пан театар» (Звездара, Белград), сербская
// латиница. Репертуар отдаётся серверной вёрсткой: один месяц на страницу
// (`?month=YYYY-MM`), фильтр по сцене (`?scene=decja-scena`) — у театра две
// сцены, «Dečja scena» (детская) и «Večernja scena» (взрослая, «Mihajlo
// Viktorović»). Берём только детскую.
//
// Каждый показ — `<article id="izvodjenje-N" class="performance-row">`: точная
// дата-время в `<time datetime>`, афиша, название (ALLCAPS), «4+ · 45 min» (часть
// может отсутствовать) и кнопка «Kupi ONLINE» на tickets.rs. Со страницы
// спектакля (`/predstave/<slug>`) берём синопсис из блока «O predstavi» и
// возраст из «Uzrast», если в списке его нет.
//
// Только разовые датированные показы — раздел «Афиша» (date задан, wd нет).
const BASE = 'https://panteatar.rs';
const MONTHS_AHEAD = 3;
const PAGE_DELAY_MS = 400;

export async function collectPanteatar(source, now = new Date()) {
  const today = iso(now);
  const rows = [];
  for (let i = 0; i < MONTHS_AHEAD; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    const month = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
    const html = await fetchText(BASE + '/repertoar?scene=decja-scena&month=' + month);
    for (const article of html.split('<article id="izvodjenje-').slice(1)) {
      const row = parseRow(article.split('</article>')[0]);
      if (row && row.date >= today) rows.push(row);
    }
    if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);
  }

  const details = new Map();
  const events = [];
  for (const row of rows) {
    if (!details.has(row.slug)) {
      details.set(row.slug, await fetchDetail(row.slug).catch((err) => {
        console.error('panteatar: страница «' + row.title + '» не загрузилась: ' + (err.message || err));
        return null;
      }));
      if (PAGE_DELAY_MS) await sleep(PAGE_DELAY_MS);
    }
    const detail = details.get(row.slug);

    const title = sentenceCase(row.title);
    const desc = (detail && detail.desc) || title;
    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: row.date,
      time: row.time,
      dur: row.dur,
      age: row.age || (detail && detail.age) || null,
      price: null,
      url: source.url
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    if (row.image) {
      ev.imageRemote = row.image;
      ev.imageKey = 'panteatar-' + row.slug;
    }
    events.push(ev);
  }
  return events;
}

// Один показ: id, дата/время из `<time datetime="2026-09-27T12:00:00+02:00">`
// (часовой пояс — Белград, поэтому дату и время читаем как записаны, без
// пересчёта), сцена из «eyebrow», название и ссылка из `<h3><a>`.
function parseRow(article) {
  const id = (article.match(/^(\d+)"/) || [])[1];
  const mDt = article.match(/datetime="(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  const mTitle = article.match(/<h3><a href="[^"]*\/predstave\/([^"?#]+)"[^>]*>([^<]+)<\/a><\/h3>/);
  if (!id || !mDt || !mTitle) return null;

  const scene = decode((article.match(/eyebrow"><i><\/i>([^<]*)</) || [])[1] || '').trim();
  if (scene && !/de[cč]ja/i.test(scene)) return null;

  const meta = decode((article.match(/<\/h3>\s*<p>([^<]*)<\/p>/) || [])[1] || '');
  const image = (article.match(/performance-poster-thumb[\s\S]*?<img src="([^"]+)"/) || [])[1] || null;

  return {
    id,
    date: mDt[1],
    time: mDt[2],
    slug: mTitle[1],
    title: decode(mTitle[2]).trim(),
    age: parseAgeText(meta),
    dur: parseDurText(meta),
    image
  };
}

// «4+ · 45 min» → возраст 4+, 45 минут; «3+» → только возраст.
// «4+» → [4, 16]; «5-10» → [5, 10] (как в парсере «Пинокио»).
function parseAgeText(text) {
  const s = String(text || '');
  let m = s.match(/(\d{1,2})\s*[-–—]\s*(\d{1,2})/);
  if (m) return [Number(m[1]), Number(m[2])];
  m = s.match(/(\d{1,2})\s*\+/);
  return m ? [Number(m[1]), 16] : null;
}

function parseDurText(text) {
  const m = String(text || '').match(/(\d{1,3})\s*min/i);
  return m ? m[1] + ' минут' : null;
}

// --- страница спектакля ----------------------------------------------------

async function fetchDetail(slug) {
  const html = await fetchText(BASE + '/predstave/' + slug);

  const uzrast = (html.match(/<b>Uzrast<\/b>\s*([^<]*)</) || [])[1] || '';

  // Синопсис — первый содержательный <p> блока «O predstavi»: пропускаем строку
  // «Uzrast: 3+» и пустые <p>, обрываем на списке титров («Tekst i režija …»).
  const body = (html.match(/<h2>O predstavi<\/h2>\s*<div class="rich-text">([\s\S]*?)<\/div>/) || [])[1] || '';
  let desc = '';
  for (const m of body.matchAll(/<p>([\s\S]*?)<\/p>/g)) {
    const text = decode(m[1].replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim();
    if (!text || /^uzrast\b/i.test(text)) continue;
    if (/^(tekst|re[zž]ija|scenografija|kostim|muzika|igraju|dramatizacija|adaptacija|koreograf)/i.test(text)) break;
    desc = text;
    break;
  }
  return { desc, age: parseAgeText(uzrast) };
}

// --- утилиты -----------------------------------------------------------------

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'sr,ru;q=0.8,en;q=0.6', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('panteatar ' + url + ': HTTP ' + res.status);
  return res.text();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// «ALISA U ZEMLJI OZA» → «Alisa u zemlji oza». Имена собственные внутри
// названия без словаря не восстановить — ту же сентенс-форму даёт и deCaps
// на фронтенде.
function sentenceCase(s) {
  const t = String(s).toLowerCase();
  return t.replace(/\p{L}/u, (c) => c.toUpperCase());
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;|&#0?34;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&#0?43;/g, '+')
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&ldquo;|&rdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;|&#8211;/g, '–')
  .replace(/&mdash;/g, '—');
