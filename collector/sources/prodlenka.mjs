import { normalize, isExcludedEvent } from '../lib/normalize.mjs';
import { parseAge } from '../lib/text.mjs';
import { UA } from '../lib/images.mjs';

// reg.prodlenka.me — витрина на base44. Публичный REST отдаёт справочники без
// авторизации, поэтому headless-браузер больше не нужен: тянем JSON напрямую.
//
//   entities/Location          — площадки (Продлёнка на Кнеза Данила, Kinder Garden в Сеньяке)
//   entities/Class             — занятия: название с возрастом, описание, цена, длительность, фото
//   entities/Schedule          — конкретные проведения: дата + время + сколько мест занято
//   functions/getBookedCounts  — актуальная занятость мест по каждому расписанию
//
// Одна площадка = один источник в sources.json (поле locationSlug). На витрине
// показаны обе, но расписание сейчас заполнено только для Kinder Garden —
// у Продлёнки на Кнеза Данила будущих занятий нет, источник вернёт 0 событий.

const API = 'https://reg.prodlenka.me/api/apps/6a048c57a9fe367e5ba1a2e6';
const DEFAULT_HORIZON_DAYS = 28; // сколько недель расписания вперёд разворачивать в афишу

export async function collectProdlenka(source, now = new Date()) {
  const [locations, classes] = await Promise.all([
    apiGet('/entities/Location?q=' + q({ is_active: true })),
    apiGet('/entities/Class?q=' + q({ is_active: true }))
  ]);

  const location = locations.find((l) => l.slug === source.locationSlug)
    || locations.find((l) => l.id === source.locationId);
  if (!location) throw new Error('prodlenka: площадка «' + (source.locationSlug || source.locationId) + '» не найдена в API');

  const today = iso(now);
  const horizon = iso(addDays(now, source.horizonDays || DEFAULT_HORIZON_DAYS));
  const schedule = await apiGet(
    '/entities/Schedule?q=' + q({ status: 'scheduled', date: { $gte: today, $lte: horizon } }) + '&sort=date&limit=500'
  );

  let booked = {};
  try {
    booked = (await apiPost('/functions/getBookedCounts')).counts || {};
  } catch {
    /* не критично — в самом расписании есть поле booked_count */
  }

  const classById = new Map(classes.map((c) => [c.id, c]));

  return schedule
    .filter((s) => s.location_id === location.id && s.date >= today && s.date <= horizon)
    .map((s) => {
      const cls = classById.get(s.class_id);
      if (!cls) return null;
      if (num(cls.duration_minutes) > 300) return null; // дневные программы — не разовое занятие

      const desc = cleanText(cls.description) || cls.name;
      const spotsMax = num(s.max_spots) ?? num(cls.max_spots);
      const spotsTaken = booked[s.id] != null ? Number(booked[s.id]) : num(s.booked_count);

      const raw = {
        title: cleanTitle(cls.name),
        desc: withSpots(desc, spotsMax, spotsTaken),
        short: firstLine(desc, 180),
        date: s.date,
        time: (s.start_time || '').slice(0, 5) || null,
        dur: humanDuration(num(cls.duration_minutes)),
        price: formatPrice(cls, desc),
        age: ageFromName(cls.name) || parseAge(cls.name) || parseAge(desc) || null,
        place: source.place || location.name,
        address: source.address || location.address || 'Белград',
        url: source.url
      };

      const ev = normalize(source, raw, now);
      if (!ev || isExcludedEvent(ev)) return null;
      if (cls.image_url) {
        ev.imageRemote = cls.image_url;
        ev.imageKey = 'prodlenka-' + (cls.slug || cls.id);
      }
      return ev;
    })
    .filter(Boolean);
}

async function apiGet(path) {
  const res = await fetch(API + path, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (!res.ok) throw new Error('prodlenka ' + path.split('?')[0] + ': HTTP ' + res.status);
  return res.json();
}

async function apiPost(path) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: { 'user-agent': UA, accept: 'application/json', 'content-type': 'application/json' },
    body: '{}'
  });
  if (!res.ok) throw new Error('prodlenka ' + path.split('?')[0] + ': HTTP ' + res.status);
  return res.json();
}

const q = (obj) => encodeURIComponent(JSON.stringify(obj));
const num = (v) => (v == null || v === '' || isNaN(Number(v)) ? null : Number(v));
const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

// «Описание\n…» в начале, отступы по краям строк, тройные переносы.
function cleanText(s) {
  return String(s || '')
    .replace(/\r/g, '')
    .replace(/^\s*описание\s*\n/i, '')
    .split('\n').map((l) => l.trim()).join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// Длинные названия вида «Prodlenka Weekend (5-8 лет). Огород, Столярка…» режем
// до первого предложения — подробности остаются в описании.
function cleanTitle(name) {
  const t = String(name || '').trim();
  return t.length > 40 ? t.split(/\.\s+/)[0].trim() : t;
}

function firstLine(text, limit) {
  const line = String(text || '').split('\n').map((s) => s.trim()).find(Boolean) || '';
  if (line.length <= limit) return line;
  return line.slice(0, limit).replace(/\s+\S*$/, '') + '…';
}

// «(7–10 лет)», «(4 - 7)», «(5+)» в названии занятия.
function ageFromName(name) {
  const s = String(name || '');
  let m = s.match(/\((\d{1,2})\s*[–—-]\s*(\d{1,2})/);
  if (m) return [Number(m[1]), Number(m[2])];
  m = s.match(/\((\d{1,2})\s*\+/);
  if (m) return [Number(m[1]), 16];
  return null;
}

function humanDuration(min) {
  if (!min) return null;
  if (min < 60) return min + ' минут';
  const h = Math.floor(min / 60), m = min % 60;
  const hh = h + ' ' + (h === 1 ? 'час' : h < 5 ? 'часа' : 'часов');
  return m ? hh + ' ' + m + ' минут' : hh;
}

// Разовая цена из поля price + абонемент из текста описания, если он там указан.
function formatPrice(cls, desc) {
  const single = num(cls.price);
  const cur = /eur|евро|€/i.test(cls.currency || '') ? '€' : 'RSD';
  let out = single ? single + ' ' + cur : null;
  const m = String(desc || '').match(/абонемент(?:\s*на\s*(\d+)\s*занят\w+)?\s*[-–—:]\s*([\d\s]+)\s*(?:rsd|дин|€|eur)/i);
  if (m) {
    const part = 'абонемент ' + m[2].replace(/\s/g, '') + ' ' + cur + (m[1] ? ' за ' + m[1] + ' занятия' : '');
    out = out ? out + ', ' + part : part;
  }
  return out;
}

// Свободные места на конкретную дату — часть той «подробной инфы», что видна
// на витрине по кнопке «Записаться». Обновляется при каждом сборе афиши.
function withSpots(desc, max, taken) {
  if (!max) return desc;
  const free = taken != null ? Math.max(0, max - taken) : null;
  const line = free == null
    ? 'Мест на занятии: ' + max
    : free === 0
      ? 'Свободных мест нет — можно записаться в лист ожидания'
      : 'Свободно мест: ' + free + ' из ' + max;
  return desc + '\n\n' + line;
}
