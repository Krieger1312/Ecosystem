#!/usr/bin/env python3
"""
Слой 6: пост-публикационный цикл — подтягивает метрики через API площадок
через 1 день / 1 неделю / 1 месяц после публикации, пишет как временной
ряд, связывает с решениями из Слоя 2 через Graphiti.

Единственный настоящий источник самоулучшения для контента.
Уровень автоматизации: полностью автоматизировано с первого дня.

Запуск: через cron ежедневно.
    python3 track_metrics.py --check-due
"""

import argparse
import os
from datetime import datetime, timedelta, timezone


CHECK_INTERVALS_DAYS = [1, 7, 30]  # через сколько дней после публикации проверять


def fetch_publications_due_for_check(conn_params: dict) -> list[dict]:
    """Заглушка: выбрать публикации, для которых наступил один из
    CHECK_INTERVALS_DAYS с момента published_at и метрика ещё не снята
    за этот интервал."""
    raise NotImplementedError("Дописать SELECT с логикой интервалов")


def fetch_metrics_from_platform(platform: str, platform_post_id: str) -> dict:
    """Заглушка: запрос метрик через YouTube Data API / TikTok API
    (views, retention_pct, ctr, likes, comments — что доступно по API)."""
    raise NotImplementedError("Дописать вызов API площадки")


def save_metrics(publication_id: str, metrics: dict, conn_params: dict) -> None:
    """Заглушка: INSERT в content.metrics_timeseries, по строке на метрику."""
    raise NotImplementedError("Дописать INSERT (по одной строке на metric_name)")


def sync_significant_pattern_to_graphiti(graphiti_url: str, idea_id: str,
                                          metrics: dict) -> None:
    """Заглушка: если метрики значимо отклоняются от среднего (сильно
    выше/ниже) — записать в Graphiti как факт "тема X с хуком Y дала
    результат Z" для будущего few-shot в generate_concept.py."""
    raise NotImplementedError("Дописать условие значимости + запрос к Graphiti")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-due", action="store_true")
    parser.add_argument(
        "--graphiti-url", default=os.environ.get("GRAPHITI_URL", "http://localhost:8000")
    )
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    if not args.check_due:
        print("Укажи --check-due для запуска проверки.")
        return

    due = fetch_publications_due_for_check(conn_params)
    for pub in due:
        metrics = fetch_metrics_from_platform(pub["platform"], pub["platform_post_id"])
        save_metrics(pub["id"], metrics, conn_params)
        sync_significant_pattern_to_graphiti(args.graphiti_url, pub["idea_id"], metrics)

    print(f"Проверено публикаций: {len(due)}")


if __name__ == "__main__":
    main()
