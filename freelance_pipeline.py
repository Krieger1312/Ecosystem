import asyncio
import os
import re

import anthropic

from agent import AGENT_WORKSPACE_DIR, AutonomousAgent

# Claude 3.7 Sonnet больше не доступен (модель отозвана) — используем актуальную
# модель уровня Sonnet
PROPOSAL_MODEL = "claude-sonnet-4-6"

PROPOSAL_SYSTEM_PROMPT = (
    "Ты — опытный фрилансер-разработчик. Напиши короткий, персонализированный, "
    "цепляющий отклик на этот проект. Без шаблонных фраз. Предложи конкретное "
    "техническое решение."
)

EXECUTE_SYSTEM_PROMPT = (
    "Ты — опытный фрилансер-разработчик. Выполни поставленную задачу: напиши "
    "готовое решение (код и/или текст). Не извиняйся и не уточняй детали — "
    "предложи рабочий вариант на основе того, что есть в ТЗ."
)

# подпапка внутри agent_workspace (изолированной зоны filesystem MCP-сервера),
# куда складываются черновики выполненных заданий
DONE_PROJECTS_DIR = os.path.join(os.path.abspath(AGENT_WORKSPACE_DIR), "done_projects")


def _slugify(title: str) -> str:
    """Грубо превращает заголовок задачи в безопасное имя файла."""
    slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "-", title).strip("-").lower()
    return slug[:60] or "task"


class FreelanceAgent:
    """Конвейер автоматизации фриланс-биржи: поиск задач -> отклик -> черновое решение.

    Переиспользует MCP-подключения и Anthropic-клиент базового AutonomousAgent
    (fetch — для парсинга бирж, puppeteer — для работы с динамическими страницами,
    filesystem — для сохранения черновиков). Серверы должны быть подключены
    заранее через agent.connect_default_servers().
    """

    def __init__(self, agent: AutonomousAgent):
        self._agent = agent

    async def find_jobs(self, keywords: str) -> list[dict]:
        """Ищет задачи по ключевым словам на фриланс-бирже.

        ЗАГЛУШКА: реальный парсинг (fetch для статичных списков, puppeteer для
        страниц с JS-рендерингом и авторизацией) подключается позже, когда
        определена конкретная биржа. Сейчас возвращает пример структуры данных,
        чтобы остальной конвейер можно было собрать и протестировать отдельно.
        """
        print(f"Поиск задач по ключевым словам: '{keywords}' (заглушка)")
        return [
            {
                "job_title": "Скрипт парсинга цен на Python",
                "description": (
                    "Нужен скрипт на Python, который раз в час собирает цены товаров "
                    "с интернет-магазина и сохраняет их в CSV. Сайт без авторизации, "
                    "структура страниц стабильная."
                ),
            },
            {
                "job_title": "Telegram-бот для учёта финансов",
                "description": (
                    "Нужен Telegram-бот на aiogram, который принимает сообщения вида "
                    "'категория сумма', сохраняет их в SQLite и по команде /report "
                    "присылает сводку трат за месяц."
                ),
            },
        ]

    async def generate_proposal(self, job_description: str) -> str:
        """Генерирует персонализированный отклик на ТЗ."""
        response = await self._agent.client.messages.create(
            model=PROPOSAL_MODEL,
            max_tokens=600,
            system=PROPOSAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": job_description}],
        )
        self._agent._track_usage(response.usage, "Генерация отклика")
        return response.content[0].text

    async def execute_task(self, job_title: str, job_description: str) -> str:
        """Просит модель написать черновое решение задачи и сохраняет его через
        filesystem MCP-сервер в agent_workspace/done_projects/."""
        response = await self._agent.client.messages.create(
            model=PROPOSAL_MODEL,
            max_tokens=2000,
            system=EXECUTE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": job_description}],
        )
        self._agent._track_usage(response.usage, "Выполнение задачи")
        result_text = response.content[0].text

        # filesystem MCP-сервер пускает запись только внутри своей allowed-директории
        # и требует, чтобы родительская папка уже существовала — поэтому сначала
        # создаём done_projects/ (вызов идемпотентен, повторный create_directory не ломает)
        cd_result = await self._agent._execute_tool("create_directory", {"path": DONE_PROJECTS_DIR})
        if "ОШИБКА" in cd_result or "не найден" in cd_result:
            raise RuntimeError(f"Не удалось создать {DONE_PROJECTS_DIR}: {cd_result}")

        file_path = os.path.join(DONE_PROJECTS_DIR, f"{_slugify(job_title)}.md")
        wf_result = await self._agent._execute_tool("write_file", {"path": file_path, "content": result_text})
        if "ОШИБКА" in wf_result or "не найден" in wf_result:
            raise RuntimeError(f"Не удалось сохранить {file_path}: {wf_result}")

        print(f"Черновик решения сохранён: {file_path}")
        return result_text


async def run_pipeline(keywords: str):
    """Полный цикл: находит задачи, генерирует отклики и черновые решения для каждой."""
    agent = AutonomousAgent()
    pipeline = FreelanceAgent(agent)

    try:
        await agent.connect_default_servers()
        # FreelanceAgent вызывает _execute_tool() напрямую, минуя agentic-цикл agent.run(),
        # а таблица маршрутизации tool_name -> MCP-сессия строится только внутри _get_tools() —
        # поэтому собираем её явно сразу после подключения серверов
        await agent._get_tools()

        jobs = await pipeline.find_jobs(keywords)
        for job in jobs:
            print(f"\n=== Задача: {job['job_title']} ===")

            proposal = await pipeline.generate_proposal(job["description"])
            print(f"Отклик:\n{proposal}\n")

            await pipeline.execute_task(job["job_title"], job["description"])
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(run_pipeline("python разработка"))
