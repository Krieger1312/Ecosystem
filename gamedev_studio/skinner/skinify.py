#!/usr/bin/env python3
"""
skinify.py — конвейер скинов кликера.
Берёт JSON-конфиг скина и собирает готовую папку + ZIP для Яндекс.Игр.

Использование:
    python skinify.py skins/cat_entrepreneur.json
    python skinify.py --all          # все скины из skins/
"""

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
TEMPLATE_DIR = SCRIPT_DIR / "template"
SKINS_DIR    = SCRIPT_DIR / "skins"
RELEASES_DIR = SCRIPT_DIR.parent / "releases"


def load_skin(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render(text: str, skin: dict) -> str:
    c = skin["colors"]
    t = skin["titles"]
    u1 = skin["upgrade1"]
    u2 = skin["upgrade2"]
    replacements = {
        "{{GAME_TITLE}}":     skin["game_title"],
        "{{CHARACTER}}":      skin["character"],
        "{{CHARACTER_NAME}}": skin["character_name"],
        "{{CURRENCY_ICON}}":  skin["currency_icon"],
        "{{CURRENCY_NAME}}":  skin["currency_name"],
        "{{SAVE_KEY}}":       skin["save_key"],
        "{{TITLES_JSON}}":    json.dumps(t, ensure_ascii=False),
        "{{TITLE_0}}":        t[0],
        "{{TITLE_MAX}}":      t[-1],
        "{{UPG1_NAME}}":      u1["name"],
        "{{UPG1_DESC}}":      u1["desc"],
        "{{UPG1_ICON}}":      u1["icon"],
        "{{UPG2_NAME}}":      u2["name"],
        "{{UPG2_DESC}}":      u2["desc"],
        "{{UPG2_ICON}}":      u2["icon"],
        "{{COLOR_BG1}}":      c["bg1"],
        "{{COLOR_BG2}}":      c["bg2"],
        "{{COLOR_ACCENT}}":   c["accent"],
        "{{COLOR_ACCENT2}}":  c["accent2"],
    }
    for key, val in replacements.items():
        text = text.replace(key, val)
    return text


def build_skin(skin_path: Path) -> Path:
    skin = load_skin(skin_path)
    skin_id = skin["id"]
    out_dir = RELEASES_DIR / skin_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Рендерим файлы шаблона
    for tmpl_file in TEMPLATE_DIR.iterdir():
        if tmpl_file.suffix in (".html", ".css", ".js"):
            rendered = render(tmpl_file.read_text(encoding="utf-8"), skin)
            (out_dir / tmpl_file.name).write_text(rendered, encoding="utf-8")

    # yandex_meta.txt
    y = skin["yandex"]
    meta_lines = [
        f"Название: {skin['game_title']}",
        "",
        f"Описание:\n{y['description']}",
        "",
        f"Теги: {y['tags']}",
        "",
        f"Категория: {y['category']}",
        "",
        f"Обложка (icon_prompt для DALL-E 3):\n{y['icon_prompt']}",
    ]
    (out_dir / "yandex_meta.txt").write_text("\n".join(meta_lines), encoding="utf-8")

    # ZIP
    zip_path = RELEASES_DIR / f"{skin_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                zf.write(f, f.name)

    kb = zip_path.stat().st_size / 1024
    print(f"[Skin] ✓ {skin['game_title']:30s}  →  releases/{skin_id}/  ({kb:.0f} КБ)")
    return zip_path


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--all":
        skins = sorted(SKINS_DIR.glob("*.json"))
        if not skins:
            print("[!] Нет скинов в skins/"); return
        for s in skins:
            build_skin(s)
        print(f"\n[Done] Собрано {len(skins)} игр")
    else:
        build_skin(Path(args[0]))


if __name__ == "__main__":
    main()
