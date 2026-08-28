// Приём сообщений с формы «Сообщить об ошибке» в подвале сайта: браузер шлёт
// сюда JSON, функция пересылает его тебе в Telegram. Если приложен скриншот —
// уходит фотографией (sendPhoto), иначе обычным текстом (sendMessage).
// В базу ничего не пишет — это просто уведомление.
//
// Секреты (supabase secrets set ...):
//   TELEGRAM_BOT_TOKEN  — токен бота от @BotFather
//   ALLOWED_CHAT_ID     — твой chat_id, куда слать сообщения
//
// Деплой:  supabase functions deploy report-bug --no-verify-jwt

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

const clip = (v: unknown, max: number) => String(v ?? '').trim().slice(0, max);
const tgUrl = (method: string) => `https://api.telegram.org/bot${TELEGRAM_TOKEN}/${method}`;

// Лимиты Telegram: текст 4096, подпись к фото 1024, загружаемое фото 10 МБ.
const CAPTION_MAX = 1024;
const PHOTO_BYTES_MAX = 10 * 1024 * 1024;

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'method not allowed' }, 405);

  let data: Record<string, unknown>;
  try {
    data = await req.json();
  } catch {
    return json({ error: 'bad json' }, 400);
  }

  const page = clip(data.page, 1500);
  const desc = clip(data.desc, 3000);
  if (!desc) return json({ error: 'empty' }, 400);

  const text = [
    '🐞 Сообщение об ошибке — сайт «Клубок»',
    '',
    `📝 ${desc}`,
    '',
    page && `↩︎ ${page}`,
  ].filter(Boolean).join('\n');

  // Скриншот: base64 без data-URL префикса, необязательный.
  const imgB64 = typeof data.image === 'string' ? data.image.trim() : '';
  const imgType = clip(data.imageType, 100) || 'image/jpeg';
  const imgName = clip(data.imageName, 200) || 'screenshot.jpg';

  let sendText = true;

  if (imgB64) {
    let bytes: Uint8Array;
    try {
      const bin = atob(imgB64);
      bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    } catch {
      return json({ error: 'bad image' }, 400);
    }
    if (bytes.length > PHOTO_BYTES_MAX) return json({ error: 'image too large' }, 413);

    const fd = new FormData();
    fd.append('chat_id', CHAT_ID);
    fd.append('caption', text.slice(0, CAPTION_MAX));
    fd.append('photo', new Blob([bytes], { type: imgType }), imgName);

    const tg = await fetch(tgUrl('sendPhoto'), { method: 'POST', body: fd });
    if (!tg.ok) {
      console.error('telegram sendPhoto failed', tg.status, await tg.text());
      return json({ error: 'delivery failed' }, 502);
    }
    // Полный текст влез в подпись — второе сообщение не нужно.
    sendText = text.length > CAPTION_MAX;
  }

  if (sendText) {
    const tg = await fetch(tgUrl('sendMessage'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: CHAT_ID, text, disable_web_page_preview: true }),
    });
    if (!tg.ok) {
      console.error('telegram sendMessage failed', tg.status, await tg.text());
      return json({ error: 'delivery failed' }, 502);
    }
  }

  return json({ ok: true });
});
