import { normalize } from '../lib/normalize.mjs';
import { parseAge, parseDuration, parsePrice, stripHtml } from '../lib/text.mjs';

// reg.prodlenka.me — SPA на base44: HTML пустой, расписание приезжает JSON-ом.
// Рендерим страницу headless-браузером и перехватываем ответы API.
export async function collectProdlenka(source, now = new Date()) {
  const { chromium } = await import('playwright');
  const browser = await chromium.launch();
  const page = await browser.newPage({ locale: 'ru-RU', viewport: { width: 1280, height: 1600 } });
  const payloads = [];

  page.on('response', async (res) => {
    const url = res.url();
    if (!/\/api\/|\.json(\?|$)|entities|classes|schedule|sessions/i.test(url)) return;
    if (!(res.headers()['content-type'] || '').includes('json')) return;
    try { payloads.push(await res.json()); } catch { /* не json */ }
  });

  try {
    await page.goto(source.url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(2500);
    const events = payloads.flatMap((p) => harvest(p)).map((raw) => normalize(source, raw, now)).filter(Boolean);
    if (events.length) return events;
    return fromDom(await page.content(), source, now);
  } finally {
    await browser.close();
  }
}

// Рекурсивно ищем в любом JSON объекты, похожие на занятие.
function harvest(node, out = []) {
  if (Array.isArray(node)) { node.forEach((n) => harvest(n, out)); return out; }
  if (!node || typeof node !== 'object') return out;

  const title = pick(node, ['title', 'name', 'class_name', 'activity', 'event_name']);
  const start = pick(node, ['start_time', 'start_date', 'starts_at', 'date', 'datetime', 'day']);
  if (title && start) {
    const s = String(start);
    const date = (s.match(/\d{4}-\d{2}-\d{2}/) || [null])[0];
    const time = (s.match(/(\d{2}:\d{2})/) || [null])[0] || pick(node, ['time', 'start']) || null;
    const desc = stripHtml(String(pick(node, ['description', 'details', 'about', 'summary']) || ''));
    const ageMin = num(pick(node, ['age_min', 'min_age', 'ageFrom']));
    const ageMax = num(pick(node, ['age_max', 'max_age', 'ageTo']));
    out.push({
      title: String(title).trim(),
      desc: desc || String(title),
      short: (desc || String(title)).slice(0, 150),
      date,
      wd: [],
      time: time ? String(time).slice(0, 5) : null,
      dur: durFrom(node) || parseDuration(desc),
      price: priceFrom(node) || parsePrice(desc),
      age: ageMin != null && ageMax != null ? [ageMin, ageMax] : parseAge(desc || String(title)),
      image: pick(node, ['image', 'image_url', 'cover', 'photo']) || null,
      url: pick(node, ['url', 'link', 'booking_url']) || null
    });
  }
  Object.values(node).forEach((v) => { if (v && typeof v === 'object') harvest(v, out); });
  return out;
}

// Резерв: расписание отрисовано в DOM, но API мы не распознали.
function fromDom(html, source, now) {
  const text = stripHtml(html);
  const rows = text.split('\n').map((s) => s.trim()).filter((s) => /\d{1,2}:\d{2}/.test(s) && s.length > 12);
  return rows.slice(0, 40).map((row) => normalize(source, {
    title: row.replace(/\d{1,2}:\d{2}\s*[–—-]?\s*(\d{1,2}:\d{2})?/, '').trim(),
    desc: row,
    short: row,
    time: (row.match(/\d{1,2}:\d{2}/) || [null])[0],
    wd: [0, 1, 2, 3, 4],
    price: parsePrice(row),
    dur: parseDuration(row)
  }, now)).filter(Boolean);
}

const pick = (o, keys) => keys.map((k) => o[k]).find((v) => v != null && v !== '');
const num = (v) => (v == null || isNaN(Number(v)) ? null : Number(v));
const durFrom = (o) => { const m = num(pick(o, ['duration', 'duration_minutes', 'length'])); return m ? m + ' минут' : null; };
const priceFrom = (o) => { const p = pick(o, ['price', 'cost', 'amount']); return p == null ? null : /[€a-zа-я]/i.test(String(p)) ? String(p) : p + ' RSD'; };
