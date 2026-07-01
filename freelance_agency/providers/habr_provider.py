"""Провайдер Habr Freelance.

Получение заказов: RSS-лента (https://freelance.habr.com/tasks.rss) — быстро,
без Puppeteer, без авторизации. Парсинг через stdlib xml.etree.ElementTree.

Отправка откликов: Puppeteer с куками сессии. Habr Freelance открывает форму
отклика по URL вида /tasks/{id}/responses/new после авторизации.
Куки загружаются из файла cookies_habr.json (массив объектов {name, value, ...}).
"""
import html
import os
import json
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from providers.base import BaseProvider, Job
from core import puppeteer_utils as pu

if TYPE_CHECKING:
    from agent import AutonomousAgent

# Вся лента или только нужные категории — добавляй ?categories=разработка к URL
HABR_RSS_URL = "https://freelance.habr.com/tasks.rss"
HABR_DOMAIN = "https://freelance.habr.com"

# Куки сессии для авторизованных запросов — получаются после ручного логина
# и сохраняются браузерным расширением в стандартный JSON-формат
HABR_COOKIES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "cookies_habr.json"
)

# Habr Freelance специфичные CSS-селекторы формы отклика
_HABR_FIELD_SELECTORS = [
    "textarea[name='response[body]']",
    "textarea[id*='response']",
    *pu.PROPOSAL_FIELD_SELECTORS,  # универсальный запасной вариант
]
_HABR_SUBMIT_SELECTORS = [
    "input[type='submit'][value*='Отправить']",
    "button[type='submit']",
    *pu.SUBMIT_BUTTON_SELECTORS,
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


class HabrProvider(BaseProvider):
    name = "habr"

    def __init__(self, agent: "AutonomousAgent"):
        self._agent = agent

    async def fetch_jobs(self) -> list[Job]:
        """Загружает RSS-ленту через MCP fetch и возвращает список заказов."""
        raw = await self._agent._execute_tool("fetch", {"url": HABR_RSS_URL})
        if pu.is_tool_error(raw):
            raise RuntimeError(f"Не удалось получить RSS Habr Freelance: {raw}")

        # RSS внутри fetch-ответа — ищем начало XML (fetch может добавить заголовки)
        xml_start = raw.find("<?xml")
        if xml_start == -1:
            xml_start = raw.find("<rss")
        if xml_start == -1:
            raise RuntimeError(f"Не удалось найти XML в ответе fetch: {raw[:200]}")
        root = ET.fromstring(raw[xml_start:])

        jobs: list[Job] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = _strip_html(item.findtext("description") or "")
            if not link:
                continue
            jobs.append(Job(
                url=link,
                title=title,
                description=desc,
                provider_name=self.name,
            ))
        return jobs

    async def send_proposal(self, job: Job, message: str) -> str:
        """Отправляет отклик через браузер с сессионными куками Habr.

        Для работы требуется файл cookies_habr.json с куками авторизованной
        сессии. Формат: массив объектов [{name, value, domain, path, ...}],
        как экспортирует расширение "EditThisCookie" или аналоги.
        """
        await pu.navigate(self._agent, HABR_DOMAIN)
        await self._inject_cookies(HABR_COOKIES_FILE)

        # Habr открывает форму отклика по прямому URL
        task_id_match = re.search(r"/tasks/(\d+)", job.url)
        if task_id_match:
            form_url = f"{HABR_DOMAIN}/tasks/{task_id_match.group(1)}/responses/new"
        else:
            form_url = job.url

        await pu.navigate(self._agent, form_url)
        await pu.type_and_submit(
            self._agent, message,
            field_selectors=_HABR_FIELD_SELECTORS,
            button_selectors=_HABR_SUBMIT_SELECTORS,
        )
        return f"Отклик отправлен на Habr: {job.url}"

    async def _inject_cookies(self, cookies_file: str) -> None:
        """Вставляет куки в текущую страницу через document.cookie.

        Ограничение: httpOnly-куки (обычно _session_id) через JS не устанавливаются.
        Для полноценной авторизации нужен кастомный MCP-сервер с page.setCookie().
        Для Habr Freelance обычно достаточно непривилегированных куки сессии.
        """
        if not os.path.exists(cookies_file):
            raise FileNotFoundError(
                f"Файл с куками не найден: {cookies_file}. "
                "Экспортируй куки авторизованной сессии браузером и сохрани сюда."
            )
        with open(cookies_file, encoding="utf-8") as f:
            cookies: list[dict] = json.load(f)

        # устанавливаем по одной — document.cookie принимает по одному значению
        inject_script = f"""
            (() => {{
                const cookies = {json.dumps(cookies)};
                let set = 0;
                for (const c of cookies) {{
                    if (!c.name || !c.value) continue;
                    let s = c.name + '=' + encodeURIComponent(c.value);
                    if (c.path) s += '; path=' + c.path;
                    if (c.expires) s += '; expires=' + new Date(c.expires * 1000).toUTCString();
                    document.cookie = s;
                    set++;
                }}
                return {{ ok: true, set }};
            }})()
        """
        raw = await self._agent._execute_tool("puppeteer_evaluate", {"script": inject_script})
        result = pu.parse_evaluate_result(raw)
        if not result.get("ok"):
            raise RuntimeError(f"Не удалось установить куки Habr: {result}")
        print(f"Habr: установлено {result.get('set', '?')} куки")
