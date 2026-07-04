"""Модуль взаимодействия с Claude: валидация заказа и генерация отклика.

Логика намеренно объединена в один вызов: модель сама решает, стоит ли
откликаться, и сразу пишет текст. Если заказ неадекватный — возвращает
строго "IGNORE", что диспетчер интерпретирует как «пропустить».
"""
from typing import TYPE_CHECKING

from providers.base import Job

if TYPE_CHECKING:
    from agent import AutonomousAgent

# Claude 3.7 Sonnet отозван — используем актуальную модель того же уровня
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "Ты — профессиональный веб-разработчик Радмир. "
    "Специализация: Next.js, React, Tailwind CSS. "
    "Тебе будет дано ТЗ заказчика с фриланс-биржи.\n\n"
    "Правила:\n"
    "1. Если задача неадекватная (слишком мало денег, нереальные сроки, "
    "не относится к веб-разработке) — ответь строго одним словом: IGNORE\n"
    "2. Если задача подходит — напиши короткий, персонализированный отклик. "
    "Начинай строго с: «Здравствуйте! Меня зовут Радмир, я изучил вашу задачу...». "
    "Далее кратко предложи техническое решение на основе Next.js / React / Tailwind CSS. "
    "Пиши как живой, уверенный в себе специалист — без штампов и воды. "
    "Объём: 3–5 предложений."
)


class AIClient:
    """Тонкая обёртка над Anthropic API для задач провайдеров."""

    def __init__(self, agent: "AutonomousAgent"):
        self._agent = agent

    async def validate_and_generate(self, job: Job) -> str | None:
        """Валидирует заказ и генерирует текст отклика.

        Возвращает:
        - str с текстом отклика, если заказ принят;
        - None, если модель решила игнорировать заказ.
        """
        user_content = (
            f"Платформа: {job.provider_name}\n"
            f"Заголовок: {job.title}\n"
            f"Бюджет: {job.budget or 'не указан'}\n"
            f"Срок: {job.deadline or 'не указан'}\n\n"
            f"Описание задачи:\n{job.description}"
        )
        response = await self._agent.client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        self._agent._track_usage(response.usage, f"AI валидация [{job.provider_name}]")

        text = response.content[0].text.strip()
        if text.upper().startswith("IGNORE"):
            return None
        return text
