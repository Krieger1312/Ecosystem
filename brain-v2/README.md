# Мозг v2 — Phase 1 (пересмотренная архитектура)

Пакет для деплоя обновлённой архитектуры единой системы памяти и оркестрации.
Заменяет Obsidian-как-источник-правды и n8n-как-оркестратор на специализированные
компоненты, оставляя Postgres как фундамент.

## Состав пакета

```
brain-v2/
├── README.md                  — этот файл
├── docker/
│   ├── docker-compose.yml     — Postgres+pgvector, Neo4j (для Graphiti), Graphiti API
│   └── .env.example           — шаблон переменных окружения
├── docs/
│   ├── ARCHITECTURE.md        — полное описание архитектуры по слоям
│   ├── MIGRATION_PLAN.md      — поэтапный план миграции с текущей системы
│   └── DECISIONS.md           — почему выбраны именно эти компоненты (для истории)
└── scripts/
    ├── setup_vps.sh           — установка Docker + запуск стека на VPS
    └── obsidian_export.py     — экспорт памяти из Postgres в markdown (read-only витрина)
```

## Быстрый старт

1. Скопируй `docker/.env.example` → `docker/.env`, заполни ключи (Neo4j пароль, Anthropic/Deepseek API-ключи)
2. На VPS: `bash scripts/setup_vps.sh`
3. `cd docker && docker compose up -d`
4. Проверь, что Graphiti API отвечает: `curl http://localhost:8000/healthcheck`
5. Дальше — по `docs/MIGRATION_PLAN.md`, начиная с одного проекта (биддинг-агент), не всей системы разом

## Важное техническое уточнение

Graphiti (движок temporal knowledge graph) использует **Neo4j** как графовую БД,
а не сам Postgres напрямую — это отдельный контейнер в docker-compose. Postgres/pgvector
остаётся как было: для векторного поиска и реляционных данных проектов. Они работают
рядом, не вместо друг друга.

См. `docs/ARCHITECTURE.md` для полной картины.
