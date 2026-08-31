import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { parseAge } from '../lib/text.mjs';

// beopinokio.rs/reg — статичный Tilda-сайт развивающего центра «ЛаборатоРиЯ»
// (детский сад BeoPinOKio). Расписание лежит в форме записи как набор
// чекбокс-групп: одна группа на день недели (data-field / t-input-title =
// «Понедельник» … «Воскресенье»), внутри — <input type="checkbox" value="ЧЧ.ММ Название возраст">.
// Парсим value чекбоксов под заголовками-днями; индивидуальные занятия
// (по просьбе) не берём.
const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
const SKIP_RE = /индивидуальн/i;

export async function collectBeopinokio(source, now = new Date()) {
  const html = await fetchPage(source.url);

  // key = нормализованный заголовок + время → одно занятие, идущее в несколько
  // дней (ДЗЮДО пн/ср/пт и т.п.), собираем в один event с массивом wd.
  const bySlot = new Map();

  for (const group of splitGroups(html)) {
    const wd = WEEKDAYS.indexOf(decode(stripTags(group.title)).toLowerCase().trim());
    if (wd === -1) continue;

    for (const rawValue of group.values) {
      const line = decode(rawValue).replace(/\s+/g, ' ').trim();
      if (!line || SKIP_RE.test(line)) continue;

      const slot = parseLine(line);
      if (!slot) continue;

      const hit = bySlot.get(slot.key);
      if (hit) { hit.wd.add(wd); continue; }
      bySlot.set(slot.key, { ...slot, wd: new Set([wd]) });
    }
  }

  const events = [];
  for (const slot of bySlot.values()) {
    const raw = {
      title: slot.title,
      desc: slot.desc,
      short: slot.desc.slice(0, 150),
      wd: [...slot.wd].sort((a, b) => a - b),
      time: slot.time,
      dur: slot.dur,
      age: slot.age,
      price: null,
      url: source.url
    };
    const ev = normalize(source, raw, now);
    if (ev) events.push(ev);
  }
  return events;
}

// Форма Tilda разбита на группы `class="t-input-group…"`. В каждой — заголовок
// (`field="li_title__…">Понедельник</div>`) и чекбоксы с расписанием.
function splitGroups(html) {
  return html.split(/class="t-input-group/).slice(1).map((chunk) => {
    const title = (chunk.match(/field="li_title__[^"]*"[^>]*>([^<]*)</) || [])[1] || '';
    const values = [...chunk.matchAll(/<input[^>]*type="checkbox"[^>]*\svalue="([^"]*)"/g)].map((m) => m[1]);
    return { title, values };
  });
}

// Строка расписания: «18.10 Название возраст» или «11.00 - 11.45 Название возраст».
function parseLine(line) {
  const m = line.match(/^(\d{1,2})[:.](\d{2})\s*(?:[-–—]\s*(\d{1,2})[:.](\d{2})\s*)?(.+)$/);
  if (!m) return null;
  const [, h1, min1, h2, min2, restRaw] = m;
  const rest = restRaw.trim();
  if (rest.length < 6) return null;

  const time = h1.padStart(2, '0') + ':' + min1;

  let dur = null;
  if (h2) {
    const d = (Number(h2) * 60 + Number(min2)) - (Number(h1) * 60 + Number(min1));
    if (d > 0) dur = d % 60 === 0 ? String(d / 60) + (d / 60 === 1 ? ' час' : ' часа') : String(d) + ' минут';
  }

  const title = titleOf(rest);
  if (title.length < 6) return null;

  return {
    key: title.toLowerCase().replace(/[^a-zа-яё0-9]+/gi, ' ').trim().slice(0, 60) + '|' + time,
    title,
    desc: rest,
    time,
    dur,
    age: extractAge(rest)
  };
}

// Заголовок занятия — текст без хвоста с возрастом, без пояснения после тире
// и без скобки в конце. Если срезали слишком много — оставляем строку целиком.
function titleOf(rest) {
  let t = rest
    .replace(/\s*\([^)]*\)\s*$/, '')
    .replace(/\s*[—–-]\s*(?:курс|занятие|подготовк|развити)[а-яё]*\s.*$/i, '')
    .replace(/\s+(?:от\s*)?\d{1,2}(?:[.,]\d)?\s*(?:(?:[-–—]|до)\s*\d{1,2}(?:[.,]\d)?\s*)?(?:лет|год[а-я]*)\+?\s*$/i, '')
    .replace(/\s+\d{1,2}\s*\+\s*$/, '')
    .trim()
    .replace(/[.,;:\s]+$/, '');
  if (t.length < 6) t = rest.replace(/[.,;:\s]+$/, '');
  return t;
}

function extractAge(rest) {
  const s = rest.replace(/(\d{1,2}),\d/g, '$1'); // «1,5 до 3» → «1 до 3», огрубляем дробный возраст
  const m = s.match(/(\d{1,2})\s*(?:[-–—]|до)\s*(\d{1,2})\s*(?:лет|год)/i);
  if (m) return [Number(m[1]), Number(m[2])];
  return parseAge(s);
}

async function fetchPage(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'ru,en;q=0.8', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('beopinokio ' + url + ': HTTP ' + res.status);
  return res.text();
}

const stripTags = (s) => s.replace(/<[^>]+>/g, '');
const decode = (s) => s
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&ndash;/g, '–')
  .replace(/&mdash;/g, '—');
