#!/usr/bin/env python3
"""
Тест качества извлечения фактов Graphiti на русскоязычных диалогах
с техническим жаргоном — ПРОГНАТЬ ПЕРВЫМ, до продакшен-использования
Graphiti любой новой подсистемой.

Как использовать:
1. Собери 20-30 реальных диалогов (свои переписки/заметки на русском,
   с техническим жаргоном, характерным для твоей работы) в
   sample_dialogues.jsonl — по одному диалогу на строку в формате:
   {"text": "...", "expected_facts": ["факт 1", "факт 2", ...]}

2. Запусти: python3 extraction_quality_test.py --samples sample_dialogues.jsonl

3. Скрипт прогонит каждый диалог через Graphiti, сравнит извлечённые
   факты с ожидаемыми (вручную заданными тобой), посчитает точность.

4. Результат пишется в brain.extraction_quality_runs — чтобы видеть
   тренд качества со временем, а не только разовый прогон.
"""

import argparse
import json
import os


def load_samples(path: str) -> list[dict]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def extract_facts_via_graphiti(graphiti_url: str, text: str) -> list[str]:
    """Заглушка: отправить текст в Graphiti, получить извлечённые факты."""
    raise NotImplementedError("Дописать вызов Graphiti API (порт 8000)")


def compare_facts(extracted: list[str], expected: list[str]) -> tuple[int, int]:
    """Заглушка: сравнить извлечённые факты с ожидаемыми.

    Точное текстовое совпадение — плохая метрика для этой задачи
    (разные формулировки одного факта). Реалистичнее — прогнать через
    Claude с промптом вроде "эти два списка фактов семантически
    эквивалентны? да/нет для каждой пары" и вручную просмотреть
    результат на первых прогонах, прежде чем доверять автоматике.
    """
    raise NotImplementedError("Дописать сравнение (желательно semantic, не строковое)")


def save_run_result(sample_size: int, correct: int, notes: str, conn_params: dict) -> None:
    """Заглушка: INSERT в brain.extraction_quality_runs."""
    raise NotImplementedError("Дописать INSERT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", required=True, help="Путь к sample_dialogues.jsonl")
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

    samples = load_samples(args.samples)
    if len(samples) < 20:
        print(f"ВНИМАНИЕ: только {len(samples)} примеров, рекомендуется минимум 20-30 "
              "для статистически значимого результата.")

    total_correct = 0
    total_expected = 0
    for sample in samples:
        extracted = extract_facts_via_graphiti(args.graphiti_url, sample["text"])
        correct, expected_count = compare_facts(extracted, sample["expected_facts"])
        total_correct += correct
        total_expected += expected_count

    accuracy = total_correct / total_expected if total_expected else 0.0
    print(f"Точность извлечения: {accuracy:.1%} ({total_correct}/{total_expected})")

    if accuracy < 0.7:
        print("⚠️  Точность ниже 70% — стоит доработать предобработку "
              "(явная инструкция на русском для Graphiti/Deepseek) перед "
              "тем, как масштабировать на новую подсистему.")

    save_run_result(len(samples), total_correct, f"accuracy={accuracy:.3f}", conn_params)


if __name__ == "__main__":
    main()
