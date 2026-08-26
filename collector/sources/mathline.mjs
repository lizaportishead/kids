import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { parseAge, matchPrice, stripMatch } from '../lib/text.mjs';

// math-line.ru — статичный Tilda-сайт с виджетом табов (T395): расписания обеих
// локаций лежат в исходном HTML одной страницы (просто скрыты CSS), поэтому
// playwright не нужен — достаточно найти нужный rec-блок по data-tab-number.
const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
// По просьбе — берём только эти дни недели, четверг и воскресенье пропускаем.
const ALLOWED_WD = new Set([0, 1, 2, 4, 5]);
// Заголовки, после которых начинается блок про продлёнку/сад, а не расписание.
const STOP_HEADINGS = ['Продленка в MathLine', 'Продлёнка Weekend', 'Образовательная программа'];

const pageCache = new Map();

export async function collectMathline(source, now = new Date()) {
  const pageUrl = source.url.split('#')[0];
  let html = pageCache.get(pageUrl);
  if (!html) {
    html = await fetchPage(pageUrl);
    pageCache.set(pageUrl, html);
  }

  const recId = findRecId(html, source.tabNumber);
  if (!recId) throw new Error('mathline: не нашли rec-блок для tabNumber=' + source.tabNumber);
  const block = extractBlock(html, recId);
  return parseSchedule(block, source, now);
}

// Находит id блока с расписанием по номеру таба (data-tab-number="N" -> data-tab-rec-ids="...").
function findRecId(html, tabNumber) {
  const re = /data-tab-rec-ids="(\d+)"\s+data-tab-number="(\d+)"/g;
  for (const m of html.matchAll(re)) {
    if (Number(m[2]) === Number(tabNumber)) return 'rec' + m[1];
  }
  return null;
}

function extractBlock(html, recId) {
  const start = html.indexOf('id="' + recId + '"');
  if (start === -1) return '';
  const next = html.indexOf('<div id="rec', start + 1);
  return html.slice(start, next === -1 ? html.length : next);
}

function parseSchedule(blockHtml, source, now) {
  const lines = blockHtml
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, '\n')
    .split('\n')
    .map((s) => decode(s.trim()))
    .filter(Boolean);

  const events = [];
  let currentWd = null;

  for (const line of lines) {
    const wdIdx = WEEKDAYS.indexOf(line.toLowerCase());
    if (wdIdx !== -1) { currentWd = wdIdx; continue; }
    if (STOP_HEADINGS.includes(line)) break;

    if (currentWd === null || !ALLOWED_WD.has(currentWd)) continue;

    const m = line.match(/^(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*(.+)$/);
    if (!m) continue;
    const [, h1, min1, h2, min2, restRaw] = m;
    const rest = restRaw.trim();
    if (!rest) continue;

    const time = h1.padStart(2, '0') + ':' + min1;
    const durMin = (Number(h2) * 60 + Number(min2)) - (Number(h1) * 60 + Number(min1));
    const dur = durMin > 0 ? String(durMin) + ' минут' : null;

    const { title, desc: descRaw } = splitTitleDesc(rest);
    const age = extractAge(rest);
    const priceMatch = matchPrice(descRaw);
    const price = priceMatch ? priceMatch.price : null;
    const desc = stripMatch(descRaw, priceMatch) || title;

    const raw = { title, desc, short: desc.slice(0, 150), wd: [currentWd], time, dur, price, age, url: source.url };
    const ev = normalize(source, raw, now);
    if (ev) events.push(ev);
  }

  return events;
}

// Заголовок класса — текст до возрастной скобки; остальное уходит в описание.
function splitTitleDesc(rest) {
  const ageParen = rest.match(/\(([^)]*(?:лет|год)[^)]*)\)/);
  if (!ageParen) {
    const dot = rest.indexOf('. ');
    return dot === -1 ? { title: rest, desc: rest } : { title: rest.slice(0, dot).trim(), desc: rest };
  }
  const title = rest.slice(0, ageParen.index).trim().replace(/[.,;:\s]+$/, '');
  return { title: title || rest, desc: rest };
}

function extractAge(rest) {
  const ageParen = rest.match(/\(([^)]*(?:лет|год)[^)]*)\)/);
  const source = ageParen ? ageParen[1] : rest;
  // "1,5-3 лет" / "5,5-7 лет" — дробный возраст мешает регулярке parseAge, огрубляем до целого.
  return parseAge(source.replace(/(\d{1,2}),\d/g, '$1'));
}

async function fetchPage(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'ru,en;q=0.8', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('mathline ' + url + ': HTTP ' + res.status);
  return res.text();
}

const decode = (s) => s.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#0?39;|&apos;/g, "'").replace(/&ndash;/g, '–').replace(/&mdash;/g, '—');
