// Приём заявок с формы «Добавить событие» на сайте: браузер шлёт сюда JSON,
// функция пересылает его тебе в Telegram обычным текстовым сообщением.
// Ничего не пишет в базу и не даёт кнопок — это просто уведомление,
// дальше ты сама решаешь, добавлять ли событие.
//
// Секреты (supabase secrets set ...):
//   TELEGRAM_BOT_TOKEN  — токен бота от @BotFather
//   ALLOWED_CHAT_ID     — твой chat_id, куда слать заявки
//
// Деплой:  supabase functions deploy suggest-event --no-verify-jwt

const TELEGRAM_TOKEN = Deno.env.get('TELEGRAM_BOT_TOKEN')!;
const CHAT_ID = Deno.env.get('ALLOWED_CHAT_ID')!;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'content-type',
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, 'content-type': 'application/json' },
  });

// Обрезаем, чтобы одним сообщением в Telegram (лимит 4096) и без попыток
// раздуть запрос.
const clip = (v: unknown, max: number) => String(v ?? '').trim().slice(0, max);

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'method not allowed' }, 405);

  let data: Record<string, unknown>;
  try {
    data = await req.json();
  } catch {
    return json({ error: 'bad json' }, 400);
  }

  const link = clip(data.link, 1500);
  const when = clip(data.when, 200);
  const place = clip(data.place, 300);
  const desc = clip(data.desc, 2000);
  const page = clip(data.page, 300);

  if (!link && !desc) return json({ error: 'empty' }, 400);

  const lines = [
    '🆕 Заявка с сайта «Клубок»',
    '',
    link && `🔗 ${link}`,
    when && `🗓 ${when}`,
    place && `📍 ${place}`,
    desc && `📝 ${desc}`,
    '',
    page && `↩︎ ${page}`,
  ].filter(Boolean);

  const tg = await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      chat_id: CHAT_ID,
      text: lines.join('\n'),
      disable_web_page_preview: false,
    }),
  });

  if (!tg.ok) {
    console.error('telegram sendMessage failed', tg.status, await tg.text());
    return json({ error: 'delivery failed' }, 502);
  }

  return json({ ok: true });
});
