#!/usr/bin/env python3
"""
Слой 5: финальная проверка перед сдачей клиенту.

Точка подтверждения #3 — всегда требует подтверждения, самая важная
точка во всей системе (см. docs/ARCHITECTURE.md).
"""

import argparse
import os
import subprocess


def run_tests(project_path: str) -> dict:
    """Заглушка: запустить тесты проекта, вернуть результат.

    Реальная реализация зависит от стека — pytest/npm test/etc.
    """
    raise NotImplementedError("Дописать под конкретный стек проекта")


def run_code_review(project_path: str) -> str:
    """Заглушка: вызвать Claude для code-review изменений
    (можно переиспользовать логику engineering:code-review skill)."""
    raise NotImplementedError("Дописать вызов Claude для ревью")


def generate_demo_materials(project_path: str, output_dir: str) -> list[str]:
    """Заглушка: сгенерировать скриншоты/запись демо для пакета сдачи клиенту."""
    raise NotImplementedError("Дописать генерацию (Playwright для скриншотов веб-проектов и т.д.)")


def compile_delivery_package(job_id: str, test_results: dict, review: str, demo_files: list[str]) -> str:
    """Заглушка: собрать всё в единый отчёт для тебя перед отправкой клиенту."""
    raise NotImplementedError("Дописать сборку отчёта")


def push_to_decision_hub(job_id: str, report_path: str) -> None:
    """Интеграция с brain-core: Точка подтверждения #3 — самая важная
    во всей системе, stakes='high' всегда.

        subprocess.run([
            "python3", "../brain-core/scripts/decision_hub.py", "add",
            "--subsystem", "freelance", "--layer", "delivery",
            "--stakes", "high",
            "--summary", f"Пакет сдачи по заказу {job_id} готов, отчёт: {report_path}",
            "--payload", json.dumps({"job_id": job_id, "report_path": report_path}),
        ], check=True)
    """
    raise NotImplementedError("Дописать вызов brain-core/scripts/decision_hub.py add")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--output-dir", default="./delivery")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    test_results = run_tests(args.project_path)
    review = run_code_review(args.project_path)
    demo_files = generate_demo_materials(args.project_path, args.output_dir)

    report_path = compile_delivery_package(args.job_id, test_results, review, demo_files)
    push_to_decision_hub(args.job_id, report_path)
    print(f"Отчёт готов: {report_path}")
    print("Поставлено в очередь Decision Hub (brain-core), stakes=high. "
          "ТРЕБУЕТСЯ ТВОЁ ПОДТВЕРЖДЕНИЕ перед отправкой клиенту.")


if __name__ == "__main__":
    main()
