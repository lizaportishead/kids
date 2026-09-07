# API-документация

- **`openapi.yaml`** — спецификация OpenAPI 3.1. Единственный источник правды.
  Покрывает:
  - `POST /suggest-event` — заявка с формы «Добавить событие» (edge-функция);
  - `GET /rest/v1/events_public` — чтение одобренных событий (PostgREST);
  - `POST /rest/v1/rpc/upsert_events` — запись из ночного коллектора (service_role);
  - `GET /data/events.json` — статический фид, который читает сайт.
- **`api.html`** — просмотрщик на Redoc.

## Как посмотреть

Спека самодостаточна — можно просто открыть `openapi.yaml`:

- вставить в <https://editor.swagger.io/>;
- плагином IDE (OpenAPI (Swagger) Editor для VS Code, встроенный во JetBrains).

Локальный рендер через `api.html` (нужен HTTP и интернет для CDN Redoc):

```bash
cd docs && python3 -m http.server 8080
# → http://localhost:8080/api.html
```

## Держать в актуальном состоянии

Спека написана вручную, автогенерации нет. При изменении контракта править `openapi.yaml`:

| Что меняется | Где в коде | Что поправить в спеке |
| --- | --- | --- |
| Поля формы заявки | `supabase/functions/suggest-event/index.ts` | `SuggestRequest`, коды ответов |
| Колонки события | `db/schema.sql` (view `events_public`) | `EventPublic` |
| Строка upsert | `collector/lib/supabase.mjs` (`rowOf`) | `EventUpsertRow` |
| Формат `events.json` | `collector/index.mjs` | `EventsFeed`, `RunReportItem` |
| project-ref Supabase | `index.html` (`SUGGEST_ENDPOINT`) | `servers` |
