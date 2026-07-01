from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Job:
    """Единый формат заказа, не зависящий от платформы-источника."""
    url: str
    title: str
    description: str
    provider_name: str
    budget: str = ""
    deadline: str = ""

    @property
    def id(self) -> str:
        """Стабильный уникальный идентификатор для дедупликации — URL заказа."""
        return self.url


class BaseProvider(ABC):
    """Абстрактный провайдер платформы.

    Каждая конкретная платформа (Habr, Kwork, …) реализует два метода:
    - fetch_jobs: получить список новых заказов;
    - send_proposal: отправить отклик на конкретный заказ.

    Провайдер получает экземпляр AutonomousAgent для доступа к MCP-инструментам
    (fetch, puppeteer, filesystem) и не создаёт собственных MCP-соединений.
    """

    name: str = ""

    @abstractmethod
    async def fetch_jobs(self) -> list[Job]:
        """Вернуть актуальный список заказов с платформы."""
        ...

    @abstractmethod
    async def send_proposal(self, job: Job, message: str) -> str:
        """Отправить отклик message на заказ job.

        Возвращает строку-подтверждение при успехе, бросает RuntimeError при ошибке.
        """
        ...
