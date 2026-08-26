import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';

// Публичный пост Telegram-группы, отдающий расписание студии текстом (без
// таблиц): виджет-embed доступен без логина, даже если пост лежит внутри
// закрытой для просмотра группы — достаточно знать id канала и сообщения.
const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];

export async function collectTelegram(source, now = new Date()) {
  const m = source.url.match(/t\.me\/([^/?#]+)\/(\d+)/);
  if (!m) throw new Error('telegram: не разобрал канал/пост из url ' + source.url);
  const [, channel, postId] = m;

  const res = await fetch('https://t.me/' + channel + '/' + postId + '?embed=1&mode=tme', {
    headers: { 'user-agent': UA, 'accept-language': 'ru,en;q=0.8' }
  });
  if (!res.ok) throw new Error('telegram ' + channel + '/' + postId + ': HTTP ' + res.status);
  const html = await res.text();

  const textMatch = html.match(/class="tgme_widget_message_text js-message_text"[^>]*>([\s\S]*?)<\/div>/);
  if (!textMatch) throw new Error('telegram ' + channel + '/' + postId + ': текст поста не найден (разметка изменилась?)');

  const text = textToLines(textMatch[1]);
  return parseSchedule(text, source, now);
}

// Достаём текст построчно: <br> — разделитель строк, эмодзи-иконки (картинки
// вместо символов в html-версии) и остальные теги выбрасываем.
function textToLines(html) {
  return html
    .replace(/<i class="emoji"[^>]*>[\s\S]*?<\/i>/g, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .split('\n')
    .map((s) => decode(s.trim()))
    .filter(Boolean);
}

function parseSchedule(lines, source, now) {
  const events = [];
  let currentWd = null;

  for (const line of lines) {
    const wdIdx = WEEKDAYS.indexOf(line.toLowerCase().replace(/:$/, ''));
    if (wdIdx !== -1) { currentWd = wdIdx; continue; }
    if (currentWd === null) continue;

    const t = line.match(/^(\d{1,2})[:.](\d{2})\s+(.+)$/);
    if (!t) continue;
    const [, h, min, rest] = t;
    const title = rest.trim();
    if (!title || title.length < 4) continue;

    const age = extractAge(title);
    // Сайт — про детские занятия; чисто взрослые классы без детского возраста в
    // подписи (например «Керамика взрослые») отсеиваем, а не подставляем дефолт 3-10.
    if (!age && /взросл/i.test(title)) continue;

    const raw = {
      title,
      desc: title,
      short: title,
      wd: [currentWd],
      time: h.padStart(2, '0') + ':' + min,
      age,
      url: source.url
    };
    const ev = normalize(source, raw, now);
    if (ev) events.push(ev);
  }

  return events;
}

function extractAge(text) {
  const cleaned = text.replace(/(\d{1,2}),\d/g, '$1'); // "1,5-3" -> "1-3", огрубляем дробный возраст
  let m = cleaned.match(/(\d{1,2})\s*[–—-]\s*(\d{1,2})\b/);
  if (m) return [Number(m[1]), Number(m[2])];
  m = cleaned.match(/(\d{1,2})\s*\+/);
  if (m) return [Number(m[1]), 16];
  return null;
}

const decode = (s) => s
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&ndash;/g, '–')
  .replace(/&mdash;/g, '—')
  .trim();
