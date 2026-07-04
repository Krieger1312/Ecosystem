"""
B2B Lead Machine — Шаги 2–3: Анализ сайта и генерация персонализированного письма.

analyze_company(name, url) делает три вещи:
  1. Скачивает HTML главной страницы (и страницы контактов, если найдена)
  2. Извлекает Email из mailto-ссылок и текста страницы
  3. Передаёт контент в Claude, чтобы сгенерировать письмо директору
"""

import asyncio
import os
import random
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ── Константы ─────────────────────────────────────────────────────────────────

FETCH_TIMEOUT    = 15          # секунды
FETCH_MAX_BYTES  = 1_500_000   # 1.5 МБ — не скачиваем огромные страницы
CONTENT_MAX_CHARS = 4_000      # максимум символов текста для Claude

# Слова, по которым находим ссылку на контактную страницу
_CONTACT_HINTS = {
    "контакт", "contacts", "contact", "связаться", "связь",
    "о нас", "about", "about-us", "обратная связь", "feedback",
}

# Email-домены, которые фильтруем как ложные срабатывания
_EMAIL_BLACKLIST_DOMAINS = {
    "example.com", "test.com", "domain.com", "email.com",
    "sentry.io", "w3.org", "schema.org", "google.com",
}

_EMAIL_RE = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ── Системный промпт для Claude ───────────────────────────────────────────────

_OFFER_SYSTEM = """\
Ты — B2B-менеджер по продажам в IT-компании. Тебе дан текст с сайта потенциального клиента.

Напиши КОРОТКОЕ персонализированное холодное письмо директору компании. Правила:
1. Начни строго с «Здравствуйте!»
2. Во втором предложении упомяни 1–2 конкретных факта о деятельности компании
   (это докажет, что письмо написано именно им, а не разослано всем подряд)
3. Предложи наши B2B-услуги: автоматизация бизнес-процессов, веб-разработка, IT-консалтинг
4. Закончи предложением созвониться или встретиться
5. Объём: 4–6 предложений, деловой и дружелюбный тон
6. Запрещены штампы: «команда экспертов», «индивидуальный подход», «мы заметили», «комплексные решения»
7. Не придумывай факты — используй ТОЛЬКО информацию из предоставленного текста
8. Если текст слишком короткий или неинформативный — честно напиши одну строку: \
«Недостаточно данных о компании для персонализации письма»\
"""

# ── HTTP-клиент ───────────────────────────────────────────────────────────────


def _make_headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
    }


async def _fetch_html(url: str, client: httpx.AsyncClient) -> str | None:
    """Скачивает HTML страницы; возвращает None при любой ошибке."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")

    for attempt in range(2):
        try:
            resp = await client.get(
                url,
                headers=_make_headers(),
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                return None
            # Ограничиваем объём
            content = resp.content[:FETCH_MAX_BYTES]
            return content.decode(resp.encoding or "utf-8", errors="replace")
        except httpx.SSLError:
            if attempt == 0:
                # Второй раз — без проверки SSL (некоторые корпоративные сайты)
                try:
                    async with httpx.AsyncClient(verify=False) as no_ssl:
                        resp = await no_ssl.get(
                            url, headers=_make_headers(),
                            timeout=FETCH_TIMEOUT, follow_redirects=True,
                        )
                        return resp.content[:FETCH_MAX_BYTES].decode(
                            resp.encoding or "utf-8", errors="replace"
                        )
                except Exception:
                    return None
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError):
            return None
        except Exception:
            return None
    return None


# ── Парсинг HTML ──────────────────────────────────────────────────────────────


def _extract_text(html: str) -> str:
    """Извлекает читаемый текст из HTML, убирая теги скриптов и стилей."""
    soup = BeautifulSoup(html, "lxml")

    # Удаляем шумовые теги
    for tag in soup(["script", "style", "noscript", "header", "footer",
                     "nav", "aside", "iframe", "svg"]):
        tag.decompose()

    # Ищем основной контентный блок
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"content|main|body", re.I))
        or soup.find(class_=re.compile(r"content|main|body|text", re.I))
        or soup.find("body")
    )
    text = (main or soup).get_text(separator="\n", strip=True)

    # Схлопываем множественные пустые строки
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:CONTENT_MAX_CHARS]


def _extract_emails(html: str) -> list[str]:
    """Ищет email-адреса в HTML: сначала в href='mailto:', потом в тексте."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []

    # Приоритет 1: mailto-ссылки (самые надёжные)
    for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
        addr = a["href"][7:].split("?")[0].strip().lower()
        if addr and "@" in addr:
            found.append(addr)

    # Приоритет 2: regex по тексту страницы
    text = soup.get_text()
    for m in _EMAIL_RE.finditer(text):
        found.append(m.group().lower())

    # Фильтрация и дедупликация
    clean: list[str] = []
    seen: set[str] = set()
    for email in found:
        domain = email.split("@")[-1]
        if domain not in _EMAIL_BLACKLIST_DOMAINS and email not in seen:
            seen.add(email)
            clean.append(email)

    return clean


def _find_contact_url(base_url: str, html: str) -> str | None:
    """Ищет ссылку на страницу 'Контакты' или 'О нас'."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", "")).lower()
        text = a.get_text(strip=True).lower()
        if any(hint in href or hint in text for hint in _CONTACT_HINTS):
            full = urljoin(base_url, a["href"])
            # Не выходим за пределы домена
            if urlparse(full).netloc == urlparse(base_url).netloc:
                return full
    return None


# ── Генерация письма через Claude ─────────────────────────────────────────────


async def _generate_offer(company_name: str, page_text: str) -> str:
    """Отправляет текст сайта в Claude и получает персонализированное письмо."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "[ANTHROPIC_API_KEY не задан — письмо не сгенерировано]"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        user_content = (
            f"Название компании: {company_name}\n\n"
            f"Текст с главной страницы сайта:\n{page_text}"
        )
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=_OFFER_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        return msg.content[0].text.strip()

    except Exception as exc:
        return f"[Ошибка Claude: {exc}]"


# ── Публичный API ─────────────────────────────────────────────────────────────


async def analyze_company(name: str, url: str) -> dict:
    """Анализирует сайт компании и генерирует персонализированное письмо.

    Возвращает словарь:
        email        — первый найденный email (строка, может быть пустой)
        offer_letter — текст письма от Claude
        status       — "ok" | "no_site" | "fetch_error" | "no_content"
    """
    if not url:
        return {"email": "", "offer_letter": "", "status": "no_site"}

    async with httpx.AsyncClient(verify=True, http2=True) as client:
        # Загружаем главную страницу
        main_html = await _fetch_html(url, client)
        if not main_html:
            return {"email": "", "offer_letter": "", "status": "fetch_error"}

        # Email с главной страницы
        emails = _extract_emails(main_html)
        main_text = _extract_text(main_html)

        # Ищем страницу контактов и тоже парсим
        contact_url = _find_contact_url(url, main_html)
        if contact_url and not emails:
            await asyncio.sleep(random.uniform(1.0, 2.5))
            contact_html = await _fetch_html(contact_url, client)
            if contact_html:
                emails.extend(_extract_emails(contact_html))
                # Добавляем текст контактной страницы (там бывают полезные факты)
                contact_text = _extract_text(contact_html)
                main_text = (main_text + "\n\n" + contact_text)[:CONTENT_MAX_CHARS]

    if not main_text.strip():
        return {"email": emails[0] if emails else "", "offer_letter": "", "status": "no_content"}

    offer = await _generate_offer(name, main_text)
    return {
        "email": emails[0] if emails else "",
        "offer_letter": offer,
        "status": "ok",
    }
