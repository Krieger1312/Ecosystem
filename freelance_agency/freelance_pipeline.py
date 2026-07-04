import asyncio
import json
import os
import re
from datetime import datetime, timezone

import anthropic

from agent import AGENT_WORKSPACE_DIR, AutonomousAgent

# Claude 3.7 Sonnet больше не доступен (модель отозвана) — используем актуальную
# модель уровня Sonnet
PROPOSAL_MODEL = "claude-sonnet-4-6"

PROPOSAL_SYSTEM_PROMPT = (
    "Ты — профессиональный веб-разработчик. Проанализируй ТЗ клиента. Если задача "
    "неадекватная (слишком мало денег или нереальные сроки) — игнорируй её. Если "
    "задача подходит, напиши короткий, персонализированный отклик. Начинай "
    "сообщение строго с: «Здравствуйте! Меня зовут Радмир, я изучил вашу "
    "задачу...». Далее кратко предложи техническое решение (например, "
    "использование Next.js и Tailwind). Не используй штампы, пиши как живой, "
    "уверенный в себе специалист."
)

EXECUTE_SYSTEM_PROMPT = (
    "Ты — опытный фрилансер-разработчик. Выполни поставленную задачу: напиши "
    "готовое решение (код и/или текст). Не извиняйся и не уточняй детали — "
    "предложи рабочий вариант на основе того, что есть в ТЗ. После генерации "
    "решение будет автоматически развёрнуто на Vercel и опубликовано клиенту — "
    "пиши самодостаточный, готовый к деплою результат."
)

# для веб-задач (Next.js/React/сайт) execute_task переключается на агентный
# tool-use цикл _execute_web_task вместо одного вызова модели — Claude сам решает,
# когда строить каркас, править файлы и деплоить
WEB_DEV_SYSTEM_PROMPT = (
    "Ты — Senior React/Next.js разработчик. Сначала используй bootstrap_nextjs_project "
    "для создания каркаса. Затем используй инструменты Filesystem, чтобы прочитать и "
    "перезаписать файл app/page.tsx (или создать новые компоненты), реализовав ТЗ "
    "заказчика. Пиши красивый UI, используя классы Tailwind CSS. Когда код готов, "
    "используй инструмент deploy_project. Если любой инструмент вернёт ошибку — это "
    "реальный лог npx/vercel/filesystem: внимательно разбери его, исправь код "
    "(перезапиши проблемный файл) и попробуй снова, не сдавайся после первой ошибки."
)

_WEB_TASK_KEYWORDS = (
    "next.js", "nextjs", "react", "сайт", "лендинг", "веб-сайт",
    "веб-приложение", "frontend", "фронтенд",
)

# vercel CLI печатает финальный production URL в свой stdout;
# ищем его явно вместо того, чтобы полагаться на номер строки/формат
_DEPLOY_URL_RE = re.compile(r"https://\S+\.vercel\.app\S*")

# подпапка внутри agent_workspace (изолированной зоны filesystem MCP-сервера),
# куда складываются черновики выполненных заданий
DONE_PROJECTS_DIR = os.path.join(os.path.abspath(AGENT_WORKSPACE_DIR), "done_projects")

# журнал отправленных откликов — ссылка на проект + текст, который реально ушёл
SENT_PROPOSALS_LOG_PATH = os.path.join(os.path.abspath(AGENT_WORKSPACE_DIR), "sent_proposals.log")

# биржи фриланса вёрстают форму отклика по-разному — пробуем по очереди самые
# распространённые селекторы текстового поля и кнопки отправки, вместо того
# чтобы полагаться на вёрстку одной конкретной площадки
_PROPOSAL_FIELD_SELECTORS = [
    "textarea[name*='message' i]",
    "textarea[placeholder*='отклик' i]",
    "textarea[placeholder*='сообщ' i]",
    "textarea[id*='proposal' i]",
    "textarea[class*='proposal' i]",
    "[contenteditable='true']",
    "textarea",
]

_SUBMIT_BUTTON_SELECTORS = [
    "button[type='submit']",
    "button[class*='submit' i]",
    "button[class*='send' i]",
    "input[type='submit']",
]

