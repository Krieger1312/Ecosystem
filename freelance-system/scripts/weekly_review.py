#!/usr/bin/env python3
"""
Еженедельная ревизия: анализ решений за период, поиск паттернов ошибок,
предложения по правкам промптов/few-shot примеров.

Механизм самоулучшения #3 из docs/IMPROVEMENT_LOOP.md.
Deepseek делает массовый анализ (дёшево), Claude формулирует конкретные
предложения. Изменения НЕ применяются автоматически — только отчёт.

Запуск: раз в 2-4 недели, вручную или через cron.
"""

import argparse
import os
from datetime import datetime, timedelta, timezone


def fetch_period_decisions(conn_params: dict, since: datetime) -> list[dict]:
    """Заглушка: выбрать все decisions + outcomes за период."""
    raise NotImplementedError("Дописать SELECT с JOIN decisions + outcomes")


def analyze_patterns_deepseek(decisions: list[dict]) -> dict:
    """Заглушка: массовый анализ через Deepseek — какие формулировки
    заявок выигрывали чаще, какие типы вакансий скорились неправильно."""
    raise NotImplementedError("Дописать вызов Deepseek API")


def formulate_prompt_changes_claude(patterns: dict) -> str:
    """Заглушка: Claude превращает найденные паттерны в конкретные
    предложения по правкам промптов — текстовый отчёт, не авто-применение."""
    raise NotImplementedError("Дописать вызов Anthropic API")


def save_review_report(report: str, output_dir: str) -> str:
    path = os.path.join(output_dir, f"review_{datetime.now(timezone.utc):%Y%m%d}.md")
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=21, help="Период анализа в днях")
    parser.add_argument("--output-dir", default="./reviews")
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    decisions = fetch_period_decisions(conn_params, since)

    if not decisions:
        print("Недостаточно данных за период — пропускаем ревизию.")
        return

    patterns = analyze_patterns_deepseek(decisions)
    report = formulate_prompt_changes_claude(patterns)
    report_path = save_review_report(report, args.output_dir)

    print(f"Отчёт готов: {report_path}")
    print("Изменения НЕ применены автоматически — просмотри и примени вручную.")


if __name__ == "__main__":
    main()
