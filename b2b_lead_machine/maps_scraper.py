"""
B2B Lead Machine — Шаг 1: Парсинг компаний из Яндекс.Карт.

Использует Playwright (async Chromium) для поиска компаний и извлечения:
  - Название компании
  - URL сайта
  - Телефон
  - Адрес

Перед первым запуском установи браузер:
    pip install playwright
    playwright install chromium

Если Яндекс показывает капчу с облачного IP — передай headless=False
чтобы увидеть страницу в окне, или настрой residential-прокси.
"""

import asyncio
import os
import random
import re
from urllib.parse import quote, urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PwTimeout

# ── Задержки (секунды) ────────────────────────────────────────────────────────
# Имитируем живого пользователя: каждая задержка — случайный интервал

DELAY_PAGE_LOAD     = (3.0, 6.0)
DELAY_AFTER_CLICK   = (1.5, 3.5)
DELAY_BETWEEN_CARDS = (2.0, 4.5)
DELAY_SCROLL        = (0.7, 1.8)

PAGE_LOAD_TIMEOUT   = 35_000  # мс
SELECTOR_TIMEOUT    = 12_000  # мс

# ── User-Agent пул ────────────────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# ── Яндекс.Карты: CSS-селекторы ───────────────────────────────────────────────
# Яндекс обфусцирует классы, поэтому ищем по частичному совпадению [class*='...'].
# При поломке — открой https://yandex.ru/maps/?text=кафе+москва в DevTools
# и найди актуальные классы для контейнера списка и карточки.

_YANDEX_URL = "https://yandex.ru/maps/?text={query}"

# Контейнер со списком результатов
_SEL_LIST = "[class*='search-list-view']"

# Отдельная карточка компании в списке
_SEL_CARD = [
    "li[class*='search-snippet-view']",
    "[class*='search-business-snippet-view']",
    "li.listitem",
]

# Название компании внутри карточки
_SEL_TITLE = [
    "[class*='search-snippet-view__title']",
    "[class*='business-snippet-view__title']",
    "h2[class*='title']",
    "h3[class*='title']",
    "span[class*='name']",
]

# Сайт в детальной панели (открывается при клике на карточку)
_SEL_SITE = [
    "a[data-id='website']",
    "a[class*='business-contacts'][href^='http']",
    "[class*='business-contacts-view'] a[href^='http'][target='_blank']",
    "[class*='orgcard-contact'] a[href^='http']",
    "[class*='card-feature'] a[href^='http'][target='_blank']",
    "a[class*='site'][href^='http']",
]

# Телефон в детальной панели
_SEL_PHONE = [
    "a[href^='tel:']",
    "span[class*='business-phone-view__phone']",
    "[class*='phone-view'] span",
    "[class*='contact-item_type_phones']",
]

# Адрес в детальной панели
_SEL_ADDRESS = [
    "[class*='business-card-view__address']",
    "[class*='address-view__text']",
    "[class*='card-feature__value']:first-child",
]

# ── Вспомогательные функции ───────────────────────────────────────────────────


def _jitter(lo: float, hi: float) -> float:
    return random.uniform(lo, hi)


async def _first_text(handle, selectors: list[str]) -> str:
    """Возвращает текст первого найденного элемента среди списка селекторов."""
    for sel in selectors:
        try:
            el = await handle.query_selector(sel)
            if el:
                txt = await el.text_content()
                if txt and txt.strip():
                    return txt.strip()
        except Exception:
            continue
    return ""


async def _first_attr(handle, selectors: list[str], attr: str) -> str:
    """Возвращает атрибут первого найденного элемента."""
    for sel in selectors:
        try:
            el = await handle.query_selector(sel)
            if el:
                val = await el.get_attribute(attr)
                if val and val.strip():
                    return val.strip()
        except Exception:
            continue
    return ""


def _clean_url(raw: str) -> str:
    """Убирает UTM-метки и Яндекс-редиректы из URL."""
    if not raw:
        return ""
    # Яндекс иногда оборачивает ссылку в /maps/redirect?url=...
    if "url=" in raw and ("redirect" in raw or "redir" in raw):
        import urllib.parse
        try:
            qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(raw).query))
            raw = urllib.parse.unquote(qs.get("url", raw))
        except Exception:
            pass
    try:
        p = urlparse(raw)
        if p.scheme in ("http", "https") and p.netloc:
            # Оставляем схему + хост + путь без UTM-мусора
            return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}" or raw
    except Exception:
        pass
    return raw


