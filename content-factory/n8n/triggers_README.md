# n8n — только триггеры (как и в freelance-system)

## Что настроить

1. **Cron** раз в день → `scripts/track_metrics.py --check-due`
2. **Webhook/уведомление** — при новых pending в Decision Hub с
   `subsystem='content'` (переиспользует общий канал из brain-core,
   не отдельный)

## Что НЕ автоматизируется через n8n

- Запуск `trend_watch.py` и `generate_concept.py` — ручные инструменты,
  вызываются тобой напрямую или через Claude Code, не по расписанию
- Публикация — только через явный `--confirm` после approve в Decision Hub,
  никаких n8n-нод, которые могли бы случайно нажать "опубликовать"
