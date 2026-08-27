# suggest-event — заявки с формы «Добавить событие»

Форма на сайте (`index.html`, кнопка «Добавить событие») отправляет сюда JSON:

```json
{ "link": "…", "when": "5 сентября в 17:00", "place": "…", "desc": "…", "page": "https://…" }
```

Функция пересылает это тебе в Telegram обычным текстовым сообщением. В базу
ничего не пишет, кнопок не добавляет — это просто уведомление. Что делать
с заявкой дальше, решаешь вручную.

## Разовая настройка

Всё ниже — команды в твоём терминале (не в Claude Code), нужны логины
в Telegram и Supabase.

### 1. Создать бота

В Telegram открой `@BotFather` → `/newbot` → следуй подсказкам. Сохрани токен
вида `123456:AAExxxxx…`.

### 2. Узнать свой chat_id

Напиши боту любое сообщение, затем открой в браузере:

```
https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/getUpdates
```

В ответе найди `"chat":{"id": ЧИСЛО, ...}` — это `ALLOWED_CHAT_ID`.

### 3. Задать секреты функции

```bash
supabase secrets set \
  TELEGRAM_BOT_TOKEN=<токен из шага 1> \
  ALLOWED_CHAT_ID=<chat_id из шага 2>
```

### 4. Задеплоить

```bash
supabase functions deploy suggest-event --no-verify-jwt
```

`--no-verify-jwt` обязателен: запрос идёт из браузера без Supabase JWT.

## Проверка

Открой сайт → «Добавить событие» → вставь ссылку или описание → «Отправить».
Через пару секунд в Telegram придёт сообщение с заявкой. Логи, если что-то
не так:

```bash
supabase functions logs suggest-event
```

## Адрес эндпоинта

`https://atteifmwatognibmzyac.functions.supabase.co/suggest-event`

Он зашит в `index.html` — константа `SUGGEST_ENDPOINT` в блоке
`<script type="text/x-dc">`. Если сменится project-ref, поправить там.

## Отчёт о ночном сборе

Второе Telegram-уведомление от системы — итог прогона коллектора (список
площадок и счётчики) — шлёт не эта функция, а сам коллектор:
`collector/lib/notify.mjs`, секреты `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
в GitHub Actions. Можно использовать того же бота и тот же chat_id.
