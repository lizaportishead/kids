// Telegram-бот «Клубок»: приходит текст/фото афиши от одного разрешённого
// пользователя, Claude извлекает структуру события, пишем в public.events
// со статусом pending и предлагаем в чате кнопки «Опубликовать» / «Удалить».
//
// Секреты (supabase secrets set ...): ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN,
// TELEGRAM_WEBHOOK_SECRET, ALLOWED_CHAT_ID.
// SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY инжектятся платформой сами.

import { createClient } from 'jsr:@supabase/supabase-js@2';

const TELEGRAM_TOKEN = Deno.env.get('TELEGRAM_BOT_TOKEN')!;
const WEBHOOK_SECRET = Deno.env.get('TELEGRAM_WEBHOOK_SECRET')!;
const ALLOWED_CHAT_ID = Deno.env.get('ALLOWED_CHAT_ID')!;
const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;

const sb = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);

const WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

Deno.serve(async (req) => {
  if (req.headers.get('x-telegram-bot-api-secret-token') !== WEBHOOK_SECRET) {
    return new Response('forbidden', { status: 401 });
  }
  const update = await req.json();
  try {
    if (update.callback_query) await handleCallback(update.callback_query);
    else if (update.message) await handleMessage(update.message);
  } catch (err) {
    console.error(err);
  }
  return new Response('ok');
});

async function handleMessage(msg: any) {
  if (String(msg.chat.id) !== ALLOWED_CHAT_ID) return;

  if (msg.text === '/start') {
    await tg('sendMessage', { chat_id: msg.chat.id, text: 'Скинь текст или фото афиши — разберу и предложу на публикацию.' });
    return;
  }

  const caption = (msg.caption || msg.text || '').trim();
  let imageB64: { mime: string; data: string } | null = null;
  let storedImageUrl: string | null = null;

  if (msg.photo?.length) {
    const largest = msg.photo[msg.photo.length - 1];
    const bytes = await downloadTelegramFile(largest.file_id);
    imageB64 = { mime: 'image/jpeg', data: encodeBase64(bytes) };
    storedImageUrl = await uploadPhoto(bytes, largest.file_unique_id);
  }

  if (!caption && !imageB64) return;
  await tg('sendMessage', { chat_id: msg.chat.id, text: '🔎 Разбираю…' });

  const ev = await extractEvent(caption, imageB64);
  if (!ev) {
    await tg('sendMessage', { chat_id: msg.chat.id, text: 'Не смогла разобрать событие. Попробуй переформулировать или добавить деталей.' });
    return;
  }
  const image = storedImageUrl;
  const id = await makeId(ev);
  const hash = await contentHash(ev);

  const row = {
    id, title: ev.title, short: ev.short, desc: ev.desc,
    date: ev.date, wd: ev.wd, time: ev.time, dur: ev.dur,
    place_name: ev.place, place_address: ev.address,
    age_min: ev.age[0], age_max: ev.age[1], age_label: ev.ageLabel,
    price: ev.price, image,
    source: { id: 'telegram', name: 'Ручное добавление', kind: 'Telegram-бот', url: null, cta: null },
    hash, status: 'pending', fetched_at: new Date().toISOString(),
  };

  const { error } = await sb.rpc('upsert_events', { payload: [row] });
  if (error) {
    await tg('sendMessage', { chat_id: msg.chat.id, text: `Ошибка записи в базу: ${error.message}` });
    return;
  }

  await tg('sendMessage', {
    chat_id: msg.chat.id,
    text: formatPreview(ev),
    reply_markup: {
      inline_keyboard: [[
        { text: '✅ Опубликовать', callback_data: `pub:${id}` },
        { text: '🗑 Удалить', callback_data: `del:${id}` },
      ]],
    },
  });
}

async function handleCallback(cq: any) {
  if (String(cq.message.chat.id) !== ALLOWED_CHAT_ID) return;
  const [action, id] = String(cq.data).split(':');

  if (action === 'pub') {
    await sb.from('events').update({ status: 'approved' }).eq('id', id);
    await tg('editMessageText', { chat_id: cq.message.chat.id, message_id: cq.message.message_id, text: cq.message.text + '\n\n✅ опубликовано' });
  } else if (action === 'del') {
    await sb.from('events').delete().eq('id', id);
    await tg('editMessageText', { chat_id: cq.message.chat.id, message_id: cq.message.message_id, text: cq.message.text + '\n\n🗑 удалено' });
  }
  await tg('answerCallbackQuery', { callback_query_id: cq.id });
}

