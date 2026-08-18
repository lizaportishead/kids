-- Клубок: схема базы событий (Supabase / Postgres)
-- Выполнить один раз в Supabase → SQL Editor → Run.

create table if not exists public.events (
  id          text primary key,               -- sha1-хэш из коллектора
  title       text not null,
  short       text,
  "desc"      text,
  date        date,                            -- разовое событие
  wd          smallint[],                      -- регулярное: дни недели 0=пн
  time        text not null default '10:00',
  dur         text,
  place       text,
  address     text,
  age_min     smallint not null default 3,
  age_max     smallint not null default 10,
  age_label   text,
  price       text,
  image       text,
  source      jsonb not null default '{}',     -- {id,name,kind,url,cta}
  source_url  text generated always as (source->>'url') stored,
  hash        text,                            -- ключ дедупликации между источниками
  status      text not null default 'approved' -- pending | approved | hidden
                check (status in ('pending','approved','hidden')),
  fetched_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

create index if not exists events_date_idx   on public.events (date);
create index if not exists events_status_idx on public.events (status);
create unique index if not exists events_hash_idx on public.events (hash) where hash is not null;

-- Сайту отдаём только одобренное, в форме, которую он уже умеет читать.
create or replace view public.events_public as
select id, title, short, "desc",
       to_char(date, 'YYYY-MM-DD') as date,
       wd, time, dur, place, address,
       array[age_min, age_max] as age,
       age_label as "ageLabel",
       price, image, source
from public.events
where status = 'approved'
  -- нижняя граница — начало текущей недели: UI позволяет уйти назад по стрелке «‹»
  and (date is null or date >= date_trunc('week', current_date)::date)
order by date nulls last, time;

-- Upsert из коллектора: обновляет содержимое, но НЕ трогает status.
-- Так ручное одобрение/скрытие переживает ночные прогоны.
-- Колонки перечислены явно: source_url — generated always, в него писать нельзя.
create or replace function public.upsert_events(payload jsonb)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare n integer;
begin
  create temp table _incoming on commit drop as
  select id, title, short, "desc", date, wd, time, dur, place, address, age_min, age_max, age_label, price, image, source, hash, status, fetched_at, updated_at
  from jsonb_populate_recordset(null::public.events, payload);

  -- Тот же hash, но другой id = дубль из второго источника: старую запись убираем.
  -- Скрытые вручную не удаляем, а исключаем из вставки — иначе они вернутся на сайт.
  delete from public.events d
  using _incoming p
  where d.hash = p.hash and d.id <> p.id and d.status <> 'hidden';

  delete from _incoming p
  where p.hash is not null
    and exists (select 1 from public.events h where h.hash = p.hash and h.status = 'hidden');

  insert into public.events as e (id, title, short, "desc", date, wd, time, dur, place, address, age_min, age_max, age_label, price, image, source, hash, status, fetched_at, updated_at)
  select id, title, short, "desc", date, wd, time, dur, place, address, age_min, age_max, age_label, price, image, source, hash, status, fetched_at, updated_at from _incoming
  on conflict (id) do update set
    title      = excluded.title,
    short      = excluded.short,
    "desc"     = excluded."desc",
    date       = excluded.date,
    wd         = excluded.wd,
    time       = excluded.time,
    dur        = excluded.dur,
    place      = excluded.place,
    address    = excluded.address,
    age_min    = excluded.age_min,
    age_max    = excluded.age_max,
    age_label  = excluded.age_label,
    price      = excluded.price,
    image      = coalesce(excluded.image, e.image),
    source     = excluded.source,
    hash       = excluded.hash,
    fetched_at = excluded.fetched_at,
    updated_at = now();
  get diagnostics n = row_count;
  return n;
end;
$$;

revoke all on function public.upsert_events(jsonb) from public, anon, authenticated;
grant execute on function public.upsert_events(jsonb) to service_role;

alter table public.events enable row level security;

-- Публичное чтение только через представление; таблица закрыта.
drop policy if exists "read approved" on public.events;
create policy "read approved" on public.events
  for select using (status = 'approved');

grant select on public.events_public to anon, authenticated;
