"""Анализатор актуальных трендов для генератора HTML5-игр.

Стратегия получения трендов (в порядке приоритета):
1. Google Trends Daily RSS для России — публичный, без авторизации.
2. Резервный список «вечнозелёных» трендов, если сеть недоступна.
"""
import html
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# Публичный RSS без авторизации, возвращает топ трендов за сегодня по России.
_GOOGLE_TRENDS_RSS = "https://trends.google.com/trends/trendingsearches/daily.rss?geo=RU"

# Таймаут HTTP-запроса: не хотим подвешивать скрипт, если сеть недоступна
_HTTP_TIMEOUT = 8

# Резервный список — актуальные российские интернет-тренды/мемы
_FALLBACK_TRENDS = [
    "Капибара",
    "Хомяк",
    "Манул",
    "Криптовалюта",
    "Нейросеть",
    "Космос",
    "Аниме",
    "Кот",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _fetch_google_trends(n: int = 3) -> list[str]:
    """Загружает топ-N трендов из Google Trends RSS (Россия)."""
    req = urllib.request.Request(
        _GOOGLE_TRENDS_RSS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TrendBot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    # RSS может содержать namespace-декларации, которые мешают ElementTree —
    # вырезаем их, чтобы работал xpath ".//item"
    raw = re.sub(r'\s+xmlns(?::\w+)?="[^"]+"', "", raw)
    root = ET.fromstring(raw)

    trends: list[str] = []
    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        if title and title not in trends:
            trends.append(title)
        if len(trends) >= n:
            break
    return trends


def get_current_trends(n: int = 3) -> list[str]:
    """Возвращает список из n актуальных ключевых слов/трендов.

    Сначала пробует получить живые данные из Google Trends.
    При любой ошибке сети или парсинга дополняет резервным списком.
    """
    trends: list[str] = []
    try:
        trends = _fetch_google_trends(n)
        if len(trends) >= n:
            print(f"[TrendAnalyzer] Получены тренды из Google: {trends[:n]}")
            return trends[:n]
        print(f"[TrendAnalyzer] Google вернул только {len(trends)} трендов, дополняем резервными")
    except (urllib.error.URLError, ET.ParseError, Exception) as exc:
        print(f"[TrendAnalyzer] Не удалось получить тренды из сети ({exc}), используем резервные")

    # Дополняем резервными, избегая дублей
    from_fallback = [t for t in _FALLBACK_TRENDS if not any(t in tr for tr in trends)]
    combined = (trends + from_fallback)[:n]
    print(f"[TrendAnalyzer] Тренды (резерв): {combined}")
    return combined


if __name__ == "__main__":
    print(get_current_trends())
