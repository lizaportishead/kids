// Запись событий в Supabase через REST (без зависимостей).
const URL_ = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_KEY;

export const supabaseEnabled = Boolean(URL_ && KEY);

function rowOf(ev, status) {
  return {
    id: ev.id,
    title: ev.title,
    short: ev.short,
    desc: ev.desc,
    date: ev.date || null,
    wd: ev.wd || null,
    time: ev.time,
    dur: ev.dur,
    place: ev.place,
    address: ev.address,
    age_min: ev.age?.[0] ?? 3,
    age_max: ev.age?.[1] ?? 10,
    age_label: ev.ageLabel,
    price: ev.price,
    image: ev.image,
    source: ev.source,
    hash: ev.hash || null,
    status,
    fetched_at: ev.fetchedAt,
    updated_at: new Date().toISOString()
  };
}

// Upsert через функцию upsert_events: она обновляет содержимое и НЕ перезаписывает
// status, поэтому ручное одобрение/скрытие не сбрасывается ночным прогоном.
export async function pushEvents(events, { status = process.env.MODERATION ? 'pending' : 'approved' } = {}) {
  if (!supabaseEnabled) return { skipped: true };
  const rows = events.map((e) => rowOf(e, status));
  const res = await fetch(URL_.replace(/\/$/, '') + '/rest/v1/rpc/upsert_events', {
    method: 'POST',
    headers: {
      apikey: KEY,
      Authorization: 'Bearer ' + KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ payload: rows })
  });
  if (!res.ok) throw new Error('Supabase ' + res.status + ': ' + (await res.text()).slice(0, 300));
  return { written: rows.length };
}