async function extractEvent(caption: string, image: { mime: string; data: string } | null) {
  const now = new Date().toISOString().slice(0, 10);
  const content: any[] = [];
  if (image) content.push({ type: 'image', source: { type: 'base64', media_type: image.mime, data: image.data } });
  content.push({ type: 'text', text: caption || '(текста нет, событие описано только на картинке)' });

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({
      model: 'claude-sonnet-5',
      max_tokens: 1024,
      system: `Сегодня ${now}. Ты извлекаешь детское событие в Белграде из поста или скриншота афиши для сайта. ` +
        `Вызови extract_event с максимально точными полями. Разовое событие — заполни date (YYYY-MM-DD), wd оставь пустым. ` +
        `Регулярное (каждую субботу и т.п.) — заполни wd (0=пн..6=вс), date оставь пустым. ` +
        `Если данных для поля нет — разумные умолчания (age_min:3, age_max:10, time:"10:00", price:"уточняется"). ` +
        `Если в присланном вообще нет события — вызови extract_event с title:"".`,
      tools: [{
        name: 'extract_event',
        description: 'Структурированные данные события для афиши',
        input_schema: {
          type: 'object',
          required: ['title', 'short', 'desc', 'time', 'place', 'address', 'age_min', 'age_max', 'price'],
          properties: {
            title: { type: 'string' },
            short: { type: 'string', description: 'краткое описание, одна фраза' },
            desc: { type: 'string' },
            date: { type: 'string', description: 'YYYY-MM-DD, для разового события' },
            wd: { type: 'array', items: { type: 'integer', minimum: 0, maximum: 6 }, description: 'дни недели для регулярного события, 0=пн' },
            time: { type: 'string', description: 'HH:MM' },
            dur: { type: 'string' },
            place: { type: 'string' },
            address: { type: 'string' },
            age_min: { type: 'integer' },
            age_max: { type: 'integer' },
            price: { type: 'string' },
          },
        },
      }],
      tool_choice: { type: 'tool', name: 'extract_event' },
      messages: [{ role: 'user', content }],
    }),
  });

  const data = await res.json();
  const call = data.content?.find((b: any) => b.type === 'tool_use');
  if (!call?.input?.title) return null;
  const f = call.input;
  const age: [number, number] = [f.age_min ?? 3, f.age_max ?? 10];
  return {
    title: String(f.title).trim(),
    short: f.short || f.title,
    desc: f.desc || f.short || f.title,
    date: f.date || null,
    wd: f.wd?.length ? f.wd : null,
    time: f.time || '10:00',
    dur: f.dur || null,
    place: f.place || 'уточняется',
    address: f.address || 'Белград',
    age,
    ageLabel: ageLabel(age),
    price: f.price || 'уточняется',
  };
}

function ageLabel([a, b]: [number, number]) {
  if (b >= 16) return a + '+ лет';
  return a + '–' + b + ' ' + (b < 5 ? 'года' : 'лет');
}

function formatPreview(ev: any) {
  const when = ev.date || (ev.wd || []).map((d: number) => WEEKDAYS[d]).join(', ');
  return `${ev.title}\n${when} ${ev.time}\n📍 ${ev.place}, ${ev.address}\n👶 ${ev.ageLabel} · 💰 ${ev.price}\n\n${ev.short}`;
}

async function sha1Hex(s: string) {
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function makeId(ev: any) {
  return (await sha1Hex(['telegram', ev.title, ev.date || (ev.wd || []).join(''), ev.time || ''].join('|'))).slice(0, 12);
}

async function contentHash(ev: any) {
  const norm = (s = '') => String(s).toLowerCase().replace(/[^a-zа-яё0-9]+/gi, ' ').trim();
  return (await sha1Hex([norm(ev.title).slice(0, 60), ev.date || (ev.wd || []).join(''), ev.time || ''].join('|'))).slice(0, 16);
}

async function downloadTelegramFile(fileId: string): Promise<Uint8Array> {
  const meta = await (await tg('getFile', { file_id: fileId })).json();
  const res = await fetch(`https://api.telegram.org/file/bot${TELEGRAM_TOKEN}/${meta.result.file_path}`);
  return new Uint8Array(await res.arrayBuffer());
}

async function uploadPhoto(bytes: Uint8Array, key: string): Promise<string | null> {
  const path = `${key}.jpg`;
  const { error } = await sb.storage.from('event-photos').upload(path, bytes, { contentType: 'image/jpeg', upsert: true });
  if (error) { console.error('upload', error); return null; }
  return sb.storage.from('event-photos').getPublicUrl(path).data.publicUrl;
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

function tg(method: string, body: unknown) {
  return fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}
