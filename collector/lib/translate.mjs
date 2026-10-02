// Запасной машинный перевод с сербского на русский — для событий, которых ещё
// нет в translations.json (новый спектакль в репертуаре появляется на сайте
// сам, ночью, и без этого висел бы в афише по-сербски до ручного перевода).
//
// Ходим в публичный переводчик Google без ключа. Перевод каждого названия
// делается один раз и кладётся в data/translations-auto.json (его коммитит
// workflow вместе с data/). Ручной перевод в translations.json главнее: как
// только событие добавлено туда, автоперевод больше не используется.
const ENDPOINT = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=sr&tl=ru&dt=t';
const TIMEOUT_MS = 20000;
const GAP_MS = 400;
const CHUNK = 1800;
const SHORT_MAX = 150;
const NOTE = 'Событие на сербском языке.';

// Текст уже русский (есть буквы, которых нет в сербской азбуке, и нет сербских) —
// переводить нечего.
export function looksRussian(text) {
  const s = String(text || '');
  return /[ыэъёщй]/i.test(s) && !/[јљњћђџ]/i.test(s);
}

export function parseResponse(json) {
  const parts = Array.isArray(json) && Array.isArray(json[0]) ? json[0] : null;
  if (!parts) throw new Error('неожиданный ответ переводчика');
  return parts.map((p) => (p && p[0]) || '').join('').trim();
}

// Длинное описание режем по предложениям, чтобы не упереться в лимит запроса.
export function splitText(text, max = CHUNK) {
  const out = [];
  let cur = '';
  for (const piece of String(text).split(/(?<=[.!?…])\s+/)) {
    if (cur && (cur + ' ' + piece).length > max) { out.push(cur); cur = piece; }
    else cur = cur ? cur + ' ' + piece : piece;
    while (cur.length > max) { out.push(cur.slice(0, max)); cur = cur.slice(max); }
  }
  if (cur) out.push(cur);
  return out;
}

export function shortOf(desc, max = SHORT_MAX) {
  if (desc.length <= max) return desc;
  const cut = desc.slice(0, max);
  return cut.slice(0, Math.max(cut.lastIndexOf(' '), 40)).replace(/[\s,;:—-]+$/, '') + '…';
}

let lastAt = 0;
async function translateText(text) {
  const src = String(text || '').replace(/\s+/g, ' ').trim();
  if (!src) return '';
  const out = [];
  for (const chunk of splitText(src)) {
    const wait = lastAt + GAP_MS - Date.now();
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    lastAt = Date.now();
    const res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded;charset=UTF-8' },
      body: 'q=' + encodeURIComponent(chunk),
      signal: AbortSignal.timeout(TIMEOUT_MS)
    });
    if (!res.ok) throw new Error('переводчик: HTTP ' + res.status);
    const ru = parseResponse(await res.json());
    if (!ru) throw new Error('переводчик вернул пустой текст');
    out.push(ru);
  }
  return out.join(' ');
}

// Перевод события: { title, short, desc } на русском. Бросает ошибку, если
// переводчик недоступен, — тогда событие остаётся в оригинале и попадает в отчёт.
export async function machineTranslate(ev) {
  const title = await translateText(ev.title);
  const hasDesc = ev.desc && ev.desc.trim() && ev.desc.trim() !== String(ev.title).trim();
  const body = hasDesc ? await translateText(ev.desc) : title;
  return { title, short: shortOf(body), desc: body + ' ' + NOTE };
}
