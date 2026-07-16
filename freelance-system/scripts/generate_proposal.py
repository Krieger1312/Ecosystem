#!/usr/bin/env python3
"""
Слой 2: генерация заявки на основе few-shot из успешных прошлых заявок.

Реализует Точку подтверждения #1: при высокой уверенности — авто-отправка,
при пограничном скоре — помечается на подтверждение (см. confirmation_points.yaml).
"""

import argparse
import os
import yaml


def load_confirmation_thresholds(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def fetch_successful_examples(graphiti_url: str, job_category: str, n: int = 5) -> list[str]:
    """Заглушка: подтянуть N успешных заявок похожей категории из Graphiti."""
    raise NotImplementedError("Дописать запрос к Graphiti")


def generate_proposal(job: dict, examples: list[str]) -> dict:
    """Заглушка: вызов Claude с few-shot примерами, вернуть текст + confidence."""
    raise NotImplementedError("Дописать вызов Anthropic API")


def decide_auto_send(confidence: float, thresholds: dict) -> bool:
    """Точка подтверждения #1: решение об авто-отправке."""
    threshold = thresholds["confirmation_points"]["proposal"]["auto_send_min_confidence"]
    return confidence >= threshold


def save_application(job_id: str, proposal: dict, auto_sent: bool, conn_params: dict) -> str:
    """Заглушка: INSERT в freelance.applications, вернуть id заявки."""
    raise NotImplementedError("Дописать INSERT")


def push_to_decision_hub(application_id: str, job_title: str, confidence: float) -> None:
    """Интеграция с brain-core: регистрирует точку подтверждения #1
    в единой очереди Decision Hub, а не только локально в freelance.applications.

    Ставки низкие (см. docs/ARCHITECTURE.md) -> stakes='low'.
    Реальный вызов — brain-core/scripts/decision_hub.py add, либо через
    subprocess, либо прямым импортом, если оба пакета лежат рядом:

        subprocess.run([
            "python3", "../brain-core/scripts/decision_hub.py", "add",
            "--subsystem", "freelance", "--layer", "proposal",
            "--stakes", "low",
            "--summary", f"Заявка на '{job_title}' ждёт подтверждения (confidence={confidence:.2f})",
            "--payload", json.dumps({"application_id": application_id}),
        ], check=True)
    """
    raise NotImplementedError("Дописать вызов brain-core/scripts/decision_hub.py add")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--config", default=os.path.join(os.path.dirname(__file__), "..", "config", "confirmation_points.yaml")
    )
    parser.add_argument(
        "--graphiti-url", default=os.environ.get("GRAPHITI_URL", "http://localhost:8000")
    )
    args = parser.parse_args()

    thresholds = load_confirmation_thresholds(args.config)
    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    # NOTE: fetch_job_by_id — дописать аналогично другим SELECT в проекте
    job = {"id": args.job_id, "description": "...", "category": "..."}

    examples = fetch_successful_examples(args.graphiti_url, job["category"])
    proposal = generate_proposal(job, examples)
    auto_send = decide_auto_send(proposal["confidence"], thresholds)

    app_id = save_application(job["id"], proposal, auto_send, conn_params)

    if auto_send:
        print(f"[{app_id}] Уверенность {proposal['confidence']:.2f} >= порога — авто-отправка")
        # NOTE: дописать реальную отправку через API биржи, если доступен
    else:
        push_to_decision_hub(app_id, job.get("title", job["id"]), proposal["confidence"])
        print(f"[{app_id}] Уверенность {proposal['confidence']:.2f} < порога — "
              f"поставлено в очередь Decision Hub (brain-core)")


if __name__ == "__main__":
    main()
