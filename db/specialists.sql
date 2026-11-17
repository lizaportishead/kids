-- Клубок: специалисты (Supabase / Postgres)
-- Выполнить в Supabase → SQL Editor → Run. Скрипт идемпотентный, можно запускать повторно.
-- Источник данных на сайте пока список SPECIALISTS в index.html; эта таблица — копия и основа для перехода на чтение из базы.

create table if not exists public.specialists (
  id         text primary key,                 -- 'sp-<slug>'
  slug       text not null unique,             -- адрес страницы /specialists/<slug>/
  name       text not null,
  type       text not null                     -- психолог / логопед / дефектолог / нейропсихолог / невролог / репетитор
             check (type in ('psy','logo','defect','neuro','neurol','tutor')),
  age_from   smallint,                         -- null = возраст неизвестен
  age_to     smallint,
  lang       text,
  place      text,
  price      text,
  fee        text,
  dur        text,
  photo      text,
  short      text,
  about      text,
  tg         text,
  wa         text,
  ig         text,
  channel    text,
  phone      text,
  site       text,
  address    text,
  geo        jsonb,                            -- [lat, lng]
  status     text not null default 'approved'  -- pending | approved | hidden
             check (status in ('pending','approved','hidden')),
  sort       int not null default 100,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.specialists enable row level security;

drop policy if exists "read approved specialists" on public.specialists;
create policy "read approved specialists" on public.specialists
  for select using (status = 'approved');

-- Править список может только супер-админ (функция public.is_superadmin() создаётся в db/schema.sql).
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = 'is_superadmin') then
    drop policy if exists "superadmin all specialists" on public.specialists;
    create policy "superadmin all specialists" on public.specialists
      for all using (public.is_superadmin()) with check (public.is_superadmin());
  end if;
end
$$;

grant select on public.specialists to anon, authenticated;
grant insert, update, delete on public.specialists to authenticated;

