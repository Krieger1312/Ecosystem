#!/usr/bin/env python3
"""
Слой 3: уточнение требований → PRD → технический дизайн → оценка.

Паттерн из shinpr-boilerplate: scope-discoverer -> PRD-creator ->
technical-designer, адаптированный под фриланс-контекст (после победы
в тендере, до начала кодирования).

Точка подтверждения #2 — здесь ВСЕГДА требуется подтверждение
(always_confirm: true в конфиге), независимо от уверенности модели.
"""

import argparse
import os


def discover_scope(client_brief: str) -> str:
    """Заглушка: классифицировать объём задачи (small/medium/large),
    как scope-discoverer в shinpr-паттерне."""
    raise NotImplementedError("Дописать вызов Claude для классификации объёма")


def generate_prd(client_brief: str, scope: str) -> str:
    """Заглушка: сформировать PRD — что нужно, граничные случаи, что не входит."""
    raise NotImplementedError("Дописать вызов Claude для генерации PRD")


def generate_technical_design(prd: str) -> str:
    """Заглушка: технический дизайн на основе PRD."""
    raise NotImplementedError("Дописать вызов Claude для дизайна")


def estimate_scope_and_timeline(prd: str, design: str) -> dict:
    """Заглушка: оценка объёма работы и сроков."""
    raise NotImplementedError("Дописать оценку")


def save_plan_for_confirmation(job_id: str, prd: str, design: str, estimate: dict, conn_params: dict) -> str:
    """Заглушка: сохранить план, пометить как требующий подтверждения
    (always_confirm — см. docs/ARCHITECTURE.md, Точка подтверждения #2)."""
    raise NotImplementedError("Дописать сохранение")


def push_to_decision_hub(plan_id: str, job_id: str, scope: str, estimate: dict) -> None:
    """Интеграция с brain-core: Точка подтверждения #2 всегда идёт в
    Decision Hub со stakes='high' — независимо от объёма (always_confirm
    в config/confirmation_points.yaml дублируется этим stakes уровнем,
    так что Decision Hub тоже ставит её в приоритет).

        subprocess.run([
            "python3", "../brain-core/scripts/decision_hub.py", "add",
            "--subsystem", "freelance", "--layer", "plan",
            "--stakes", "high",
            "--summary", f"План по заказу {job_id} готов ({scope}), нужна оценка объёма/сроков",
            "--payload", json.dumps({"plan_id": plan_id, "estimate": estimate}),
        ], check=True)
    """
    raise NotImplementedError("Дописать вызов brain-core/scripts/decision_hub.py add")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--client-brief-file", required=True, help="Путь к файлу с брифом от клиента")
    args = parser.parse_args()

    with open(args.client_brief_file) as f:
        client_brief = f.read()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    scope = discover_scope(client_brief)
    prd = generate_prd(client_brief, scope)
    design = generate_technical_design(prd)
    estimate = estimate_scope_and_timeline(prd, design)

    plan_id = save_plan_for_confirmation(args.job_id, prd, design, estimate, conn_params)
    push_to_decision_hub(plan_id, args.job_id, scope, estimate)
    print(f"[{plan_id}] План готов, объём: {scope}. "
          f"Поставлено в очередь Decision Hub (brain-core), stakes=high.")


if __name__ == "__main__":
    main()
