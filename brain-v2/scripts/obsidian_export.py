#!/usr/bin/env python3
"""
Экспорт памяти из Postgres/Graphiti в markdown-файлы для read-only витрины в Obsidian.

Это НЕ синхронизация в обе стороны — агенты пишут в Postgres/Graphiti,
этот скрипт только генерирует markdown-снимок для просмотра человеком.
Ручные правки в экспортированных файлах не сохраняются при следующем запуске.

Запуск: python3 obsidian_export.py --vault-path /path/to/obsidian/vault
Рекомендуется добавить в cron, например раз в час:
    0 * * * * /usr/bin/python3 /path/to/obsidian_export.py --vault-path /path/to/vault
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

# NOTE: заполнить реальными клиентами после разворачивания стека:
#   - psycopg2 / asyncpg для Postgres
#   - graphiti-core клиент для запроса фактов из Neo4j через Graphiti API
# Ниже — скелет с понятной структурой, чтобы Claude Code мог быстро
# дописать реальные запросы, зная актуальную схему БД.


def fetch_projects_from_postgres(conn_params: dict) -> list[dict]:
    """Заглушка: вернуть список проектов и их метаданных из Postgres."""
    raise NotImplementedError(
        "Дописать запрос к существующей схеме Postgres из Phase 1"
    )


def fetch_facts_from_graphiti(graphiti_url: str, project_id: str) -> list[dict]:
    """Заглушка: запросить факты/связи по проекту через Graphiti API."""
    raise NotImplementedError(
        "Дописать запрос к Graphiti REST API (см. docker/docker-compose.yml, порт 8000)"
    )


def render_project_markdown(project: dict, facts: list[dict]) -> str:
    """Собрать markdown-файл для одного проекта."""
    lines = [
        f"# {project.get('name', 'Без названия')}",
        "",
        f"> Автоматически сгенерировано {datetime.now(timezone.utc).isoformat()}. "
        "Не редактировать вручную — правки будут перезаписаны.",
        "",
        "## Текущий статус",
        "",
        project.get("status", "нет данных"),
        "",
        "## Факты и связи",
        "",
    ]
    for fact in facts:
        ts = fact.get("timestamp", "?")
        text = fact.get("text", "")
        lines.append(f"- [{ts}] {text}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-path", required=True, help="Путь к Obsidian vault")
    parser.add_argument(
        "--graphiti-url", default=os.environ.get("GRAPHITI_URL", "http://localhost:8000")
    )
    args = parser.parse_args()

    vault_path = Path(args.vault_path) / "brain-export"
    vault_path.mkdir(parents=True, exist_ok=True)

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    projects = fetch_projects_from_postgres(conn_params)
    for project in projects:
        facts = fetch_facts_from_graphiti(args.graphiti_url, project["id"])
        markdown = render_project_markdown(project, facts)
        out_file = vault_path / f"{project['id']}.md"
        out_file.write_text(markdown, encoding="utf-8")
        print(f"Экспортировано: {out_file}")


if __name__ == "__main__":
    main()
