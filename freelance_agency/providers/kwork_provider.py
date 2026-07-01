"""Провайдер Kwork.

Получение заказов: Puppeteer — Kwork рендерит страницы через React/SPA,
RSS отсутствует. Категория "Разработка сайтов" — c=41.

Отправка откликов: Puppeteer, кнопка "Хочу выполнить" открывает модальное окно
с полем предложения — заполняем и отправляем.

Авторизация: куки из файла cookies_kwork.json. Формат — массив объектов
[{name, value, domain, path, expires, ...}], как экспортирует EditThisCookie.
"""
import json
import os
import re
from typing import TYPE_CHECKING

from providers.base import BaseProvider, Job
from core import puppeteer_utils as pu

if TYPE_CHECKING:
    from agent import AutonomousAgent

KWORK_DOMAIN = "https://kwork.ru"
KWORK_PROJECTS_URL = "https://kwork.ru/projects?c=41"  # category 41 — web development

KWORK_COOKIES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "cookies_kwork.json"
)

# JS-скрипт для разбора карточек проектов на странице листинга Kwork.
# Классы намеренно дублируются в нескольких вариантах — Kwork меняет
# дизайн, при поломке уточни актуальные селекторы в DevTools браузера.
_SCRAPE_PROJECTS_SCRIPT = """
    (() => {
        const cards = document.querySelectorAll(
            '.wants-card, .project-card, [class*="project__item"], [class*="wants__item"]'
        );
        const jobs = [];
        cards.forEach(card => {
            const linkEl = card.querySelector('a[href*="/projects/"]');
            const titleEl = card.querySelector(
                '.wants-card__title, .project-card__title, h2, h3, [class*="title"]'
            );
            const descEl = card.querySelector(
                '.wants-card__description, .project-card__description, [class*="description"], p'
            );
            const budgetEl = card.querySelector(
                '.wants-card__price, .project-card__price, [class*="price"], [class*="budget"]'
            );
            if (!linkEl || !titleEl) return;
            jobs.push({
                url: linkEl.href,
                title: titleEl.textContent.trim(),
                description: descEl ? descEl.textContent.trim() : '',
                budget: budgetEl ? budgetEl.textContent.trim() : '',
            });
        });
        return { ok: true, jobs };
    })()
"""

# Форма отклика на Kwork открывается кнопкой "Хочу выполнить" / "Откликнуться",
# которая рендерит модальное окно. Ищем textarea внутри модала, потом submit.
_KWORK_FIELD_SELECTORS = [
    ".modal textarea",
    "textarea[name*='description' i]",
    "textarea[name*='comment' i]",
    "textarea[placeholder*='предложение' i]",
    "textarea[placeholder*='опишите' i]",
    *pu.PROPOSAL_FIELD_SELECTORS,
]
_KWORK_SUBMIT_SELECTORS = [
    ".modal button[type='submit']",
    ".modal button[class*='submit' i]",
    ".modal button[class*='send' i]",
    *pu.SUBMIT_BUTTON_SELECTORS,
]
# Кнопка "Хочу выполнить" для открытия модала отклика
_KWORK_RESPOND_BUTTON_SELECTORS = [
    "button[class*='want' i]",
    "a[class*='want' i]",
    "button[class*='respond' i]",
    "[class*='wants-btn']",
    "button[data-action*='respond']",
]


class KworkProvider(BaseProvider):
    name = "kwork"

    def __init__(self, agent: "AutonomousAgent"):
        self._agent = agent

    async def fetch_jobs(self) -> list[Job]:
        """Открывает страницу категории через Puppeteer и парсит карточки проектов."""
        await pu.navigate(self._agent, KWORK_DOMAIN)
        await self._inject_cookies(KWORK_COOKIES_FILE)
        await pu.navigate(self._agent, KWORK_PROJECTS_URL)

        raw = await self._agent._execute_tool(
            "puppeteer_evaluate", {"script": _SCRAPE_PROJECTS_SCRIPT}
        )
        result = pu.parse_evaluate_result(raw)
        if not result.get("ok"):
            raise RuntimeError(f"Не удалось распарсить страницу Kwork: {result}")

        jobs: list[Job] = []
        for item in result.get("jobs", []):
            url = item.get("url", "")
            if not url:
                continue
            jobs.append(Job(
                url=url,
                title=item.get("title", ""),
                description=item.get("description", ""),
                provider_name=self.name,
                budget=item.get("budget", ""),
            ))
        print(f"Kwork: найдено {len(jobs)} проектов")
        return jobs

    async def send_proposal(self, job: Job, message: str) -> str:
        """Переходит на страницу проекта, кликает «Хочу выполнить», заполняет и отправляет."""
        await pu.navigate(self._agent, job.url)

        # открываем модальное окно отклика
        opened = False
        for sel in _KWORK_RESPOND_BUTTON_SELECTORS:
            click = await self._agent._execute_tool("puppeteer_click", {"selector": sel})
            if not pu.is_tool_error(click):
                opened = True
                break

        if not opened:
            # Если кнопки не нашли — пробуем напрямую (форма, возможно, уже на странице)
            print(f"Kwork: кнопка открытия формы отклика не найдена, пробуем заполнить форму напрямую на {job.url}")

        await pu.type_and_submit(
            self._agent, message,
            field_selectors=_KWORK_FIELD_SELECTORS,
            button_selectors=_KWORK_SUBMIT_SELECTORS,
        )
        return f"Отклик отправлен на Kwork: {job.url}"

    async def _inject_cookies(self, cookies_file: str) -> None:
        """Устанавливает куки авторизованной сессии Kwork.

        Kwork использует httpOnly-куки для сессии (_ga, PHPSESSID и т.п.) —
        они не устанавливаются через document.cookie из JS. Полноценная
        инъекция требует CDP page.setCookie(). Текущая реализация устанавливает
        только доступные куки; этого может быть достаточно, если сессия ещё
        не истекла и httpOnly-куки хранятся в браузере puppeteer с предыдущего
        визита (при совпадении профиля браузера).
        """
        if not os.path.exists(cookies_file):
            raise FileNotFoundError(
                f"Файл с куками не найден: {cookies_file}. "
                "Экспортируй куки авторизованной сессии kwork.ru в этот файл."
            )
        with open(cookies_file, encoding="utf-8") as f:
            cookies: list[dict] = json.load(f)

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
            raise RuntimeError(f"Не удалось установить куки Kwork: {result}")
        print(f"Kwork: установлено {result.get('set', '?')} куки")