-- ── Данные ───────────────────────────────────────────────────────────────
insert into public.specialists (id, slug, name, type, age_from, age_to, lang, place, price, fee, dur, photo, short, about, tg, wa, ig, channel, phone, site, address, geo, status, sort) values
  ('sp-maria-sidorkina', 'maria-sidorkina', 'Мария Сидоркина', 'psy', 3, 17, 'Русский', 'Белград, Нови-Сад · кабинет или онлайн', '55 минут · €45', '€45', '55 минут', 'https://optim.tildacdn.pub/tild3930-6162-4661-b536-613730613137/-/resize/920x/-/format/webp/hwMJRtfdCjI_1.jpg.webp', 'Помогает детям-эмигрантам адаптироваться, справиться со страхами и наладить отношения.', 'Детский и подростковый психолог Okids (Вена). Специализируется на работе с детьми-эмигрантами: помогает адаптироваться к новой среде, преодолеть страхи и неуверенность, наладить отношения со сверстниками и близкими. Интегративный подход, в центре — личность ребёнка; использует игровую и арт-терапию.', 'https://t.me/psy_marys', 'https://wa.me/79997194433', 'https://www.instagram.com/psy_marys/', 'https://t.me/kidspsy_maria_sidorkina', null, 'https://maria-sidorkina.tilda.ws/', null, null, 'approved', 10),
  ('sp-svetlana-lavrenova', 'svetlana-lavrenova', 'Светлана Лавренова', 'logo', null, null, 'Русский', 'Белград · центр «We play» (Belgrade Waterfront), выезд на дом', null, null, null, null, 'Логопед и специалист по раннему развитию: запуск речи, билингвизм.', 'Логопед, специалист по раннему развитию, работает как няня. Консультирует по запуску речи и билингвизму. Очный приём по субботам в детском центре «We play» (Belgrade Waterfront), по договорённости выезжает на домашние занятия. Родители отмечают пунктуальность и формат «мама + малыш». Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/svetlana_srbija', null, null, null, null, null, null, null, 'approved', 20),
  ('sp-emiliya-asainova', 'emiliya-asainova', 'Эмилия Асаинова', 'neuro', null, null, 'Русский', 'Белград', null, null, null, null, 'Нейропсихолог, логопед и дефектолог.', 'Указана как нейропсихолог, логопед и дефектолог. Формат приёма и адрес в источнике не названы. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/emilyasainova', null, 'https://www.instagram.com/brain_train_beo/', 'https://t.me/neuro_beo', null, null, null, null, 'approved', 30),
  ('sp-kseniya-yurkanova', 'kseniya-yurkanova', 'Ксения Юрканова', 'logo', null, null, 'Русский', 'Белград', null, null, null, null, 'Логопед по запуску речи и педагог раннего развития.', 'Логопед по запуску речи, педагог раннего развития. Формат приёма и адрес в источнике не названы. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/KseniaYurkanova', null, 'https://www.instagram.com/logoped_yurkanova/', null, null, null, null, null, 'approved', 40),
  ('sp-olga-pilyugina', 'olga-pilyugina', 'Ольга Пилюгина', 'logo', null, null, 'Русский', 'Нови-Сад (приём в Белграде не подтверждён)', null, null, null, null, 'Логопед в Нови-Саде, есть положительный отзыв.', 'Логопед. О ней оставили положительный отзыв в Нови-Саде; приём в Белграде не подтверждён. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/opilugina', null, null, null, null, null, null, null, 'approved', 50),
  ('sp-ekaterina-konyuh-sinitsa', 'ekaterina-konyuh-sinitsa', 'Екатерина Конюх-Синица', 'logo', null, null, 'Русский', 'Онлайн', null, null, null, null, 'Билингвальный логопед: обучает билингвов русскому языку онлайн.', 'Билингвальный логопед, больше 10 лет опыта. Обучает билингвов русскому языку онлайн, консультирует родителей и коллег по билингвизму. Отзывов в чате нет: контакт сохранили как возможный вариант. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', null, null, null, 'https://t.me/bilingual_logoped', null, null, null, null, 'approved', 60),
  ('sp-sasha-novi-sad', 'sasha-novi-sad', 'Александра Гламочич', 'logo', null, null, 'Русский', 'Нови-Сад (кабинет) · онлайн', null, null, null, null, 'Игровой логопед в Нови-Саде: кабинет там и онлайн по всему миру.', 'Логопед в Нови-Саде (игровой логопед), у неё самой ребёнок-билингв. Кабинет в Нови-Саде, консультирует и занимается онлайн из любой страны. Рекомендована в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', null, null, 'https://www.instagram.com/logoprav', null, null, null, null, null, 'approved', 70),
  ('sp-igor-shtuchnyy', 'igor-shtuchnyy', 'Игорь Штучный', 'neurol', null, null, 'Русский', 'Новый Белград · клиника Citilab', null, null, null, null, 'Невролог в клинике Citilab, родители отмечали внимательный осмотр.', 'Невролог в клинике Citilab (Новый Белград). По отзывам родителей: внимательный осмотр ребёнка и подробные ответы на вопросы. Принимает ли он детей сейчас, не подтверждено. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', null, null, null, null, null, null, null, null, 'approved', 80),
  ('sp-aleksandr-dimitrievich', 'aleksandr-dimitrievich', 'Александр Димитриевич', 'neurol', null, null, 'Русский', 'Чачак, по отзыву также Белград', null, null, null, null, 'Невролог, упоминали для ребёнка: Чачак и, по отзыву, Белград.', 'Невролог. Его упоминали для ребёнка: принимал в Чачаке и, по отзыву, в Белграде; район и актуальный адрес не указаны. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', null, null, null, null, null, null, null, null, 'approved', 90),
  ('sp-artem-semenov', 'artem-semenov', 'Артём Семёнов', 'neurol', null, null, 'Русский', 'Белград', null, null, null, null, 'Невролог, есть быстрые свободные окошки.', 'Невролог. Рекомендован за быстрые свободные окошки для записи. Детский он или взрослый, в источнике не указано, уточняйте при записи. Рекомендован в чате «Рожаем в Сербии». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/neurologSemenov', null, null, null, null, null, null, null, 'approved', 100),
  ('sp-marina-gorbunova', 'marina-gorbunova', 'Марина Горбунова', 'logo', null, null, 'Русский', 'Белград · Бежанийска коса / Новый Белград, очно и онлайн', null, null, null, null, 'Логопед, дефектолог и нейропсихолог: речь, внимание, память, моторика.', 'Логопед, дефектолог и нейропсихолог: многолетний опыт работы с детьми в России, США и Сербии. Запуск и развитие речи, коррекция звукопроизношения, развитие внимания, памяти, мышления и моторики, двигательные практики и элементы детской йоги. Принимает также детей от 8 месяцев на разные форматы пребывания под присмотром. Очно и онлайн. Объявление Марины из чата «Тоддлеры и дошкольники Белграда». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/MarinaGorbunovaLogoped', null, 'https://www.instagram.com/marina.gorbunova.kids/', null, null, null, null, null, 'approved', 110),
  ('sp-daria-konovalova', 'daria-konovalova', 'Дарья Коновалова', 'tutor', null, null, 'Русский, английский', 'Белград', '1 час · 2400 RSD', '2400 RSD', '1 час', null, 'Репетитор английского для детей и подростков, первое занятие бесплатно.', 'Репетитор английского для детей, в основном подростков. Образование: лингвистическая гимназия и факультет общей психологии, учится на англистике в университете Singidunum. Преподаёт около двух лет. На занятиях развивает все языковые навыки: речь, понимание на слух, грамматику, чтение и письмо; программа подбирается индивидуально. Первое занятие бесплатное: определит уровень и подскажет, на чём сделать акцент. Пакет из 8 занятий — 16000 RSD (2000 RSD за урок). Отзывы присылает в личные сообщения. Объявление из чата «Белград Школьный». Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/Dariko_art', null, null, null, null, null, null, null, 'approved', 120),
  ('sp-nadezhda-logoped', 'nadezhda-logoped', 'Надежда', 'logo', null, null, 'Русский', 'Белград · Новый Белград (очно) и онлайн', null, null, null, null, 'Логопед и дефектолог: занятия очно на Новом Белграде и онлайн.', 'Логопед. Логопедические и дефектологические занятия очно на Новом Белграде и онлайн. Найдена в Instagram. Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/logoped_belgrade', null, 'https://www.instagram.com/logoped_belgrade/', null, null, null, null, null, 'approved', 130),
  ('sp-sofya-logoped', 'sofya-logoped', 'Софья', 'logo', null, null, 'Русский', 'Белград · Палилула, очно и онлайн', null, null, null, null, 'Логопед-дефектолог: миофункциональная коррекция, подготовка к школе.', 'Логопед-дефектолог, работает с детьми и взрослыми. Миофункциональная коррекция, подготовка к школе. Очно в Белграде (Палилула) и онлайн. Найдена в Instagram. Подробности и актуальность контактов уточняйте у специалиста.', null, null, 'https://www.instagram.com/sofya_belgrade/', null, null, null, null, null, 'approved', 140),
  ('sp-elmira-logoped', 'elmira-logoped', 'Эльмира', 'logo', null, null, 'Русский', 'Новый Белград', null, null, null, null, 'Логопед и миологопед на Новом Белграде, работает с билингвами.', 'Логопед в Белграде (Новый Белград), миологопед, работает с билингвами. Найдена в Instagram. Подробности и актуальность контактов уточняйте у специалиста.', null, null, 'https://www.instagram.com/logoped_v_belgrade/', null, null, null, null, null, 'approved', 150),
  ('sp-irina-vorontsova', 'irina-vorontsova', 'Ирина Воронцова', 'neuro', null, null, 'Русский', 'Белград · Maršala Birjuzova 2–4', null, null, null, null, 'Нейропсихолог: помогает понять, что происходит с ребёнком и как ему помочь.', 'Нейропсихолог, более 20 лет помогает детям и родителям. Консультации в Белграде, адрес: Maršala Birjuzova 2–4. Найдена в Instagram. Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/neiropsiholog_vorontsova', null, 'https://www.instagram.com/neiropsiholog_vorontsova/', null, null, null, null, null, 'approved', 160),
  ('sp-lena-surzhikova', 'lena-surzhikova', 'Лена Суржикова', 'neuro', null, null, 'Русский', 'Белград', null, null, null, null, 'Нейропсихолог: диагностика и нейрокоррекция.', 'Нейропсихолог: диагностика, нейрокоррекция, воспитание и нейроразвитие с научным подходом. Работает в Белграде. Найдена в Instagram. Подробности и актуальность контактов уточняйте у специалиста.', null, null, 'https://www.instagram.com/lenasurzhikova/', null, null, null, null, null, 'approved', 170),
  ('sp-arina-logoped', 'arina-logoped', 'Арина', 'logo', null, null, 'Русский', 'Белград · очно и онлайн', null, null, null, 'data/images/specialist-arina-logoped.jpg', 'Логопед-дефектолог, педагог по подготовке к школе и развитию письменной речи.', 'Логопед-дефектолог и педагог по подготовке к школе и развитию письменной речи. Проводит очные и онлайн занятия в Белграде. Найдена в Telegram-канале. Подробности и актуальность контактов уточняйте у специалиста.', 'https://t.me/logoped_zhivanovich', null, null, null, null, null, null, null, 'approved', 180)
on conflict (id) do update set
  slug = excluded.slug, name = excluded.name, type = excluded.type, age_from = excluded.age_from, age_to = excluded.age_to,
  lang = excluded.lang, place = excluded.place, price = excluded.price, fee = excluded.fee, dur = excluded.dur,
  photo = excluded.photo, short = excluded.short, about = excluded.about, tg = excluded.tg, wa = excluded.wa, ig = excluded.ig,
  channel = excluded.channel, phone = excluded.phone, site = excluded.site, address = excluded.address, geo = excluded.geo,
  sort = excluded.sort, updated_at = now();
