"""Генерация иконки игры через DALL-E 3."""
import asyncio
import os
from pathlib import Path


async def generate_game_icon(prompt: str, output_path: Path | str) -> Path | None:
    """Генерирует иконку 1024×1024 через DALL-E 3 и сохраняет в output_path.

    Возвращает Path к файлу или None при любой ошибке.
    """
    if not prompt:
        print("[Icon] Промпт пуст — иконка пропущена")
        return None

    output_path = Path(output_path)

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        print(f"[Icon] Запрашиваю DALL-E 3: {prompt[:80]}...")
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        image_url = response.data[0].url
        print(f"[Icon] URL получен, скачиваю...")

        image_bytes = await asyncio.to_thread(_download, image_url)
        if image_bytes is None:
            return None

        output_path.write_bytes(image_bytes)
        print(f"[Icon] ✓ Иконка сохранена → {output_path}")
        return output_path

    except Exception as exc:
        print(f"[Icon] ⚠ Не удалось сгенерировать иконку: {exc}")
        return None


def _download(url: str) -> bytes | None:
    """Синхронная загрузка URL (вызывается через asyncio.to_thread)."""
    try:
        import requests  # type: ignore
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        print(f"[Icon] ⚠ Ошибка скачивания: {exc}")
        return None
