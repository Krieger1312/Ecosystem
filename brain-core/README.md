# brain-core — фундаментальный слой протокола

Достраивает недостающие слои 0-4 поверх уже развёрнутого brain-v2
(Graphiti + Postgres): единая онтология, Decision Hub, мониторинг/бюджет,
устойчивость (backup/recovery), проверка качества извлечения на русском.

Не заменяет brain-v2 — подключается к нему. freelance-system переподключается
на этот пакет; контент-фабрика и будущие подсистемы строятся поверх него
с самого начала, а не рядом.

## Состав

```
brain-core/
├── README.md
├── docs/
│   ├── ONTOLOGY.md              — единый словарь сущностей (Actor/Decision/Outcome)
│   └── MIGRATION_FROM_V2.md     — как freelance-system переподключается
├── db/
│   └── core_schema.sql          — схема brain: actors, pending_decisions, llm_usage_log
├── scripts/
│   ├── decision_hub.py          — Слой 1: единая точка подтверждений
│   ├── llm_usage_logger.py      — Слой 2: логирование каждого вызова LLM
│   ├── budget_dashboard.py      — Слой 2: дневной/недельный отчёт трат
│   ├── backup.sh                — Слой 3: дамп Postgres + экспорт Neo4j
│   ├── RESTORE_RUNBOOK.md       — Слой 3: пошаговое восстановление
│   └── extraction_quality_test.py — Слой 4: тест извлечения фактов на русском
└── config/
    └── ontology_types.yaml      — формальное определение типов сущностей
```

## Порядок разворачивания

1. **db/core_schema.sql** — накатить поверх существующего Postgres из brain-v2
2. **scripts/extraction_quality_test.py** — прогнать ПЕРВЫМ, до того как
   что-либо ещё пишет в Graphiti в проде. Если качество извлечения на
   русском окажется низким — сначала чинить это, потом продолжать
3. **scripts/decision_hub.py** — развернуть до того, как контент-фабрика
   начнёт генерировать свои точки подтверждения
4. **scripts/llm_usage_logger.py** + **budget_dashboard.py** — обернуть
   существующие вызовы Claude/Deepseek в freelance-system этим логгером
5. **backup.sh** — поставить в cron сразу, не откладывать

## Обязательный контракт для любой новой подсистемы

Прежде чем подсистема (freelance, контент, Godot, что угодно следующее)
начинает писать в общую память, она обязана:
1. Использовать типы из `config/ontology_types.yaml`, не свои
2. Писать точки подтверждения в `brain.pending_decisions`, не в свой канал
3. Оборачивать вызовы LLM через `llm_usage_logger.py`
4. Пройти `extraction_quality_test.py` на своих реальных данных перед продом
