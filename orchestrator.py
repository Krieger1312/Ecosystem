"""Точка входа оркестратора фриланс-бота.

Запуск:
    python orchestrator.py [--interval 300] [--providers habr kwork]

По умолчанию опрашивает все зарегистрированные провайдеры каждые 5 минут.
Логи пишет в stdout; при желании перенаправь в файл через >> bot.log 2>&1.

Файлы куки должны быть рядом с репозиторием:
  cookies_habr.json  — для HabrProvider
  cookies_kwork.json — для KworkProvider
"""
import argparse
import asyncio
import logging
import sys

from agent import AutonomousAgent
from core.ai_client import AIClient
from core.dispatcher import Dispatcher
from providers.habr_provider import HabrProvider
from providers.kwork_provider import KworkProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Реестр всех доступных провайдеров — добавь новую платформу сюда
PROVIDER_REGISTRY = {
    "habr": HabrProvider,
    "kwork": KworkProvider,
}

DEFAULT_POLL_INTERVAL = 300  # секунд между циклами


def _build_providers(names: list[str], agent: AutonomousAgent):
    providers = []
    for name in names:
        cls = PROVIDER_REGISTRY.get(name)
        if cls is None:
            log.warning("Неизвестный провайдер '%s', пропускаем. Доступны: %s",
                        name, list(PROVIDER_REGISTRY))
            continue
        providers.append(cls(agent))
    return providers


async def run(poll_interval: int, provider_names: list[str]) -> None:
    agent = AutonomousAgent()
    try:
        # подключаем серверы, которые используют провайдеры
        await agent.connect_default_servers()   # fetch + filesystem + puppeteer
        await agent._get_tools()                # строим таблицу маршрутизации MCP

        providers = _build_providers(provider_names, agent)
        if not providers:
            log.error("Нет активных провайдеров, завершаем")
            return

        ai_client = AIClient(agent)
        dispatcher = Dispatcher(providers, ai_client)

        log.info(
            "Оркестратор запущен. Провайдеры: %s. Интервал опроса: %ds",
            [p.name for p in providers], poll_interval,
        )

        cycle = 0
        while True:
            cycle += 1
            log.info("=== Цикл %d ===", cycle)
            try:
                sent = await dispatcher.poll_once()
                if sent:
                    log.info("Отправлено откликов: %s", sent)
                else:
                    log.info("Откликов не отправлено в этом цикле")
            except Exception as exc:
                log.exception("Неожиданная ошибка в цикле %d: %s", cycle, exc)

            log.info("Следующий цикл через %d секунд...", poll_interval)
            await asyncio.sleep(poll_interval)
    finally:
        await agent.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Фриланс-бот: автоматический мониторинг и отклики")
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_POLL_INTERVAL,
        help=f"Интервал опроса в секундах (по умолчанию {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--providers", nargs="+", default=list(PROVIDER_REGISTRY),
        metavar="NAME",
        help=f"Список провайдеров для запуска (по умолчанию все: {list(PROVIDER_REGISTRY)})",
    )
    args = parser.parse_args()
    asyncio.run(run(args.interval, args.providers))


if __name__ == "__main__":
    main()
