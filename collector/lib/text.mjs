// Разбор русскоязычных подписей: дата, время, возраст, цена, длительность.

const MONTHS = ['январ', 'феврал', 'март', 'апрел', 'ма', 'июн', 'июл', 'август', 'сентябр', 'октябр', 'ноябр', 'декабр'];

export function stripHtml(html = '') {
  return html
    .replace(/<br\s*\/?>(\s*)/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;|&apos;/g, "'")
    .replace(/&laquo;|&raquo;/g, '"')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function parseDate(text, now = new Date()) {
  const t = text.toLowerCase();

  // 22 августа / 22 авг
  let m = t.match(/(\d{1,2})\s+([а-яё]{3,})/);
  if (m) {
    const mi = MONTHS.findIndex((p) => m[2].startsWith(p));
    if (mi !== -1) return resolveYear(mi, Number(m[1]), now);
  }
  // 22.08 / 22.08.2026 / 22/08
  m = t.match(/\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b/);
  if (m) {
    const day = Number(m[1]), mi = Number(m[2]) - 1;
    if (mi >= 0 && mi < 12 && day >= 1 && day <= 31) {
      if (m[3]) {
        const y = Number(m[3].length === 2 ? '20' + m[3] : m[3]);
        return iso(new Date(y, mi, day));
      }
      return resolveYear(mi, day, now);
    }
  }
  // сегодня / завтра / в субботу
  if (/\bсегодня\b/.test(t)) return iso(now);
  if (/\bзавтра\b/.test(t)) return iso(addDays(now, 1));
  const WD = ['понедельник', 'вторник', 'сред', 'четверг', 'пятниц', 'суббот', 'воскресен'];
  const wi = WD.findIndex((w) => t.includes(w));
  if (wi !== -1) return iso(nextWeekday(now, wi));
  return null;
}

export function parseWeekdays(text) {
  const t = text.toLowerCase();
  const WD = [/\bпн\b|понедельник/, /\bвт\b|вторник/, /\bср\b|сред/, /\bчт\b|четверг/, /\bпт\b|пятниц/, /\bсб\b|суббот/, /\bвс\b|воскресен/];
  const hits = WD.map((re, i) => (re.test(t) ? i : -1)).filter((i) => i !== -1);
  return hits.length > 1 || /кажд/.test(t) ? hits : [];
}

export function parseTime(text) {
  const m = text.match(/\b([01]?\d|2[0-3])[:.]([0-5]\d)\b/);
  if (m) return String(m[1]).padStart(2, '0') + ':' + m[2];
  const h = text.match(/\bв\s+([01]?\d|2[0-3])\s*(?:ч|часов|часа)?\b/i);
  return h ? String(h[1]).padStart(2, '0') + ':00' : null;
}

export function parseAge(text) {
  let m = text.match(/(\d{1,2})\s*[–—-]\s*(\d{1,2})\s*(?:лет|год)/i);
  if (m) return [Number(m[1]), Number(m[2])];
  m = text.match(/\bот\s*(\d{1,2})\s*(?:до\s*(\d{1,2}))?\s*(?:лет|год)/i);
  if (m) return [Number(m[1]), m[2] ? Number(m[2]) : Number(m[1]) + 4];
  m = text.match(/(\d{1,2})\s*\+/);
  if (m) return [Number(m[1]), 16];
  return null;
}

const PRICE_COMBO_RE = /(\d[\d\s]*)\s*RSD\s*разовое\s*занятие(?:\s*\/\s*(\d[\d\s]*)\s*RSD\s*абонемент[^.]*)?\.?/i;
const PRICE_SUBSCRIPTION_RE = /Стоимость абонемента\s*-?\s*(\d[\d\s]*)\s*RSD\s*для детей сада,\s*(\d[\d\s]*)\s*RSD\s*для остальных детей\.?/i;
const PRICE_SIMPLE_RE = /(\d[\d\s]{1,6})\s*(rsd|дин|динар[а-я]*|€|eur|евро)\.?/i;
const PRICE_FREE_RE = /\bбесплатн[а-я]*\.?/i;
const PRICE_DONATE_RE = /\b(донат|по желанию)\.?/i;

// Находит упоминание цены в тексте и возвращает распознанное значение вместе
// с исходным фрагментом (raw), чтобы вызывающий код мог вырезать его из
// описания и не дублировать цену на странице дважды.
export function matchPrice(text) {
  let m = text.match(PRICE_COMBO_RE);
  if (m) {
    let price = m[1].replace(/\s/g, '') + ' RSD (разовое)';
    if (m[2]) price += ', абонемент от ' + m[2].replace(/\s/g, '') + ' RSD за 4 занятия';
    return { price, raw: m[0] };
  }
  m = text.match(PRICE_SUBSCRIPTION_RE);
  if (m) return { price: 'абонемент ' + m[1].replace(/\s/g, '') + ' RSD (дети сада) / ' + m[2].replace(/\s/g, '') + ' RSD (остальные)', raw: m[0] };
  m = text.match(PRICE_SIMPLE_RE);
  if (m) {
    const n = m[1].replace(/\s/g, '');
    const unit = /€|eur|евро/i.test(m[2]) ? '€' : 'RSD';
    return { price: unit === '€' ? n + ' €' : n + ' RSD', raw: m[0] };
  }
  m = text.match(PRICE_FREE_RE);
  if (m) return { price: 'бесплатно', raw: m[0] };
  m = text.match(PRICE_DONATE_RE);
  if (m) return { price: 'донейшн', raw: m[0] };
  return null;
}

export function parsePrice(text) {
  const m = matchPrice(text);
  return m ? m.price : null;
}

// Вырезает найденный ранее фрагмент цены из текста описания, чтобы она не
// повторялась дважды: и в отдельном поле price, и в самом описании.
export function stripMatch(text, m) {
  if (!m) return text;
  return text.replace(m.raw, ' ').replace(/[ \t]{2,}/g, ' ').replace(/\s+([.,;:])/g, '$1').trim();
}

export function parseDuration(text) {
  const m = text.match(/(\d{1,3})\s*(?:мин|минут)/i);
  if (m) return m[1] + ' минут';
  const h = text.match(/(\d(?:[.,]\d)?)\s*(?:ч|часа|часов)\b/i);
  return h ? h[1].replace('.', ',') + ' часа' : null;
}

export function titleFrom(text) {
  const line = text.split('\n').map((s) => s.trim()).find((s) => s.length > 8 && s.length < 90);
  if (!line) return text.slice(0, 70).trim();
  return line.replace(/^[^\p{L}\d«"]+/u, '').replace(/[!.,;:\s]+$/, '').slice(0, 90);
}

export function shortFrom(text, title) {
  const body = text.split('\n').map((s) => s.trim()).filter(Boolean).filter((s) => s !== title).join(' ');
  const cut = body.slice(0, 150);
  return (cut.length < body.length ? cut.replace(/\s\S*$/, '') + '…' : cut) || title;
}

export const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
export const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

function resolveYear(monthIndex, day, now) {
  const thisYear = new Date(now.getFullYear(), monthIndex, day);
  // прошедшую дату считаем следующим годом (анонсы смотрят вперёд)
  if (thisYear < addDays(now, -3)) return iso(new Date(now.getFullYear() + 1, monthIndex, day));
  return iso(thisYear);
}

function nextWeekday(now, target) {
  const cur = (now.getDay() + 6) % 7;
  const delta = (target - cur + 7) % 7 || 7;
  return addDays(now, delta);
}
