-- Кабинет площадки: выполнить целиком в Supabase → SQL Editor → Run (можно повторно).

-- ── Кабинет площадки ─────────────────────────────────────────────────────
-- Каждой площадке при подключении вручную заводим пользователя в
-- Supabase Auth (Authentication → Users → Add user), затем сюда вручную
-- прописываем owner_user_id — так площадка получает доступ только к своей
-- карточке и своим событиям. События публикуются сразу (status='approved'),
-- без модерации.

alter table public.place add column if not exists owner_user_id uuid references auth.users (id);
alter table public.place add column if not exists logo         text;
alter table public.place add column if not exists site         text;
alter table public.place add column if not exists telegram     text;
alter table public.place add column if not exists instagram    text;

create unique index if not exists place_owner_idx on public.place (owner_user_id) where owner_user_id is not null;

-- Регулярное событие с разным временем в разные дни — это несколько строк
-- events с общим series_id (одна логическая карточка в кабинете площадки,
-- несколько строк в базе). У разовых событий и у строк коллектора
-- series_id остаётся пустым.
alter table public.events add column if not exists series_id text;
create index if not exists events_series_idx on public.events (series_id) where series_id is not null;

grant select, insert, update, delete on public.place  to authenticated;
grant select, insert, update, delete on public.events to authenticated;

drop policy if exists "venue reads own place" on public.place;
create policy "venue reads own place" on public.place
  for select using (owner_user_id = auth.uid());

drop policy if exists "venue updates own place" on public.place;
create policy "venue updates own place" on public.place
  for update using (owner_user_id = auth.uid())
  with check (owner_user_id = auth.uid());

drop policy if exists "venue reads own events" on public.events;
create policy "venue reads own events" on public.events
  for select using (
    place in (select id from public.place where owner_user_id = auth.uid())
  );

drop policy if exists "venue inserts own events" on public.events;
create policy "venue inserts own events" on public.events
  for insert with check (
    place in (select id from public.place where owner_user_id = auth.uid())
    and status = 'approved'
  );

drop policy if exists "venue updates own events" on public.events;
create policy "venue updates own events" on public.events
  for update using (
    place in (select id from public.place where owner_user_id = auth.uid())
  ) with check (
    place in (select id from public.place where owner_user_id = auth.uid())
    and status = 'approved'
  );

drop policy if exists "venue deletes own events" on public.events;
create policy "venue deletes own events" on public.events
  for delete using (
    place in (select id from public.place where owner_user_id = auth.uid())
  );

-- Файлы площадок: логотип и фото событий. Публичное чтение, писать может
-- только сама площадка и только в свою папку venue-media/<id площадки>/...
insert into storage.buckets (id, name, public)
values ('venue-media', 'venue-media', true)
on conflict (id) do nothing;

drop policy if exists "venue media public read" on storage.objects;
create policy "venue media public read" on storage.objects
  for select using (bucket_id = 'venue-media');

drop policy if exists "venue media own write" on storage.objects;
create policy "venue media own write" on storage.objects
  for insert with check (
    bucket_id = 'venue-media'
    and (storage.foldername(name))[1] = (
      select id::text from public.place where owner_user_id = auth.uid()
    )
  );

drop policy if exists "venue media own update" on storage.objects;
create policy "venue media own update" on storage.objects
  for update using (
    bucket_id = 'venue-media'
    and (storage.foldername(name))[1] = (
      select id::text from public.place where owner_user_id = auth.uid()
    )
  );

drop policy if exists "venue media own delete" on storage.objects;
create policy "venue media own delete" on storage.objects
  for delete using (
    bucket_id = 'venue-media'
    and (storage.foldername(name))[1] = (
      select id::text from public.place where owner_user_id = auth.uid()
    )
  );

-- ── Кабинет площадки: супер-админ и ужесточение прав ─────────────────────
-- Супер-админ — пользователь Supabase Auth с app_metadata.role = 'superadmin'
-- (app_metadata меняется только сервисным ключом, сам пользователь не может).
create or replace function public.is_superadmin()
returns boolean
language sql stable
as $$ select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'superadmin' $$;

drop policy if exists "superadmin reads places" on public.place;
create policy "superadmin reads places" on public.place
  for select using (public.is_superadmin());

drop policy if exists "superadmin updates places" on public.place;
create policy "superadmin updates places" on public.place
  for update using (public.is_superadmin()) with check (public.is_superadmin());

drop policy if exists "superadmin all events" on public.events;
create policy "superadmin all events" on public.events
  for all using (public.is_superadmin()) with check (public.is_superadmin());

drop policy if exists "superadmin media write" on storage.objects;
create policy "superadmin media write" on storage.objects
  for all using (bucket_id = 'venue-media' and public.is_superadmin())
  with check (bucket_id = 'venue-media' and public.is_superadmin());

-- Площадка не должна менять имя (по нему коллектор находит площадку),
-- владельца и служебные поля: разрешаем обновлять только карточку.
revoke update on public.place from authenticated;
grant update (address, phone, link, site, telegram, instagram, logo) on public.place to authenticated;
revoke insert, delete on public.place from authenticated;
