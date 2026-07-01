"""Оркестратор генерации HTML5-игр по тренду для Яндекс.Игры.

Полный цикл:
  1. get_current_trends()           — получает топ-3 тренда
  2. GameDirectorAgent.analyze_and_route_trend(trend)
                                    — Claude выбирает жанр и тему (clicker /
                                      runner / falling_objects) и печатает
                                      обоснование прямо в консоль
  3. build_game(genre, theme)       — подставляет плейсхолдеры в нужный шаблон
  4. zip_game()                     — пакует в .zip для Яндекс.Игр

Запуск:
  python trend_game_orchestrator.py
  python trend_game_orchestrator.py --trend "Капибара"
  python trend_game_orchestrator.py --trend "Хомяк" --output builds/
"""
import argparse
import re
import zipfile
from pathlib import Path

from trend_analyzer import get_current_trends
from core.game_director import GameDirectorAgent

# ── Пути ──────────────────────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
TEMPLATES  = _HERE / "templates"
OUTPUT_DIR = _HERE / "output"

# ── Конфигурация жанров ────────────────────────────────────────────────────────
# Для каждого жанра задаём:
#   js   — шаблон игровой логики
#   html — шаблон HTML-обёртки
#   keys — ВСЕ плейсхолдеры {{...}}, которые встречаются в шаблонах жанра
#           (ключи — имена полей в theme_settings от GameDirectorAgent)

GENRE_CONFIG: dict[str, dict] = {
    "clicker": {
        "js":   TEMPLATES / "clicker_template.js",
        "html": TEMPLATES / "index_template.html",
        "keys": {
            "game_title", "hero_name", "click_emoji", "currency_name",
            "bg_color", "primary_color", "secondary_color", "accent_color", "text_color",
            "upgrade_1_name", "upgrade_1_desc", "upgrade_1_emoji",
            "upgrade_2_name", "upgrade_2_desc", "upgrade_2_emoji",
            "upgrade_3_name", "upgrade_3_desc", "upgrade_3_emoji",
        },
    },
    "runner": {
        "js":   TEMPLATES / "runner_template.js",
        "html": TEMPLATES / "canvas_index.html",
        "keys": {
            "game_title", "player_emoji", "obstacle_emoji", "collectible_emoji",
            "score_label", "bg_color", "ground_color",
            "primary_color", "secondary_color", "accent_color", "text_color",
        },
    },
    "falling_objects": {
        "js":   TEMPLATES / "falling_objects_template.js",
        "html": TEMPLATES / "canvas_index.html",
        "keys": {
            "game_title", "hero_name", "player_emoji",
            "good_object_emoji", "bad_object_emoji",
            "score_label", "lives_label",
            "bg_color", "primary_color", "secondary_color", "accent_color", "text_color",
        },
    },
}


# ── Подстановка плейсхолдеров ─────────────────────────────────────────────────

def _apply(text: str, settings: dict) -> str:
    """Заменяет {{KEY}} → settings[key] (регистр KEY → snake_case в settings)."""
    def replacer(m):
        key = m.group(1).lower()   # {{GAME_TITLE}} → "game_title"
        return str(settings.get(key, m.group(0)))   # незнакомый ключ — оставить

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", replacer, text)


# ── Сборка ────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name, flags=re.UNICODE).strip("_").lower()[:40] or "game"


def build_game(trend: str, genre: str, theme: dict, output_root: Path) -> Path:
    """Читает шаблоны жанра, подставляет theme и записывает файлы игры.

    Возвращает путь к собранной папке.
    """
    cfg = GENRE_CONFIG.get(genre)
    if cfg is None:
        print(f"[Build] Неизвестный жанр «{genre}», откат на clicker")
        cfg = GENRE_CONFIG["clicker"]

    game_dir = output_root / f"{_slugify(trend)}_{genre}"
    game_dir.mkdir(parents=True, exist_ok=True)

    js_src   = cfg["js"].read_text(encoding="utf-8")
    html_src = cfg["html"].read_text(encoding="utf-8")

    (game_dir / "game.js").write_text(_apply(js_src, theme),   encoding="utf-8")
    (game_dir / "index.html").write_text(_apply(html_src, theme), encoding="utf-8")

    # проверяем, нет ли незаменённых плейсхолдеров
    combined = (game_dir / "game.js").read_text() + (game_dir / "index.html").read_text()
    missed   = re.findall(r"\{\{[A-Z0-9_]+\}\}", combined)
    if missed:
        print(f"[Build] ⚠ Незаменённые плейсхолдеры: {sorted(set(missed))}")

    print(f"[Build] ✓ Игра [{genre}] собрана → {game_dir}")
    return game_dir


def zip_game(game_dir: Path) -> Path:
    """Упаковывает папку в .zip. index.html в корне архива — требование Яндекс.Игр."""
    zip_path = game_dir.parent / f"{game_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(game_dir.iterdir()):
            zf.write(f, arcname=f.name)
    print(f"[Zip]   ✓ Архив готов → {zip_path}")
    return zip_path


# ── Главный сценарий ──────────────────────────────────────────────────────────

def run(trend: str | None = None, output_root: Path = OUTPUT_DIR) -> Path:
    """Полный цикл: тренд → Director → сборка → zip.

    Выводит в консоль лог рассуждений Директора о выборе жанра.
    Возвращает путь к .zip-архиву.
    """
    # 1. Получаем тренд
    if trend is None:
        trends = get_current_trends(n=3)
        trend  = trends[0]
        print(f"\n[Orchestrator] Актуальные тренды: {trends}")
        print(f"[Orchestrator] Выбран главный тренд: «{trend}»\n")
    else:
        print(f"\n[Orchestrator] Используем тренд: «{trend}»\n")

    # 2. GameDirectorAgent решает жанр и тему
    director = GameDirectorAgent()
    decision = director.analyze_and_route_trend(trend)

    genre = decision["selected_genre"]
    theme = decision["theme_settings"]
    just  = decision.get("justification", "—")

    # Итоговый лог решения
    print(f"\n{'='*55}")
    print(f"  ТРЕНД:        {trend}")
    print(f"  ЖАНР:         {genre.upper()}")
    print(f"  ОБОСНОВАНИЕ:  {just}")
    print(f"  НАЗВАНИЕ:     {theme.get('game_title', '—')}")
    print(f"{'='*55}\n")

    # 3. Сборка игры
    game_dir = build_game(trend, genre, theme, output_root)

    # 4. Упаковка
    zip_path = zip_game(game_dir)

    print(f"\n✅ Готово! Загружай на Яндекс.Игры: {zip_path}\n")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генератор HTML5-игр по интернет-тренду для Яндекс.Игр"
    )
    parser.add_argument("--trend",  default=None,
                        help="Конкретный тренд (иначе — Google Trends / резерв)")
    parser.add_argument("--output", default=str(OUTPUT_DIR), type=Path,
                        help=f"Папка для собранных игр (по умолчанию: {OUTPUT_DIR})")
    args = parser.parse_args()
    run(trend=args.trend, output_root=args.output)


if __name__ == "__main__":
    main()
