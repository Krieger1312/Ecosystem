#!/usr/bin/env python3
"""
Слой 2: генерация концепции/сценария на основе брифа + разборов трендов.

Точка подтверждения: пишет в Decision Hub (brain-core), ждёт твоего
approve/reject перед тем, как продакшен-слой начнёт работу.
"""

import argparse
import os


def fetch_relevant_trend_analyses(conn_params: dict, platform: str, n: int = 5) -> list[dict]:
    """Заглушка: подтянуть последние N разборов трендов для площадки."""
    raise NotImplementedError("Дописать SELECT из content.trend_analyses")


def generate_script(brief: str, trend_context: list[dict], platform: str) -> dict:
    """Заглушка: вызов Claude — сценарий + заголовок под площадку."""
    raise NotImplementedError("Дописать вызов Anthropic API")


def save_idea(title: str, script: str, platform: str, trend_id: str | None, conn_params: dict) -> str:
    """Заглушка: INSERT в content.ideas со статусом 'draft'."""
    raise NotImplementedError("Дописать INSERT")


def push_to_decision_hub(idea_id: str, title: str) -> None:
    """Заглушка: вызвать brain-core/scripts/decision_hub.py add
    --subsystem content --layer concept --stakes medium."""
    raise NotImplementedError(
        "Дописать вызов decision_hub.py add (subprocess или прямой импорт)"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief-file", required=True)
    parser.add_argument("--platform", choices=["youtube", "tiktok", "both"], required=True)
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    with open(args.brief_file, encoding="utf-8") as f:
        brief = f.read()

    trend_context = fetch_relevant_trend_analyses(conn_params, args.platform)
    result = generate_script(brief, trend_context, args.platform)

    idea_id = save_idea(
        result["title"], result["script"], args.platform,
        result.get("based_on_trend_id"), conn_params
    )
    push_to_decision_hub(idea_id, result["title"])

    print(f"Идея сохранена: {idea_id}, ждёт подтверждения в Decision Hub.")


if __name__ == "__main__":
    main()
