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
    "предложи рабочий вариант на основе того, что есть в ТЗ. После генерации "
    "решение будет автоматически развёрнуто на Vercel и опубликовано клиенту — "
    "пиши самодостаточный, готовый к деплою результат."
)

# подпапка внутри agent_workspace (изолированной зоны filesystem MCP-сервера),
# куда складываются черновики выполненных заданий
DONE_PROJECTS_DIR = os.path.join(os.path.abspath(AGENT_WORKSPACE_DIR), "done_projects")

# vercel --prod печатает финальный production URL в свой stdout;
# ищем его явно вместо того, чтобы полагаться на номер строки/формат
_DEPLOY_URL_RE = re.compile(r"https://\S+\.vercel\.app\S*")


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
        """Просит модель написать черновое решение задачи, сохраняет его в отдельной
        папке проекта через filesystem MCP-сервер, разворачивает проект на Vercel
        (профессиональный скилл деплоя) и готовит отчёт для клиента со ссылкой."""
        response = await self._agent.client.messages.create(
            model=PROPOSAL_MODEL,
            max_tokens=2000,
            system=EXECUTE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": job_description}],
        )
        self._agent._track_usage(response.usage, "Выполнение задачи")
        result_text = response.content[0].text

        # каждое задание получает свою папку — это и единица деплоя для vercel
        # (деплоится директория целиком), и естественная группировка файлов проекта
        project_dir = os.path.join(DONE_PROJECTS_DIR, _slugify(job_title))

        # filesystem MCP-сервер не создаёт промежуточные директории сам (требует,
        # чтобы родительская папка уже существовала) — создаём done_projects/,
        # а потом вложенную project_dir; оба вызова идемпотентны
        for directory in (DONE_PROJECTS_DIR, project_dir):
            cd_result = await self._agent._execute_tool("create_directory", {"path": directory})
            if "ОШИБКА" in cd_result or "не найден" in cd_result:
                raise RuntimeError(f"Не удалось создать {directory}: {cd_result}")

        solution_path = os.path.join(project_dir, "solution.md")
        wf_result = await self._agent._execute_tool("write_file", {"path": solution_path, "content": result_text})
        if "ОШИБКА" in wf_result or "не найден" in wf_result:
            raise RuntimeError(f"Не удалось сохранить {solution_path}: {wf_result}")
        print(f"Черновик решения сохранён: {solution_path}")

        # деплой — best-effort: если vercel не установлен/не авторизован в этом
        # окружении, задача не должна падать целиком, просто отчёт не создастся
        try:
            deploy_url = await self.deploy_project(project_dir)
        except Exception as e:
            print(f"Не удалось развернуть проект на Vercel: {e}")
            return result_text

        report_path = os.path.join(project_dir, "report_for_client.txt")
        report_text = f"Ваш проект готов. Вы можете посмотреть его вживую по этой ссылке: {deploy_url}"
        rf_result = await self._agent._execute_tool("write_file", {"path": report_path, "content": report_text})
        if "ОШИБКА" in rf_result or "не найден" in rf_result:
            raise RuntimeError(f"Не удалось сохранить {report_path}: {rf_result}")
        print(f"Отчёт для клиента сохранён: {report_path}")

        return result_text

    async def deploy_project(self, project_path: str) -> str:
        """Разворачивает готовый проект на Vercel и возвращает публичный production URL.

        Запускает `vercel --prod --yes` как реальный subprocess в директории
        project_path (не через MCP filesystem — vercel CLI работает с настоящей
        файловой системой и должен быть установлен и авторизован на хосте).
        Перехватывает stdout, ищет в нём опубликованный URL вида *.vercel.app.
        """
        process = await asyncio.create_subprocess_exec(
            "vercel", "--prod", "--yes",
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode(errors="replace")

        if process.returncode != 0:
            raise RuntimeError(f"vercel --prod завершился с кодом {process.returncode}:\n{output}")

        matches = _DEPLOY_URL_RE.findall(output)
        if not matches:
            raise RuntimeError(f"Не удалось найти URL в выводе vercel:\n{output}")

        # vercel в конце вывода печатает итоговый production URL последним
        url = matches[-1]
        print(f"Проект развёрнут: {url}")
        return url


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
