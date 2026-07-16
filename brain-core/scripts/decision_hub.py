#!/usr/bin/env python3
"""
Decision Hub — единая точка, куда стекаются все pending-решения из любой
подсистемы (freelance, content, будущий godot и т.д.), с приоритизацией
по цене ошибки, а не по времени поступления.

Использование:
  Подсистема добавляет решение:
    python3 decision_hub.py add --subsystem freelance --layer plan \\
        --stakes high --summary "План по заказу X готов, нужна оценка"

  Ты просматриваешь очередь:
    python3 decision_hub.py list

  Ты разрешаешь решение:
    python3 decision_hub.py resolve --id <uuid> --action approved
"""

import argparse
import json
import os


STAKES_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def add_decision(subsystem: str, layer: str, stakes: str, summary: str,
                  payload: dict | None, conn_params: dict) -> str:
    """Заглушка: INSERT в brain.pending_decisions, вернуть id."""
    raise NotImplementedError("Дописать INSERT")


def list_pending(conn_params: dict) -> list[dict]:
    """Заглушка: SELECT все status='pending', отсортировать по stakes
    через STAKES_PRIORITY, затем по created_at."""
    raise NotImplementedError("Дописать SELECT с ORDER BY")


def resolve_decision(decision_id: str, action: str, reason: str | None,
                      conn_params: dict) -> None:
    """Заглушка: UPDATE status/resolution_reason/resolved_at."""
    raise NotImplementedError("Дописать UPDATE")


def notify_if_needed(conn_params: dict, notify_webhook: str | None) -> None:
    """Заглушка: если есть новые pending с stakes='high' — отправить
    одно агрегированное уведомление (не по одному на каждое решение)."""
    raise NotImplementedError(
        "Дописать агрегированное уведомление, напр. в Telegram через webhook"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--subsystem", required=True)
    p_add.add_argument("--layer", required=True)
    p_add.add_argument("--stakes", choices=["low", "medium", "high"], default="medium")
    p_add.add_argument("--summary", required=True)
    p_add.add_argument("--payload", help="JSON-строка с деталями")

    p_list = sub.add_parser("list")

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--id", required=True)
    p_resolve.add_argument("--action", choices=["approved", "edited", "rejected"], required=True)
    p_resolve.add_argument("--reason")

    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    if args.command == "add":
        payload = json.loads(args.payload) if args.payload else None
        decision_id = add_decision(
            args.subsystem, args.layer, args.stakes, args.summary, payload, conn_params
        )
        print(f"Добавлено: {decision_id}")
        notify_if_needed(conn_params, os.environ.get("DECISION_HUB_WEBHOOK"))

    elif args.command == "list":
        decisions = list_pending(conn_params)
        for d in decisions:
            print(f"[{d['stakes']:>6}] {d['subsystem']}/{d['layer']}: {d['summary']} ({d['id']})")

    elif args.command == "resolve":
        resolve_decision(args.id, args.action, args.reason, conn_params)
        print(f"Решение {args.id} -> {args.action}")


if __name__ == "__main__":
    main()
