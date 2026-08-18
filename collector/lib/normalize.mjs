import { createHash } from 'node:crypto';
import { parseAge } from './text.mjs';

export function ageLabel(age) {
  if (!age) return 'для детей';
  const [a, b] = age;
  if (b >= 16) return a + '+ лет';
  return a + '–' + b + ' ' + (b < 5 ? 'года' : 'лет');
}

// Ключ дедупликации, НЕ зависящий от источника: одно событие, найденное
// и в Instagram, и на «Продлёнке», даёт одинаковый hash.
export function contentHash(ev) {
  const norm = (s) => String(s || '').toLowerCase().replace(/[^a-zа-яё0-9]+/gi, ' ').trim();
  return createHash('sha1')
    // place сознательно НЕ участвует: normalize() подставляет туда имя источника,
    // когда парсер не нашёл площадку, и хэши двух источников разошлись бы.
    .update([norm(ev.title).slice(0, 60), ev.date || (ev.wd || []).join(''), ev.time || ''].join('|'))
    .digest('hex')
    .slice(0, 16);
}

export function makeId(source, ev) {
  return createHash('sha1').update([source.id, ev.title, ev.date || (ev.wd || []).join(''), ev.time || ''].join('|')).digest('hex').slice(0, 12);
}

// Приводит сырое событие к схеме сайта и отбрасывает бесполезное.
export function normalize(source, raw, now = new Date()) {
  const title = (raw.title || '').trim();
  if (!title || title.length < 6) return null;
  if (!raw.date && !(raw.wd && raw.wd.length)) return null;

  const age = raw.age || parseAge(raw.desc || title) || [3, 10];
  const ev = {
    id: '',
    title,
    short: raw.short || title,
    desc: raw.desc || raw.short || title,
    date: raw.date || null,
    wd: raw.wd && raw.wd.length ? raw.wd : null,
    time: raw.time || '10:00',
    dur: raw.dur || '1 час',
    place: raw.place || source.place || source.name,
    address: raw.address || source.address || 'Белград',
    age,
    ageLabel: raw.ageLabel || ageLabel(age),
    price: raw.price || 'уточняется',
    image: raw.image || null,
    source: { id: source.id, name: source.name, kind: source.kind, url: raw.url || source.url, cta: source.cta },
    fetchedAt: now.toISOString()
  };
  ev.id = makeId(source, ev);
  ev.hash = contentHash(ev);
  return ev;
}

export function dedupe(events) {
  const seen = new Map();
  for (const e of events) {
    const key = e.hash || contentHash(e);
    if (!seen.has(key)) seen.set(key, e);
  }
  return [...seen.values()].sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999') || a.time.localeCompare(b.time));
}
