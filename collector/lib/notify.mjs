// Отчёт о прогоне коллектора в Telegram: список площадок и сколько событий
// с каждой собрано, плюс итог и ошибки. Это только уведомление — без кнопок
// и команд, управлять афишей отсюда нельзя.
//
// Молчит, если TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы (например при
// локальном запуске) — тогда возвращает { skipped: true }.
const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const CHAT_ID = process.env.TELEGRAM_CHAT_ID;

export const notifyEnabled = Boolean(TOKEN && CHAT_ID);

export async function sendRunReport(report, sources, { total, now } = {}) {
  if (!notifyEnabled) return { skipped: true };

  const nameOf = new Map(sources.map((s) => [s.id, s.name || s.id]));
  const stamp = (now || new Date()).toISOString().slice(0, 16).replace('T', ' ');

  const venues = report
    .filter((r) => r.status === 'ok' && typeof r.events === 'number' && nameOf.has(r.source))
    .map((r) => `${nameOf.get(r.source)} — ${r.events}`);

  const skipped = report
    .filter((r) => r.status === 'skipped' && nameOf.has(r.source))
    .map((r) => `• ${nameOf.get(r.source)}: пропущено (${r.reason})`);

  const errors = report
    .filter((r) => r.status === 'error')
    .map((r) => `⚠️ ${nameOf.get(r.source) || r.source}: ${r.reason}`);

  // Новые события с сербских сайтов, переведённые машиной: стоит перечитать
  // и перенести выверенный текст в translations.json.
  const auto = report
    .filter((r) => r.status === 'auto' && Array.isArray(r.titles))
    .flatMap((r) => r.titles.map((t) => `• ${t}`));

  const lines = [`🗓 Афиша обновлена · ${stamp} UTC`, ''];
  lines.push(...(venues.length ? venues : ['(ничего не собрано)']));
  if (typeof total === 'number') lines.push('', `Всего в афише: ${total}`);
  if (skipped.length) lines.push('', ...skipped);
  if (auto.length) lines.push('', '🔤 Автоперевод с сербского — проверить:', ...auto);
  if (errors.length) lines.push('', ...errors);

  const res = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      chat_id: CHAT_ID,
      text: lines.join('\n'),
      disable_web_page_preview: true,
    }),
  });
  if (!res.ok) throw new Error('Telegram ' + res.status + ': ' + (await res.text()).slice(0, 300));
  return { sent: true };
}