def _clean_phone(raw: str) -> str:
    """Нормализует телефонный номер."""
    if not raw:
        return ""
    # Убираем всё, кроме цифр и +
    digits = re.sub(r"[^\d+]", "", raw)
    return digits if len(digits) >= 7 else ""


def _find_chromium() -> str | None:
    """Ищет системный Chromium; возвращает None → playwright найдёт свой."""
    candidates = [
        "/opt/pw-browsers/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


# ── Главная функция ───────────────────────────────────────────────────────────


async def scrape_yandex_maps(
    query: str,
    max_results: int = 20,
    headless: bool = True,
) -> list[dict]:
    """Парсит Яндекс.Карты и возвращает список компаний.

    Параметры:
        query       — поисковый запрос («строительные компании Казань»)
        max_results — сколько компаний собрать максимум
        headless    — False = открыть браузер в окне (удобно для отладки)

    Возвращает list[dict] с ключами: name, site, phone, address.
    """
    results: list[dict] = []
    seen_names: set[str] = set()

    chromium_path = _find_chromium()
    if chromium_path:
        print(f"[Maps] Используется Chromium: {chromium_path}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=chromium_path,
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1366,768",
                "--disable-extensions",
            ],
        )
        context = await browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
            },
        )
        # Скрываем признак автоматизации
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        page = await context.new_page()
        try:
            search_url = _YANDEX_URL.format(query=quote(query))
            print(f"[Maps] Открываю: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded",
                            timeout=PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(_jitter(*DELAY_PAGE_LOAD))

            # Ждём появления списка результатов
            try:
                await page.wait_for_selector(_SEL_LIST, timeout=SELECTOR_TIMEOUT)
            except PwTimeout:
                print("[Maps] ⚠ Список результатов не появился.")
                print("[Maps]   Вероятно, Яндекс показал капчу или заблокировал IP.")
                print("[Maps]   Запусти с headless=False для визуальной проверки.")
                await browser.close()
                return []

            # Прокручиваем список для подгрузки карточек
            scroll_rounds = max(2, min(max_results // 4, 8))
            for _ in range(scroll_rounds):
                await page.keyboard.press("End")
                await asyncio.sleep(_jitter(*DELAY_SCROLL))
                await page.keyboard.press("PageDown")
                await asyncio.sleep(_jitter(*DELAY_SCROLL))

            # Ищем карточки по нескольким вариантам селекторов
            cards = []
            for sel in _SEL_CARD:
                cards = await page.query_selector_all(sel)
                if cards:
                    print(f"[Maps] Найдено карточек: {len(cards)} (селектор: {sel})")
                    break

            if not cards:
                print("[Maps] Карточки не найдены — возможно, Яндекс сменил вёрстку.")
                await browser.close()
                return []

            # Перебираем карточки
            for card in cards:
                if len(results) >= max_results:
                    break
                try:
                    name = await _first_text(card, _SEL_TITLE)
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)

                    # Клик по карточке → открывается детальная панель
                    await card.scroll_into_view_if_needed()
                    await card.click()
                    await asyncio.sleep(_jitter(*DELAY_AFTER_CLICK))

                    # Сайт: сначала href атрибут, потом текст ссылки
                    raw_site = await _first_attr(page, _SEL_SITE, "href")
                    if not raw_site:
                        raw_site = await _first_text(page, _SEL_SITE)
                    site = _clean_url(raw_site)

                    # Телефон: из href="tel:..." или текст
                    raw_phone = await _first_attr(page, _SEL_PHONE, "href")
                    if raw_phone.startswith("tel:"):
                        raw_phone = raw_phone[4:]
                    if not raw_phone:
                        raw_phone = await _first_text(page, _SEL_PHONE)
                    phone = _clean_phone(raw_phone)

                    address = await _first_text(page, _SEL_ADDRESS)

                    entry = {
                        "name": name,
                        "site": site,
                        "phone": phone,
                        "address": address,
                    }
                    results.append(entry)
                    print(
                        f"[Maps] ✓ {name[:45]:<45} | "
                        f"сайт: {(site or '—')[:35]:<35} | тел: {phone or '—'}"
                    )

                    await asyncio.sleep(_jitter(*DELAY_BETWEEN_CARDS))

                except PwTimeout:
                    print("[Maps] Таймаут при обработке карточки, пропускаем")
                except Exception as exc:
                    print(f"[Maps] Ошибка карточки: {exc}")

        finally:
            await browser.close()

    print(f"\n[Maps] Итого собрано: {len(results)} компаний")
    return results