# инструменты для веб-агентного цикла, которых нет среди MCP-серверов —
# их реализация находится прямо в FreelanceAgent (см. bootstrap_nextjs_project, deploy_project)
BOOTSTRAP_TOOL_SCHEMA = {
    "name": "bootstrap_nextjs_project",
    "description": (
        "Создаёт каркас нового Next.js-приложения (TypeScript, Tailwind, ESLint, App Router) "
        "командой `npx create-next-app@latest` внутри agent_workspace/done_projects/. "
        "Вызывается один раз в начале веб-задачи, до правки файлов проекта. "
        "Возвращает абсолютный путь к созданной папке проекта."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "Имя папки/пакета проекта (будет приведено к безопасному виду)",
            }
        },
        "required": ["project_name"],
    },
}

DEPLOY_TOOL_SCHEMA = {
    "name": "deploy_project",
    "description": (
        "Разворачивает готовый проект на Vercel (`vercel --prod --yes`) и возвращает "
        "публичный production URL. Вызывается в конце, когда код готов."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Абсолютный путь к папке проекта, который вернул bootstrap_nextjs_project",
            }
        },
        "required": ["project_path"],
    },
}


def _slugify(title: str) -> str:
    """Грубо превращает заголовок задачи в безопасное имя файла."""
    slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "-", title).strip("-").lower()
    return slug[:60] or "task"


def _is_web_task(job_title: str, job_description: str) -> bool:
    """Эвристика: упоминает ли ТЗ веб-сайт/React/Next.js — тогда нужен полноценный
    агентный цикл bootstrap -> код -> деплой, а не один вызов модели."""
    text = f"{job_title} {job_description}".lower()
    return any(keyword in text for keyword in _WEB_TASK_KEYWORDS)


def _truncate(text: str, max_len: int = 4000) -> str:
    """Обрезает длинный консольный лог (npx/vercel), оставляя хвост — там обычно
    сама ошибка, а не шум установки зависимостей в начале."""
    if len(text) > max_len:
        return "...[ЛОГ ОБРЕЗАН, показан конец]...\n" + text[-max_len:]
    return text


def _is_tool_error(result_text: str) -> bool:
    """Распознаёт обе формы ошибки, которые может вернуть AutonomousAgent._execute_tool:
    обычный isError-результат MCP (текст с префиксом "[ОШИБКА ИНСТРУМЕНТА]") и
    транспортное исключение при самом вызове session.call_tool (текст вида "Ошибка
    вызова инструмента ..." — другой регистр первой буквы), плюс отсутствие
    инструмента в таблице маршрутизации ("не найден"). Сравнение через .lower(),
    т.к. эти два случая используют разный регистр и поиск "ОШИБКА" по точному
    регистру не ловит исключения (баг, из-за которого Dangerous browser arguments
    от puppeteer_navigate раньше проходил незамеченным)."""
    lowered = result_text.lower()
    return "ошибка" in lowered or "не найден" in lowered


