#!/usr/bin/env python3
"""
Простой текстовый отчёт трат по подсистемам за период, с алертом при
аномальном расходе (не абсолютный лимит, а отклонение от нормы).

Запуск: python3 budget_dashboard.py --days 7
Рекомендуется в cron ежедневно, с выводом в тот же канал, что Decision Hub.
"""

import argparse
import os
from datetime import datetime, timedelta, timezone


def fetch_usage_by_subsystem(conn_params: dict, since: datetime) -> list[dict]:
    """Заглушка: SUM(estimated_cost_usd) GROUP BY subsystem за период."""
    raise NotImplementedError("Дописать агрегирующий SELECT")


def fetch_daily_baseline(conn_params: dict, lookback_days: int = 30) -> float:
    """Заглушка: средний дневной расход за последние N дней —
    база для сравнения аномалий."""
    raise NotImplementedError("Дописать расчёт среднего")


def detect_anomaly(today_cost: float, baseline: float, threshold_multiplier: float = 3.0) -> bool:
    """Простое правило: сегодняшний расход в N раз выше среднего —
    не строгая ML-аномалия, но достаточно для раннего сигнала."""
    if baseline == 0:
        return False
    return today_cost > baseline * threshold_multiplier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    usage = fetch_usage_by_subsystem(conn_params, since)

    print(f"=== Расходы за последние {args.days} дней ===")
    total = 0.0
    for row in usage:
        print(f"  {row['subsystem']:>12}: ${row['total_cost']:.2f}")
        total += row["total_cost"]
    print(f"  {'ИТОГО':>12}: ${total:.2f}")

    baseline = fetch_daily_baseline(conn_params)
    today_cost = total / max(args.days, 1)  # грубая оценка среднего за день в периоде
    if detect_anomaly(today_cost, baseline):
        print(f"\n⚠️  АНОМАЛИЯ: средний расход за период (${today_cost:.2f}/день) "
              f"значительно выше базового (${baseline:.2f}/день)")


if __name__ == "__main__":
    main()
