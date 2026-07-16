#!/usr/bin/env python3
"""
Слой 3: удаление зелёного/синего фона через CorridorKey.

Уровень автоматизации: полностью автоматизировано.

Использование:
    python3 produce_keying.py --idea-id <uuid> --raw-footage <путь> --output-dir ./assets
"""

import argparse
import os


def run_corridorkey_inference(raw_footage_path: str, output_dir: str,
                               screen_color: str = "auto") -> str:
    """Заглушка: вызов CorridorKey CLI/engine для инференса.

    Реальная интеграция — CLI из github.com/nikopueringer/CorridorKey
    (`corridorkey_cli.py run_inference`) либо async-движок из
    99oblivius/CorridorKey-Engine для батчевой обработки через JSON-RPC.
    Требует GPU (минимум 6-8GB VRAM).
    """
    raise NotImplementedError("Дописать вызов CorridorKey CLI/engine")


def save_asset_record(idea_id: str, file_path: str, conn_params: dict) -> str:
    """Заглушка: INSERT в content.assets с asset_type='keyed_footage'."""
    raise NotImplementedError("Дописать INSERT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idea-id", required=True)
    parser.add_argument("--raw-footage", required=True)
    parser.add_argument("--output-dir", default="./assets")
    parser.add_argument("--screen-color", choices=["auto", "green", "blue"], default="auto")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    output_path = run_corridorkey_inference(args.raw_footage, args.output_dir, args.screen_color)
    asset_id = save_asset_record(args.idea_id, output_path, conn_params)

    print(f"Кеинг готов: {asset_id} -> {output_path}")


if __name__ == "__main__":
    main()
