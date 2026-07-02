#!/usr/bin/env python3
"""
build.py — упаковщик игры для публикации на Яндекс.Играх.

Яндекс.Игры требуют, чтобы index.html лежал в КОРНЕ ZIP-архива
(не внутри подпапки). Этот скрипт упаковывает содержимое
указанной папки без вложения в поддиректорию.

Использование:
    python build.py                              # шаблон по умолчанию: templates/clicker/
    python build.py templates/clicker/           # явно указать папку
    python build.py templates/clicker/ -o dist/game.zip   # другой выходной файл
    python build.py --list                       # показать доступные шаблоны

Структура ZIP-архива (правильная для Яндекс.Игр):
    index.html   ← в корне архива
    style.css    ← в корне архива
    game.js      ← в корне архива
    assets/      ← если есть, сохраняется со структурой
"""

import argparse
import sys
import zipfile
from pathlib import Path

# ── Константы ─────────────────────────────────────────────────────────────────

_HERE         = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
DEFAULT_INPUT = TEMPLATES_DIR / "clicker"
DEFAULT_OUTPUT = _HERE / "game_build.zip"

# Файлы/папки, которые НЕ включаем в архив
_EXCLUDE_PATTERNS = {
    ".DS_Store", "Thumbs.db", "__pycache__", ".git",
    "*.pyc", "*.pyo", "*.log",
}


def _should_exclude(path: Path) -> bool:
    """True — если файл или папку нужно пропустить."""
    name = path.name
    if name.startswith("."):      # скрытые файлы
        return True
    if name in _EXCLUDE_PATTERNS:
        return True
    # Проверяем glob-паттерны (*.pyc и т.п.)
    return any(path.match(pat) for pat in _EXCLUDE_PATTERNS if "*" in pat)


def list_templates() -> None:
    """Выводит список доступных шаблонов из папки templates/."""
    if not TEMPLATES_DIR.exists():
        print(f"Папка templates/ не найдена по пути: {TEMPLATES_DIR}")
        return
    tmpl_dirs = sorted(d for d in TEMPLATES_DIR.iterdir() if d.is_dir())
    if not tmpl_dirs:
        print("Шаблоны не найдены в templates/")
        return
    print(f"Доступные шаблоны в {TEMPLATES_DIR}:")
    for d in tmpl_dirs:
        has_index = (d / "index.html").exists()
        marker = "✓" if has_index else "⚠ (нет index.html)"
        print(f"  {marker}  {d.name}/")


def build(input_dir: Path, output_path: Path) -> None:
    """Упаковывает содержимое input_dir в output_path (ZIP).

    Все файлы кладутся в корень архива без родительской директории.
    Подпапки (assets/, img/ и т.п.) сохраняются со своей структурой.
    """
    # ── Валидация входных данных ───────────────────────────────────────────────
    if not input_dir.exists():
        print(f"[Build] ✗ Папка не найдена: {input_dir}")
        sys.exit(1)

    if not input_dir.is_dir():
        print(f"[Build] ✗ Ожидается папка, не файл: {input_dir}")
        sys.exit(1)

    index_file = input_dir / "index.html"
    if not index_file.exists():
        print(f"[Build] ⚠ Внимание: index.html не найден в {input_dir}")
        print("         Яндекс.Игры требуют index.html в корне архива")

    # ── Сбор файлов ───────────────────────────────────────────────────────────
    all_files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and not _should_exclude(p)
    )

    if not all_files:
        print(f"[Build] ✗ Нет файлов для упаковки в {input_dir}")
        sys.exit(1)

    # ── Создание архива ───────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in all_files:
            # arcname — путь внутри архива: относительно input_dir (без родительской папки)
            arcname = file_path.relative_to(input_dir)
            zf.write(file_path, arcname=arcname)
            print(f"  + {arcname}")

    # ── Итог ──────────────────────────────────────────────────────────────────
    size_kb = output_path.stat().st_size / 1024
    print(f"\n[Build] ✓ Архив готов: {output_path.resolve()}")
    print(f"        Файлов: {len(all_files)} | Размер: {size_kb:.1f} КБ")
    print(f"\n  Загружай на Яндекс.Игры: https://games.yandex.ru/studio/")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Упаковщик HTML5-игры в ZIP для Яндекс.Игр",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python build.py
  python build.py templates/clicker/
  python build.py templates/clicker/ -o dist/my_game.zip
  python build.py --list
        """,
    )
    parser.add_argument(
        "input", nargs="?", type=Path, default=DEFAULT_INPUT,
        metavar="TEMPLATE_DIR",
        help=f"Папка с игрой (по умолчанию: {DEFAULT_INPUT.relative_to(_HERE)})",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=DEFAULT_OUTPUT,
        metavar="OUTPUT.zip",
        help=f"Путь к выходному ZIP-файлу (по умолчанию: {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="Показать доступные шаблоны и выйти",
    )
    args = parser.parse_args()

    if args.list:
        list_templates()
        return

    print(f"[Build] Упаковываю: {args.input}")
    build(args.input, args.output)


if __name__ == "__main__":
    main()
