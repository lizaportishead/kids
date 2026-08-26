# Telegram-бот для ручного добавления событий

Шлёшь боту текст или фото афиши → Claude разбирает в структуру события →
пишется в `events` со статусом `pending` → бот присылает превью с кнопками
«Опубликовать» / «Удалить». Пока не нажала «Опубликовать» — на сайте событие
не видно (`events_public` отдаёт только `status = 'approved'`).

## Разовая настройка

Всё ниже — команды в твоём терминале (не в Claude Code), нужны твои логины
в Telegram и Supabase.

### 1. Создать бота

В Telegram открой `@BotFather` → `/newbot` → следуй подсказкам. Сохрани токен
вида `123456:AAExxxxx…`.

### 2. Узнать свой chat_id

Напиши боту что угодно (любое сообщение), затем открой в браузере:

```
https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/getUpdates
```

В ответе найди `"chat":{"id": ЧИСЛО, ...}` — это `ALLOWED_CHAT_ID`. Он нужен,
чтобы бот реагировал только на тебя, а не на кого угодно, кто найдёт бота.

### 3. Установить Supabase CLI и подключиться к проекту

```bash
brew install supabase/tap/supabase
supabase login
supabase link --project-ref atteifmwatognibmzyac
```

### 4. Создать бакет для фото

Supabase Dashboard → Storage → New bucket → имя `event-photos`,
переключатель **Public** — включить.

### 5. Задать секреты функции

```bash
supabase secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  TELEGRAM_BOT_TOKEN=<токен из шага 1> \
  TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 24) \
  ALLOWED_CHAT_ID=<chat_id из шага 2>
```

`ANTHROPIC_API_KEY` — из [console.anthropic.com](https://console.anthropic.com)
(Settings → API Keys). Сохрани куда-нибудь значение `TELEGRAM_WEBHOOK_SECRET`,
оно понадобится в шаге 7.

### 6. Задеплоить функцию

```bash
supabase functions deploy telegram-bot --no-verify-jwt
```

`--no-verify-jwt` обязателен: Telegram не умеет посылать Supabase JWT,
а функция сама проверяет каждый запрос по `TELEGRAM_WEBHOOK_SECRET`.

### 7. Подписать бота на вебхук

```bash
curl "https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/setWebhook" \
  -d "url=https://atteifmwatognibmzyac.functions.supabase.co/telegram-bot" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET из шага 5>"
```

Должно вернуться `{"ok":true,"result":true,...}`.

### 8. Проверить

Напиши боту в Telegram что-то вроде:

> Мастер-класс по керамике, суббота в 11:00, Дом культуры, вход 1500 RSD, 5-10 лет

Через несколько секунд должно прийти превью с кнопками. Нажми «Опубликовать» —
событие появится на сайте (может понадобиться обновить страницу, кэш там
не участвует, читает Supabase напрямую).

Фото тоже работает — можно прислать скриншот поста или просто фото афиши
с подписью или без.

## Если что-то не так

```bash
supabase functions logs telegram-bot
```

Частые причины: не тот `secret_token` в `setWebhook`, не совпадает
`ALLOWED_CHAT_ID` (бот молчит на сообщения не от тебя — это нормально),
не создан бакет `event-photos` (фото не прикрепится, но событие всё равно
добавится, просто без картинки — на сайте для таких уже есть заглушка).
