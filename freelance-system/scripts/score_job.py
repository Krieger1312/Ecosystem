#!/usr/bin/env python3
"""
Слой 1: скоринг вакансий по профилю, с учётом накопленных red flags.

Использует Claude/Deepseek для оценки + Graphiti для подтягивания
исторических паттернов ("похожие вакансии этого типа плохо кончались").
"""

import argparse
import os


PROFILE = """
Заполни своим реальным профилем: навыки, ставка, типы проектов,
которые интересны/неинтересны, дедлкиллеры (что сразу дисквалифицирует
вакансию).
"""

SCORING_PROMPT_TEMPLATE = """Ты — скорер вакансий фрилансера. Оцени вакансию
по профилю. Верни ТОЛЬКО JSON, без преамбулы и markdown-разметки.

Профиль фрилансера:
{profile}

Похожие вакансии из истории (что сработало/не сработало):
{historical_context}

Вакансия:
Заголовок: {title}
Описание: {description}
Бюджет: {budget}

Верни JSON такой структуры:
{{
  "score": <0-10>,
  "reason": "<одно предложение>",
  "red_flags": ["<если есть>"],
  "recommended_action": "<apply|skip|maybe>"
}}
"""


def fetch_historical_context(graphiti_url: str, job_description: str) -> str:
    """Заглушка: запросить у Graphiti похожие прошлые вакансии и их исходы."""
    raise NotImplementedError("Дописать запрос к Graphiti API (порт 8000 из brain-v2)")


def score_job(job: dict, historical_context: str) -> dict:
    """Заглушка: вызов Claude/Deepseek API со SCORING_PROMPT_TEMPLATE."""
    raise NotImplementedError("Дописать вызов Anthropic/Deepseek API")


def fetch_unscored_jobs(conn_params: dict) -> list[dict]:
    """Заглушка: выбрать вакансии из freelance.jobs, где score IS NULL."""
    raise NotImplementedError("Дописать SELECT")


def save_scores(jobs_with_scores: list[dict], conn_params: dict) -> None:
    """Заглушка: UPDATE freelance.jobs SET score=..., score_reason=..., red_flags=..."""
    raise NotImplementedError("Дописать UPDATE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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

    jobs = fetch_unscored_jobs(conn_params)
    scored = []
    for job in jobs:
        context = fetch_historical_context(args.graphiti_url, job["description"])
        result = score_job(job, context)
        scored.append({**job, **result})

    save_scores(scored, conn_params)
    print(f"Оценено вакансий: {len(scored)}")


if __name__ == "__main__":
    main()
