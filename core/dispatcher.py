"""Диспетчер: опрашивает все провайдеры, дедуплицирует заказы, роутит отклики.

Хранит id уже обработанных заказов в памяти (в рамках одного запуска).
При перезапуске оркестратора дедупликация сбрасывается — для персистентного
хранения seen_ids расширь метод _load_seen / _persist_seen и подключи файл или БД.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from core.ai_client import AIClient
from core.puppeteer_utils import is_tool_error
from providers.base import BaseProvider, Job

if TYPE_CHECKING:
    from agent import AutonomousAgent

log = logging.getLogger(__name__)


class Dispatcher:
    """Центральный координатор потоков данных между провайдерами и ИИ-клиентом."""

    def __init__(self, providers: list[BaseProvider], ai_client: AIClient):
        self._providers = {p.name: p for p in providers}
        self._ai = ai_client
        self._seen_ids: set[str] = set()

    async def poll_once(self) -> dict[str, int]:
        """Один полный цикл опроса.

        1. Параллельно забирает заказы у всех провайдеров.
        2. Фильтрует дубликаты.
        3. Для каждого нового заказа запрашивает у ИИ текст отклика.
        4. Если ИИ не вернул IGNORE — отправляет отклик через нужный провайдер.

        Возвращает словарь {provider_name: кол-во отправленных откликов}.
        """
        raw_jobs = await self._fetch_all_providers()
        new_jobs = self._deduplicate(raw_jobs)

        if not new_jobs:
            log.info("Новых заказов не найдено")
            return {}

        log.info("Новых заказов: %d", len(new_jobs))
        sent: dict[str, int] = {}

        for job in new_jobs:
            try:
                proposal = await self._ai.validate_and_generate(job)
            except Exception as exc:
                log.error("Ошибка AI для заказа %s: %s", job.url, exc)
                continue

            if proposal is None:
                log.info("Пропускаем (IGNORE): %s", job.title[:60])
                continue

            provider = self._providers.get(job.provider_name)
            if provider is None:
                log.warning("Провайдер %s не зарегистрирован, пропускаем", job.provider_name)
                continue

            try:
                await provider.send_proposal(job, proposal)
                sent[job.provider_name] = sent.get(job.provider_name, 0) + 1
                log.info("Отклик отправлен: [%s] %s", job.provider_name, job.title[:60])
            except Exception as exc:
                log.error("Ошибка отправки отклика [%s] %s: %s", job.provider_name, job.url, exc)

        return sent

    async def _fetch_all_providers(self) -> list[Job]:
        """Параллельно вызывает fetch_jobs у каждого провайдера."""
        tasks = {
            name: asyncio.create_task(p.fetch_jobs(), name=f"fetch_{name}")
            for name, p in self._providers.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        jobs: list[Job] = []
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                log.error("Ошибка опроса провайдера %s: %s", name, result)
            else:
                log.info("Провайдер %s вернул %d заказов", name, len(result))
                jobs.extend(result)
        return jobs

    def _deduplicate(self, jobs: list[Job]) -> list[Job]:
        """Убирает заказы, которые уже встречались в этом запуске."""
        new: list[Job] = []
        for job in jobs:
            if job.id not in self._seen_ids:
                self._seen_ids.add(job.id)
                new.append(job)
        return new
