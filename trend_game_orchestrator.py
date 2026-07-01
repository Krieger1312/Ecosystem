"""Оркестратор генерации HTML5-игр по тренду.

Полный цикл за одну команду:
  python trend_game_orchestrator.py [--trend "Капибара"] [--output output/]

1. get_current_trends()  — забирает 3 тренда (Google Trends → резерв)
2. generate_substitutions() — Claude анализирует тренд и возвращает JSON
   с параметрами оформления и контентом для плейсхолдеров шаблона
3. build_game()          — читает шаблоны, подставляет значения, пишет файлы
4. zip_game()            — упаковывает папку в .zip, готовый к загрузке на
                           portal.yandex.ru/games/
"""
import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import anthropic

from trend_analyzer import get_current_trends

# ── Пути ─────────────────────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
TEMPLATES  = _HERE / "templates"
OUTPUT_DIR = _HERE / "output"

JS_TEMPLATE   = TEMPLATES / "clicker_template.js"
HTML_TEMPLATE = TEMPLATES / "index_template.html"

# Claude 3.7 Sonnet отозван — используем актуальную модель того же уровня
_MODEL = "claude-sonnet-4-6"

# ── Промпт для генерации данных подстановки ───────────────────────────────────
_SYSTEM = """\
Ты — геймдизайнер и UX-дизайнер HTML5-кликеров для платформы Яндекс.Игры.
Получив описание тренда, ты подбираешь тематическое оформление и контент.
Отвечай СТРОГО валидным JSON — без пояснений до или после JSON.
"""

_USER_TMPL = """\
Тренд: «{trend}»

Сгенерируй JSON для HTML5-кликера по этой теме. Используй следующую схему:

{{
  "game_title":       "<название игры на русском, 2–4 слова>",
  "hero_name":        "<имя/описание главного кликабельного объекта>",
  "click_emoji":      "<один emoji главного объекта>",
  "currency_name":    "<название валюты в игре, существительное>",
  "bg_color":         "<hex-цвет фона, соответствующий теме>",
  "primary_color":    "<hex-цвет основных элементов интерфейса>",
  "secondary_color":  "<hex-цвет панелей/карточек (чуть светлее/темнее bg)>",
  "accent_color":     "<hex-цвет кнопок и акцентов (яркий, контрастный)>",
  "text_color":       "<hex-цвет текста>",
  "upgrade_1_name":   "<название дешёвого апгрейда — тематическое>",
  "upgrade_1_desc":   "<краткое описание, напр. '+1/сек'>",
  "upgrade_1_emoji":  "<emoji апгрейда 1>",
  "upgrade_2_name":   "<название среднего апгрейда>",
  "upgrade_2_desc":   "<описание>",
  "upgrade_2_emoji":  "<emoji апгрейда 2>",
  "upgrade_3_name":   "<название дорогого апгрейда>",
  "upgrade_3_desc":   "<описание>",
  "upgrade_3_emoji":  "<emoji апгрейда 3>"
}}
"""

# Все плейсхолдеры в шаблонах и соответствующие поля JSON
_PLACEHOLDER_MAP = {
    "{{GAME_TITLE}}":      "game_title",
    "{{HERO_NAME}}":       "hero_name",
    "{{CLICK_EMOJI}}":     "click_emoji",
    "{{CURRENCY_NAME}}":   "currency_name",
    "{{BG_COLOR}}":        "bg_color",
    "{{PRIMARY_COLOR}}":   "primary_color",
    "{{SECONDARY_COLOR}}": "secondary_color",
    "{{ACCENT_COLOR}}":    "accent_color",
    "{{TEXT_COLOR}}":      "text_color",
    "{{UPGRADE_1_NAME}}":  "upgrade_1_name",
    "{{UPGRADE_1_DESC}}":  "upgrade_1_desc",
    "{{UPGRADE_1_EMOJI}}": "upgrade_1_emoji",
    "{{UPGRADE_2_NAME}}":  "upgrade_2_name",
    "{{UPGRADE_2_DESC}}":  "upgrade_2_desc",
    "{{UPGRADE_2_EMOJI}}": "upgrade_2_emoji",
    "{{UPGRADE_3_NAME}}":  "upgrade_3_name",
    "{{UPGRADE_3_DESC}}":  "upgrade_3_desc",
    "{{UPGRADE_3_EMOJI}}": "upgrade_3_emoji",
}


# ── AI: генерация подстановок ─────────────────────────────────────────────────

