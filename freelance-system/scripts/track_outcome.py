#!/usr/bin/env python3
"""
Трекинг исходов через время (won/lost/delivered/client_revision_requested).

Механизм самоулучшения #2 из docs/IMPROVEMENT_LOOP.md — разделяет
"что сработало" от "что просто произошло".

Запуск через cron раз в день, плюс ручная команда для быстрой пометки:
    python3 track_outcome.py --application-id <id> --status won
"""

import argparse
import os


def check_outcomes_via_api(conn_params: dict) -> int:
    """Заглушка: там, где биржа даёт API статуса тендера — сверить
    автоматически pending-заявки."""
    raise NotImplementedError("Дописать под конкретные API, где доступны")


def mark_outcome(application_id: str, status: str, satisfaction: float | None,
                  notes: str | None, conn_params: dict) -> None:
    """Заглушка: UPDATE freelance.outcomes, плюс синхронизация значимых
    исходов в Graphiti (см. sync_to_graphiti)."""
    raise NotImplementedError("Дописать UPDATE + вызов sync_to_graphiti при значимых исходах")


def sync_to_graphiti(graphiti_url: str, application_id: str, status: str, notes: str | None) -> None:
    """Заглушка: записать факт исхода в Graphiti с временной меткой —
    это то, что делает возможным few-shot генерацию на успешных примерах
    в generate_proposal.py."""
    raise NotImplementedError("Дописать запрос к Graphiti API")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-id")
    parser.add_argument("--status", choices=["won", "lost", "delivered", "client_revision_requested"])
    parser.add_argument("--satisfaction", type=float, help="1-5, если применимо")
    parser.add_argument("--notes")
    parser.add_argument("--auto-check", action="store_true", help="Автосверка через API бирж")
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

    if args.auto_check:
        updated = check_outcomes_via_api(conn_params)
        print(f"Автоматически обновлено исходов: {updated}")
        return

    if not args.application_id or not args.status:
        parser.error("Для ручной пометки нужны --application-id и --status")

    mark_outcome(args.application_id, args.status, args.satisfaction, args.notes, conn_params)
    sync_to_graphiti(args.graphiti_url, args.application_id, args.status, args.notes)
    print(f"Исход записан: {args.application_id} -> {args.status}")


if __name__ == "__main__":
    main()