def _parse_evaluate_result(raw: str) -> dict:
    """Достаёт JSON-объект, возвращённый JS-скриптом, из текстового ответа
    puppeteer_evaluate. Формат сервера (выяснен живой проверкой, нигде не
    документирован): "Execution result:\\n<JSON>\\n\\nConsole output:\\n..."."""
    if _is_tool_error(raw):
        return {"ok": False, "error": raw}
    marker = "Execution result:\n"
    json_part = raw
    if marker in raw:
        json_part = raw.split(marker, 1)[1]
    json_part = json_part.split("\n\nConsole output:")[0]
    try:
        return json.loads(json_part)
    except (json.JSONDecodeError, ValueError):
        return {"ok": False, "error": f"Не удалось разобрать ответ puppeteer_evaluate: {raw}"}


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

    async def send_proposal(self, url: str, message: str) -> str:
        """Автономно отправляет отклик на странице заказа через запущенную
        Puppeteer-сессию: переходит по url, находит поле ввода отклика по списку
        универсальных CSS-селекторов, печатает текст посимвольно с задержкой ~40мс
        и нажимает кнопку отправки.

        У MCP-сервера puppeteer нет инструмента, эквивалентного Node-уровневому
        page.type(selector, message, {delay: 40}) — есть только puppeteer_fill
        (мгновенная вставка без задержки) и puppeteer_evaluate (произвольный JS
        в контексте страницы). Печать с задержкой реализована как async JS внутри
        puppeteer_evaluate: посимвольная вставка через execCommand('insertText')
        для contenteditable или field.value += ch с диспатчем 'input' для
        textarea/input, с setTimeout(40мс) между символами.
        """
        # --no-sandbox нужен, потому что бот обычно работает в контейнере под root,
        # где штатный sandbox Chromium запускаться не может; сервер puppeteer считает
        # такие флаги "опасными" и без allowDangerous=True отклоняет вызов. headless:
        # True — на сервере без X-дисплея (типичный случай для бота на бэкенде)
        # headed-режим вообще не запустится
        nav_result = await self._agent._execute_tool(
            "puppeteer_navigate",
            {
                "url": url,
                "launchOptions": {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-setuid-sandbox"],
                },
                "allowDangerous": True,
            },
        )
        if _is_tool_error(nav_result):
            raise RuntimeError(f"Не удалось открыть {url}: {nav_result}")

        type_script = f"""
            (async () => {{
                const candidates = {json.dumps(_PROPOSAL_FIELD_SELECTORS)};
                let field = null;
                for (const sel of candidates) {{
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) {{ field = el; break; }}
                }}
                if (!field) return {{ ok: false, error: 'Текстовое поле отклика не найдено' }};
                field.focus();
                const text = {json.dumps(message)};
                const isEditable = field.isContentEditable;
                for (const ch of text) {{
                    if (isEditable) {{
                        document.execCommand('insertText', false, ch);
                    }} else {{
                        field.value += ch;
                        field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                    await new Promise(r => setTimeout(r, 40));
                }}
                return {{ ok: true }};
            }})()
        """
        type_raw = await self._agent._execute_tool("puppeteer_evaluate", {"script": type_script})
        type_result = _parse_evaluate_result(type_raw)
        if not type_result.get("ok"):
            raise RuntimeError(f"Не удалось напечатать отклик на {url}: {type_result.get('error', type_raw)}")

        last_click_error = None
        for selector in _SUBMIT_BUTTON_SELECTORS:
            click_result = await self._agent._execute_tool("puppeteer_click", {"selector": selector})
            if not _is_tool_error(click_result):
                break
            last_click_error = click_result
        else:
            raise RuntimeError(f"Не удалось найти и нажать кнопку отправки на {url}: {last_click_error}")

        await self._log_sent_proposal(url, message)
        print(f"Отклик отправлен: {url}")
        return f"Отклик успешно отправлен на {url}"

    async def _log_sent_proposal(self, url: str, message: str) -> None:
        """Дописывает запись об отправленном отклике в sent_proposals.log (ссылка +
        текст). MCP filesystem не даёт нативный append — читаем текущее содержимое
        (если файла ещё нет, read_text_file вернёт ошибку, считаем его пустым) и
        перезаписываем write_file с добавленной записью."""
        existing = await self._agent._execute_tool("read_text_file", {"path": SENT_PROPOSALS_LOG_PATH})
        if _is_tool_error(existing):
            existing = ""

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"[{timestamp}] {url}\n{message}\n{'-' * 40}\n"

        wf_result = await self._agent._execute_tool(
            "write_file", {"path": SENT_PROPOSALS_LOG_PATH, "content": existing + entry}
        )
        if _is_tool_error(wf_result):
            raise RuntimeError(f"Не удалось записать лог отправленных откликов: {wf_result}")

    async def execute_task(self, job_title: str, job_description: str) -> str:
        """Выполняет задачу. Веб-задачи (Next.js/React/сайт) запускают полноценный
        агентный цикл _execute_web_task (каркас -> код -> деплой, с самостоятельным
        разбором ошибок). Остальные задачи — прежний путь: один вызов модели,
        сохранение текстового решения в отдельной папке проекта через filesystem
        MCP-сервер и best-effort деплой на Vercel с отчётом для клиента."""
        if _is_web_task(job_title, job_description):
            return await self._execute_web_task(job_title, job_description)

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
            if _is_tool_error(cd_result):
                raise RuntimeError(f"Не удалось создать {directory}: {cd_result}")

        solution_path = os.path.join(project_dir, "solution.md")
        wf_result = await self._agent._execute_tool("write_file", {"path": solution_path, "content": result_text})
        if _is_tool_error(wf_result):
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
        if _is_tool_error(rf_result):
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
            raise RuntimeError(f"vercel --prod завершился с кодом {process.returncode}:\n{_truncate(output)}")

        matches = _DEPLOY_URL_RE.findall(output)
        if not matches:
            raise RuntimeError(f"Не удалось найти URL в выводе vercel:\n{_truncate(output)}")

        # vercel в конце вывода печатает итоговый production URL последним
        url = matches[-1]
        print(f"Проект развёрнут: {url}")
        return url

    async def bootstrap_nextjs_project(self, project_name: str) -> str:
        """Создаёт каркас Next.js-проекта (TypeScript, Tailwind, ESLint, App Router)
        командой create-next-app внутри done_projects/.

        Реальный subprocess, не MCP: create-next-app сам создаёт целевую папку и
        пишет тысячи файлов (node_modules) — это не то, для чего предназначен
        MCP filesystem write_file. Заранее создаём только родителя (done_projects/),
        саму папку проекта создаёт сам create-next-app.
        """
        safe_name = _slugify(project_name)
        os.makedirs(DONE_PROJECTS_DIR, exist_ok=True)
        project_dir = os.path.join(DONE_PROJECTS_DIR, safe_name)

        process = await asyncio.create_subprocess_exec(
            "npx", "create-next-app@latest", safe_name,
            "--typescript", "--tailwind", "--eslint", "--app", "--use-npm", "--yes",
            cwd=DONE_PROJECTS_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode(errors="replace")

        if process.returncode != 0:
            raise RuntimeError(
                f"create-next-app завершился с кодом {process.returncode}:\n{_truncate(output)}"
            )

        print(f"Каркас Next.js-проекта создан: {project_dir}")
        return (
            f"Каркас создан: {project_dir}\n"
            f"Дальше редактируй файлы внутри этой папки через filesystem-инструменты "
            f"(например {os.path.join(project_dir, 'app', 'page.tsx')}), "
            f"а в конце вызови deploy_project с project_path=\"{project_dir}\"."
        )

    async def _execute_web_task(self, job_title: str, job_description: str) -> str:
        """Агентный tool-use цикл для веб-задач: Claude сам решает, когда вызвать
        bootstrap_nextjs_project, отредактировать файлы через filesystem MCP-инструменты
        и развернуть проект через deploy_project. Ошибки любого инструмента (включая
        реальные логи npx/vercel) возвращаются модели как tool_result с is_error=True —
        на следующем шаге она видит лог, правит код и пробует снова, пока не кончится
        бюджет итераций (agent.max_iterations)."""
        mcp_tools = await self._agent._get_tools()
        filesystem_tool_names = {
            "read_file", "read_text_file", "write_file", "edit_file",
            "create_directory", "list_directory", "list_directory_with_sizes",
            "directory_tree", "move_file", "search_files", "get_file_info",
        }
        # из объединённого MCP-набора берём только файловые инструменты — puppeteer
        # и fetch тут не нужны и только засоряют контекст модели; cache_control,
        # выставленный _get_tools() на последнем MCP-инструменте, снимаем и
        # переставляем на действительно последний инструмент финального списка
        tools = [
            {k: v for k, v in t.items() if k != "cache_control"}
            for t in mcp_tools if t["name"] in filesystem_tool_names
        ]
        tools.append(dict(BOOTSTRAP_TOOL_SCHEMA))
        tools.append(dict(DEPLOY_TOOL_SCHEMA))
        tools[-1]["cache_control"] = {"type": "ephemeral"}

        messages = [{"role": "user", "content": f"Задача клиента: {job_title}\n\n{job_description}"}]

        response = None
        for iteration in range(1, self._agent.max_iterations + 1):
            print(f"Веб-задача «{job_title}»: шаг {iteration}/{self._agent.max_iterations}")
            response = await self._agent._create_message(
                model=PROPOSAL_MODEL,
                max_tokens=4000,
                system=WEB_DEV_SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            self._agent._track_usage(response.usage, f"Веб-задача, шаг {iteration}")
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                is_error = False
                if block.name == "bootstrap_nextjs_project":
                    try:
                        result_text = await self.bootstrap_nextjs_project(
                            block.input.get("project_name", job_title)
                        )
                    except Exception as e:
                        result_text = f"[ОШИБКА ИНСТРУМЕНТА] {e}"
                        is_error = True
                elif block.name == "deploy_project":
                    try:
                        url = await self.deploy_project(block.input.get("project_path", ""))
                        result_text = f"Проект развёрнут: {url}"
                    except Exception as e:
                        result_text = f"[ОШИБКА ИНСТРУМЕНТА] {e}"
                        is_error = True
                else:
                    result_text = await self._agent._execute_tool(block.name, block.input)
                    is_error = _is_tool_error(result_text)

                tool_result = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                if is_error:
                    tool_result["is_error"] = True
                tool_results.append(tool_result)

            messages.append({"role": "user", "content": tool_results})
        else:
            print(f"Веб-задача «{job_title}»: достигнут лимит итераций, остановка")

        final_text = ""
        if response and response.content:
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    final_text += block.text
        return final_text


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
