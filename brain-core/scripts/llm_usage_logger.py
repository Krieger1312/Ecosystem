#!/usr/bin/env python3
"""
Обёртка для логирования каждого вызова LLM в brain.llm_usage_log.

Использование в других скриптах (пример):

    from llm_usage_logger import log_call

    response = anthropic_client.messages.create(...)
    log_call(
        subsystem="freelance", layer="proposal",
        provider="anthropic", model="claude-sonnet-4-5",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        conn_params=conn_params,
    )

Цены за токен для оценки стоимости — вынесены в PRICING, обновляй
при изменении тарифов у провайдеров.
"""

import os


# NOTE: ориентировочные цены, актуализируй под реальные тарифы на момент использования
PRICING = {
    ("anthropic", "claude-sonnet-4-5"): {"input": 3.0, "output": 15.0},   # $ за 1M токенов
    ("deepseek", "deepseek-chat"): {"input": 0.27, "output": 1.10},
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float | None:
    key = (provider, model)
    if key not in PRICING:
        return None
    p = PRICING[key]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def log_call(subsystem: str, layer: str, provider: str, model: str,
             input_tokens: int, output_tokens: int, conn_params: dict) -> None:
    """Заглушка: INSERT в brain.llm_usage_log с оценённой стоимостью."""
    cost = estimate_cost(provider, model, input_tokens, output_tokens)
    raise NotImplementedError(
        f"Дописать INSERT (расчётная стоимость этого вызова: {cost})"
    )


if __name__ == "__main__":
    # Самопроверка расчёта стоимости без обращения к БД
    example_cost = estimate_cost("anthropic", "claude-sonnet-4-5", 1000, 500)
    print(f"Пример расчёта стоимости: ${example_cost:.6f}" if example_cost else "Модель не в PRICING")
