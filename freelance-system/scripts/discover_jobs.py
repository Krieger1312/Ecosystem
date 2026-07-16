#!/usr/bin/env python3
"""
Слой 1: обнаружение вакансий из RSS/API источников.

Намеренно не включает скрапинг Upwork напрямую (риск бана аккаунта на
старте) — только официальные RSS/API. Расширяй список источников по мере
наработки репутации на площадках.

Запуск: python3 discover_jobs.py
Рекомендуется через cron каждые 15-30 минут.
"""

import argparse
import os
from datetime import datetime, timezone


def fetch_upwork_rss(feed_url: str) -> list[dict]:
    """Заглушка: распарсить Upwork RSS-фид в список вакансий.

    Реальная реализация — feedparser или аналог, без авторизации не нужен.
    """
    raise NotImplementedError("Дописать парсинг RSS-фида")


def fetch_other_sources() -> list[dict]:
    """Заглушка: другие источники с официальным API (Freelancer.com API,
    Toptal и т.д., если применимо к твоей нише)."""
    raise NotImplementedError("Дописать под конкретные источники, актуальные для тебя")


def save_to_postgres(jobs: list[dict], conn_params: dict) -> int:
    """Заглушка: вставить новые вакансии в freelance.jobs,
    дедупликация по (source, external_id) через UNIQUE constraint из schema.sql."""
    raise NotImplementedError("Дописать INSERT ... ON CONFLICT DO NOTHING")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upwork-rss-url",
        default=os.environ.get("UPWORK_RSS_URL"),
        help="URL RSS-фида Upwork под твои ключевые запросы",
    )
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    all_jobs = []
    if args.upwork_rss_url:
        all_jobs.extend(fetch_upwork_rss(args.upwork_rss_url))
    all_jobs.extend(fetch_other_sources())

    inserted = save_to_postgres(all_jobs, conn_params)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Новых вакансий: {inserted}")


if __name__ == "__main__":
    main()
