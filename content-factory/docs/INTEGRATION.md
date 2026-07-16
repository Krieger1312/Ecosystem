# Интеграция с brain-core / brain-v2

## Онтология

Зритель контента — `Actor` с `role="content_viewer"` (см.
`brain-core/config/ontology_types.yaml`). Тема/сценарий/публикация —
`Decision` с `subsystem="content"`.

## Decision Hub

`generate_concept.py` и `publish_gate.py` пишут точки подтверждения
через `brain-core/scripts/decision_hub.py add --subsystem content`,
так же как freelance-system — единая очередь, единая приоритизация.

## Outcome — вариант time_series

В отличие от freelance (`binary` вариант Outcome), контент использует
`time_series`: `track_metrics.py` пишет строки в `content.metrics_timeseries`
с `metric_name`/`value`/`measured_at`, а не единый финальный статус.

## Логирование LLM

Все вызовы Claude/Deepseek в скриптах этого пакета оборачиваются через
`brain-core/scripts/llm_usage_logger.py` с `subsystem="content"` —
продакшен видео (озвучка, сборка) может быть заметно дороже по токенам,
чем фриланс-заявки, стоит следить через `budget_dashboard.py` отдельно
по этому тегу.

## Обязательное условие перед стартом

Прежде чем `track_metrics.py` начинает писать факты в Graphiti в проде —
`extraction_quality_test.py` из brain-core должен быть пройден
(это общее требование для любой новой подсистемы, не специфичное для
контента, но важно не забыть, раз это первая подсистема после freelance).
