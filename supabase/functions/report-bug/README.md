# report-bug — сообщения с формы «Сообщить об ошибке»

Ссылка «Сообщить об ошибке» в подвале сайта (`index.html`) открывает модалку
с тремя полями и отправляет сюда JSON:

```json
{
  "page": "https://…",          // страница с ошибкой, по умолчанию — текущая
  "desc": "что пошло не так",     // описание, обязательное
  "image": "<base64>",           // скриншот без data-URL префикса, необязательный
  "imageName": "screenshot.png",
  "imageType": "image/png"
}
```

Функция пересылает это в Telegram: со скриншотом — фотографией (`sendPhoto`,
текст в подписи), без — обычным сообщением (`sendMessage`). В базу ничего не
пишет — это просто уведомление.

Ограничения формы: скриншот до 5 МБ (Telegram принимает загрузку до 10 МБ).
Описание обрезается до 3000 символов, ссылка — до 1500.

## Разовая настройка

Всё ниже — команды в твоём терминале (не в Claude Code), нужны логины
в Telegram и Supabase.

### 1. Бот и chat_id

Можно взять тех же, что у `suggest-event` и ночного отчёта коллектора.
Если бота ещё нет: `@BotFather` → `/newbot`. `chat_id` — из
`https://api.telegram.org/bot<ТОКЕН>/getUpdates` после сообщения боту.

### 2. Задать секреты функции

```bash
supabase secrets set \
  TELEGRAM_BOT_TOKEN=<токен бота> \
  ALLOWED_CHAT_ID=<твой chat_id>
```

(Если секреты уже заданы для `suggest-event` — они общие на проект, повторять
не нужно.)

### 3. Задеплоить

```bash
supabase functions deploy report-bug --no-verify-jwt
```

`--no-verify-jwt` обязателен: запрос идёт из браузера без Supabase JWT.

## Проверка

Открой сайт → подвал → «Сообщить об ошибке» → опиши проблему, при желании
приложи скриншот → «Отправить». Через пару секунд в Telegram придёт
сообщение. Логи, если что-то не так:

```bash
supabase functions logs report-bug
```

## Адрес эндпоинта

`https://atteifmwatognibmzyac.functions.supabase.co/report-bug`

Он зашит в `index.html` — константа `REPORT_ENDPOINT` в блоке
`<script type="text/x-dc">`, рядом с `SUGGEST_ENDPOINT`. Если сменится
project-ref, поправить там.
