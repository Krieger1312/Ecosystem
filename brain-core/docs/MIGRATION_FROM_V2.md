# Миграция freelance-system на brain-core

freelance-system уже работает со своей локальной схемой `freelance.*`.
brain-core не заменяет её — добавляет общий слой сверху. Изменения
минимальны и не ломают то, что уже написано.

## Что меняется

1. **Точки подтверждения** — `generate_proposal.py`, `plan_project.py`,
   `qa_review.py` из freelance-system при создании точки подтверждения
   теперь ДОПОЛНИТЕЛЬНО вызывают `brain-core/scripts/decision_hub.py add`
   (не вместо записи в `freelance.decisions`, а вместе с ней — старая
   таблица остаётся источником детальных данных, Decision Hub — только
   для агрегированной очереди и приоритизации).

2. **Логирование LLM** — везде, где freelance-system вызывает
   Anthropic/Deepseek API, оборачивается через
   `brain-core/scripts/llm_usage_logger.py` с `subsystem="freelance"`.

3. **Онтология в Graphiti** — факты, которые freelance-system пишет в
   Graphiti (успешные заявки, red flags), используют типы из
   `config/ontology_types.yaml` — в частности, клиент фрилансера
   теперь явно помечается как `Actor` с `role="freelance_client"`,
   а не безымянным узлом.

## Что НЕ меняется

- Схема `freelance.jobs/applications/outcomes` остаётся как есть
- Логика скоринга, генерации заявок, планирования — без изменений
- Пороги в `confirmation_points.yaml` продолжают работать как раньше —
  Decision Hub только агрегирует то, что уже решено этими порогами,
  не заменяет их логику

## Порядок миграции

1. Накатить `brain-core/db/core_schema.sql`
2. Прогнать `extraction_quality_test.py` на реальных диалогах фриланс-переписки
3. Добавить вызовы `decision_hub.py add` в существующие скрипты freelance-system
   в местах, где сейчас просто печатается "ТРЕБУЕТСЯ ТВОЁ ПОДТВЕРЖДЕНИЕ"
4. Обернуть вызовы LLM через `llm_usage_logger.py`
5. Проверить `budget_dashboard.py` показывает данные по `subsystem='freelance'`