def generate_substitutions(trend: str, api_key: str | None = None) -> dict:
    """Спрашивает Claude, какие значения подставить в шаблон для данного тренда.

    Возвращает словарь с ключами из _PLACEHOLDER_MAP.values().
    Поддерживает dry-run режим (ANTHROPIC_API_KEY не задан) — возвращает
    пример-заглушку для локального тестирования без API.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[AI] ANTHROPIC_API_KEY не задан, используем тестовые данные")
        return _dry_run_substitutions(trend)

    client = anthropic.Anthropic(api_key=key)
    prompt = _USER_TMPL.format(trend=trend)

    print(f"[AI] Запрашиваю Claude для тренда «{trend}»...")
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=800,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    # Claude иногда добавляет ```json ... ``` — убираем фencing
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    print(f"[AI] Получены данные: {data.get('game_title', '?')}")
    return data


def _dry_run_substitutions(trend: str) -> dict:
    """Тестовые данные для запуска без API-ключа."""
    slug = trend[:8]
    return {
        "game_title":      f"{trend}-Кликер",
        "hero_name":       trend,
        "click_emoji":     "🎮",
        "currency_name":   "Очки",
        "bg_color":        "#1a1a2e",
        "primary_color":   "#16213e",
        "secondary_color": "#0f3460",
        "accent_color":    "#e94560",
        "text_color":      "#ffffff",
        "upgrade_1_name":  f"{slug} Помощник",
        "upgrade_1_desc":  "+1/сек",
        "upgrade_1_emoji": "🐾",
        "upgrade_2_name":  f"{slug} Завод",
        "upgrade_2_desc":  "+8/сек",
        "upgrade_2_emoji": "🏭",
        "upgrade_3_name":  f"{slug} Мегабот",
        "upgrade_3_desc":  "+50/сек",
        "upgrade_3_emoji": "🤖",
    }


# ── Сборка игры ───────────────────────────────────────────────────────────────

def _apply_substitutions(text: str, subs: dict) -> str:
    """Заменяет все {{PLACEHOLDER}} на значения из subs."""
    for placeholder, key in _PLACEHOLDER_MAP.items():
        value = subs.get(key, placeholder)  # оставляем плейсхолдер если ключа нет
        text = text.replace(placeholder, str(value))
    return text


def _slugify(name: str) -> str:
    """Безопасное имя папки из названия тренда."""
    slug = re.sub(r"[^\w\-]", "_", name, flags=re.UNICODE).strip("_").lower()
    return slug[:40] or "game"


def build_game(trend: str, subs: dict, output_root: Path) -> Path:
    """Собирает папку с игрой: index.html + game.js (плейсхолдеры заменены).

    Возвращает путь к созданной папке.
    """
    slug      = _slugify(trend)
    game_dir  = output_root / slug
    game_dir.mkdir(parents=True, exist_ok=True)

    js_src   = JS_TEMPLATE.read_text(encoding="utf-8")
    html_src = HTML_TEMPLATE.read_text(encoding="utf-8")

    (game_dir / "game.js").write_text(
        _apply_substitutions(js_src, subs), encoding="utf-8"
    )
    (game_dir / "index.html").write_text(
        _apply_substitutions(html_src, subs), encoding="utf-8"
    )

    print(f"[Build] Игра собрана: {game_dir}")
    return game_dir


def zip_game(game_dir: Path) -> Path:
    """Упаковывает папку с игрой в .zip рядом с ней.

    Внутри архива — только содержимое папки (без родительского пути),
    так как Яндекс.Игры ожидает index.html в корне архива.
    """
    zip_path = game_dir.parent / f"{game_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in game_dir.iterdir():
            zf.write(file, arcname=file.name)
    print(f"[Zip] Архив готов: {zip_path}")
    return zip_path


# ── Главный сценарий ──────────────────────────────────────────────────────────

def run(trend: str | None = None, output_root: Path = OUTPUT_DIR) -> Path:
    """Полный цикл: тренд → AI-данные → сборка → zip.

    Возвращает путь к .zip-архиву.
    """
    if trend is None:
        trends = get_current_trends(n=3)
        trend  = trends[0]
        print(f"[Orchestrator] Выбран тренд: «{trend}» (из {trends})")
    else:
        print(f"[Orchestrator] Используем указанный тренд: «{trend}»")

    subs     = generate_substitutions(trend)
    game_dir = build_game(trend, subs, output_root)
    zip_path = zip_game(game_dir)

    print(f"\n✅ Готово! Загружай на Яндекс.Игры: {zip_path}")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генератор HTML5-кликеров по тренду для Яндекс.Игры"
    )
    parser.add_argument(
        "--trend", default=None,
        help="Конкретный тренд (если не указан — берётся из Google Trends)",
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_DIR), type=Path,
        help=f"Папка для собранных игр (по умолчанию: {OUTPUT_DIR})",
    )
    args = parser.parse_args()
    run(trend=args.trend, output_root=args.output)


if __name__ == "__main__":
    main()
