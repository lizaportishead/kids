# suggest-event — заявки с формы «Добавить событие»

Форма на сайте (`index.html`, кнопка «Добавить событие») отправляет сюда JSON:

```json
{ "link": "…", "when": "5 сентября в 17:00", "place": "…", "desc": "…", "page": "https://…" }
```

Функция пересылает это тебе в Telegram обычным сообщением. В базу ничего не
пишет — это уведомление. Дальше можно переслать текст telegram-боту, он
разберёт событие в структуру и предложит на публикацию.

## Разовая настройка

Секреты уже заданы для функции `telegram-bot` (`TELEGRAM_BOT_TOKEN`,
`ALLOWED_CHAT_ID`) и общие для всего проекта — отдельно ставить не нужно.
Если `telegram-bot` ещё не настраивала, сделай шаги 1–2 и 5 из
`../telegram-bot/README.md`.

Задеплоить:

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
