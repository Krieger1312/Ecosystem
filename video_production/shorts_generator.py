#!/usr/bin/env python3
"""
shorts_generator.py — ИИ-пайплайн генерации YouTube Shorts (9:16).

Шаги пайплайна:
  1. generate_script(topic)   — Claude пишет сценарий в виде JSON-массива сцен
  2. generate_audio(script)   — edge-tts озвучивает текст голосом Dmitry
  3. generate_visuals(script) — DALL-E 3 рисует вертикальный кадр для каждой сцены
  4. assemble_video(...)      — moviepy монтирует видео с субтитрами и аудио

Запуск:
  python shorts_generator.py --topic "Интересные факты о капибаре"
  python shorts_generator.py --topic "5 советов по Python" --output video.mp4
"""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import numpy as np

# ── Константы ─────────────────────────────────────────────────────────────────

SHORT_W    = 1080           # ширина кадра (9:16)
SHORT_H    = 1920           # высота кадра
VOICE      = "ru-RU-DmitryNeural"
FONT_SIZE  = 72             # размер шрифта субтитров (px)
FONT_PAD   = 48             # горизонтальный отступ текста от края

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 1: Генерация сценария через Claude
# ─────────────────────────────────────────────────────────────────────────────

_SCRIPT_SYSTEM = """\
Ты — сценарист YouTube Shorts. Напиши сценарий ролика (~60 слов).
Разбей его на 4–6 коротких фраз; каждая фраза — одна сцена.
Для каждой сцены придумай image_prompt на английском для DALL-E 3:
вертикальная иллюстрация 9:16, яркие цвета, flat/vector стиль, БЕЗ текста.

Ответ СТРОГО в виде JSON-массива без пояснений:
[{"text": "фраза", "image_prompt": "DALL-E prompt"}, ...]
"""


def generate_script(topic: str) -> list[dict]:
    """Шаг 1 — Claude генерирует сценарий Short'са по заданной теме.

    Возвращает список сцен: [{"text": ..., "image_prompt": ...}, ...].
    При отсутствии ANTHROPIC_API_KEY возвращает сухой пример.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[Script] ANTHROPIC_API_KEY не задан — используем заглушку")
        return _dry_script(topic)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    print(f"[Script] Генерирую сценарий по теме: «{topic}»...")
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=_SCRIPT_SYSTEM,
        messages=[{"role": "user", "content": f"Тема: {topic}"}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        script = json.loads(raw)
        assert isinstance(script, list) and script
        print(f"[Script] ✓ Готово: {len(script)} сцен")
        return script
    except (json.JSONDecodeError, AssertionError) as exc:
        print(f"[Script] ⚠ Парсинг JSON не удался ({exc}), используем заглушку")
        return _dry_script(topic)


def _dry_script(topic: str) -> list[dict]:
    return [
        {
            "text": f"Привет! Сегодня мы поговорим о теме: {topic}.",
            "image_prompt": (
                f"bright colorful illustration about {topic}, "
                "vertical 9:16, no text, flat design, vibrant colors"
            ),
        },
        {
            "text": "Это важная и интересная тема современности.",
            "image_prompt": (
                "abstract burst of ideas and light, dynamic composition, "
                "vertical 9:16, no text, flat vector style"
            ),
        },
        {
            "text": "Подпишись на канал, чтобы не пропускать ничего интересного!",
            "image_prompt": (
                "subscribe notification bell, social media thumbs up, "
                "cheerful illustration, vertical 9:16, no text, flat design"
            ),
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 2: Озвучка через edge-tts
# ─────────────────────────────────────────────────────────────────────────────

async def generate_audio(script: list[dict], output_path: Path) -> bool:
    """Шаг 2 — Генерирует аудиофайл audio.mp3 из текста сценария.

    Использует edge-tts (голос ru-RU-DmitryNeural).
    Возвращает True при успехе, False при ошибке.
    """
    try:
        import edge_tts
    except ImportError:
        print("[Audio] ⚠ edge-tts не установлен (pip install edge-tts)")
        return False

    full_text = " ".join(s["text"] for s in script)
    print(f"[Audio] Озвучиваю {len(full_text)} симв. голосом {VOICE}...")

    try:
        communicate = edge_tts.Communicate(full_text, VOICE)
        await communicate.save(str(output_path))
        print(f"[Audio] ✓ Аудио сохранено → {output_path}")
        return True
    except Exception as exc:
        print(f"[Audio] ⚠ Ошибка генерации аудио: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 3: Генерация изображений через DALL-E 3
# ─────────────────────────────────────────────────────────────────────────────

async def generate_visuals(script: list[dict], output_dir: Path) -> list[Path]:
    """Шаг 3 — Генерирует по одному PNG 1080×1920 на каждую сцену.

    Использует DALL-E 3 (1024×1792) и масштабирует до SHORT_W×SHORT_H.
    При недоступности OPENAI_API_KEY создаёт цветные заглушки через PIL.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for i, scene in enumerate(script):
        dest = output_dir / f"scene_{i:02d}.png"
        print(f"[Visual] Сцена {i + 1}/{len(script)}: {scene['image_prompt'][:55]}...")

        result = await _generate_vertical_image(scene["image_prompt"], dest)
        if result is None:
            result = _make_fallback_image(i, dest)
        paths.append(result)

    print(f"[Visual] ✓ Готово: {len(paths)} изображений")
    return paths


async def _generate_vertical_image(prompt: str, output_path: Path) -> Path | None:
    """Генерирует вертикальное изображение через DALL-E 3 (размер 1024×1792).

    Подход аналогичен generate_game_icon из tools/image_generator.py,
    но использует нативный 9:16 формат DALL-E для лучшего качества.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import AsyncOpenAI

        client   = AsyncOpenAI(api_key=api_key)
        response = await client.images.generate(
            model="dall-e-3",
            prompt=f"{prompt} Vertical 9:16 composition, no text.",
            size="1024x1792",
            n=1,
        )
        url = response.data[0].url
        img_bytes = await asyncio.to_thread(_download, url)
        if img_bytes is None:
            return None

        return await asyncio.to_thread(_save_as_png, img_bytes, output_path)

    except Exception as exc:
        print(f"[Visual] ⚠ DALL-E ошибка: {exc}")
        return None


def _download(url: str) -> bytes | None:
    try:
        import requests
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        print(f"[Visual] ⚠ Ошибка скачивания: {exc}")
        return None


def _save_as_png(img_bytes: bytes, output_path: Path) -> Path:
    """Масштабирует изображение до SHORT_W×SHORT_H и сохраняет как PNG."""
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize((SHORT_W, SHORT_H), Image.LANCZOS)
    img.save(output_path, "PNG")
    return output_path


def _make_fallback_image(index: int, output_path: Path) -> Path:
    """Создаёт однотонный градиентный фон-заглушку через PIL."""
    from PIL import Image, ImageDraw

    palette = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560", "#2b2d42"]
    color   = palette[index % len(palette)]
    img     = Image.new("RGB", (SHORT_W, SHORT_H), color)
    draw    = ImageDraw.Draw(img)
    # Лёгкая сетка для визуальной структуры
    for y in range(0, SHORT_H, 100):
        draw.line([(0, y), (SHORT_W, y)], fill="#ffffff18", width=1)
    for x in range(0, SHORT_W, 100):
        draw.line([(x, 0), (x, SHORT_H)], fill="#ffffff18", width=1)
    img.save(output_path, "PNG")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 4: Монтаж через moviepy
# ─────────────────────────────────────────────────────────────────────────────

def assemble_video(
    image_paths: list[Path],
    script: list[dict],
    audio_path: Path | None,
    output_path: Path,
) -> bool:
    """Шаг 4 — Собирает финальное видео 9:16 с субтитрами и аудиодорожкой.

    Возвращает True при успехе, False при ошибке.
    """
    try:
        from moviepy.editor import (
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_videoclips,
        )
    except ImportError:
        print("[Video] ⚠ moviepy не установлен (pip install moviepy)")
        return False

    print("[Video] Начинаю монтаж...")

    # Загружаем аудио и определяем общую длительность
    audio_clip  = None
    total_dur   = None

    if audio_path and audio_path.exists():
        try:
            audio_clip = AudioFileClip(str(audio_path))
            total_dur  = audio_clip.duration
            print(f"[Video] Длина аудио: {total_dur:.1f} сек")
        except Exception as exc:
            print(f"[Video] ⚠ Не удалось загрузить аудио: {exc}")

    if total_dur is None:
        # Оценка по количеству слов (~2.5 слова/сек для русского TTS)
        total_words = sum(len(s["text"].split()) for s in script)
        total_dur   = max(total_words / 2.5, len(script) * 2.0)

    # Равномерно делим время между сценами
    n         = max(len(image_paths), 1)
    scene_dur = total_dur / n

    # Собираем клипы сцена за сценой
    clips: list = []
    for i, (img_path, scene) in enumerate(zip(image_paths, script)):
        try:
            base = ImageClip(str(img_path)).set_duration(scene_dur)
        except Exception as exc:
            print(f"[Video] ⚠ Сцена {i + 1} пропущена ({exc})")
            continue

        sub       = _make_subtitle_clip(scene["text"], scene_dur)
        composite = CompositeVideoClip([base, sub], size=(SHORT_W, SHORT_H))
        clips.append(composite)
        print(f"[Video] Сцена {i + 1}/{n} готова ({scene_dur:.1f} сек)")

    if not clips:
        print("[Video] ✗ Нет готовых клипов для сборки")
        return False

    video = concatenate_videoclips(clips, method="compose")

    # Накладываем аудио (обрезаем по длине видео)
    if audio_clip:
        audio_clip = audio_clip.subclip(0, min(audio_clip.duration, video.duration))
        video      = video.set_audio(audio_clip)

    # Рендеринг
    success = _render(video, output_path, has_audio=audio_clip is not None)

    # Освобождаем ресурсы
    video.close()
    for c in clips:
        c.close()
    if audio_clip:
        audio_clip.close()

    return success


def _render(video, output_path: Path, has_audio: bool) -> bool:
    """Пишет видеофайл; при ошибке делает одну резервную попытку."""
    common = dict(
        fps=30,
        codec="libx264",
        audio_codec="aac" if has_audio else None,
        logger=None,
    )
    for attempt, extra in enumerate(
        [{"preset": "ultrafast"}, {}],  # попытка 1: быстро, попытка 2: дефолт
        start=1,
    ):
        try:
            video.write_videofile(str(output_path), **common, **extra)
            print(f"[Video] ✓ Готово → {output_path}")
            return True
        except Exception as exc:
            print(f"[Video] ⚠ Попытка {attempt} не удалась: {exc}")
            if output_path.exists():
                output_path.unlink()

    print("[Video] ✗ Не удалось записать видео")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Субтитры (PIL, без ImageMagick)
# ─────────────────────────────────────────────────────────────────────────────

def _make_subtitle_clip(text: str, duration: float):
    """Создаёт прозрачный клип с субтитрами через PIL.

    Жёлтый текст (#FFEB00) с чёрной обводкой, выровнен по центру экрана.
    Не требует ImageMagick — работает везде, где установлен Pillow.
    """
    from moviepy.editor import ImageClip
    from PIL import Image, ImageDraw

    font  = _load_font(FONT_SIZE)
    max_w = SHORT_W - FONT_PAD * 2
    lines = _wrap_text(text, font, max_w)
    line_h = _line_height(font)

    total_h = len(lines) * line_h
    # Центр экрана по вертикали
    start_y = (SHORT_H - total_h) // 2

    canvas = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)
    stroke = 3

    for li, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw   = bbox[2] - bbox[0]
        x    = (SHORT_W - tw) // 2
        y    = start_y + li * line_h

        # Чёрная обводка (8 направлений)
        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 220))

        # Основной текст — жёлтый
        draw.text((x, y), line, font=font, fill=(255, 235, 0, 255))

    frame    = np.array(canvas)
    rgb      = frame[:, :, :3]
    alpha    = frame[:, :, 3].astype(float) / 255.0

    clip = ImageClip(rgb, ismask=False).set_duration(duration)
    mask = ImageClip(alpha, ismask=True).set_duration(duration)
    return clip.set_mask(mask)


def _load_font(size: int):
    """Ищет системный TTF-шрифт с поддержкой кириллицы."""
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue

    # Попытка через fontconfig (Linux)
    try:
        import subprocess
        out = subprocess.check_output(
            ["fc-list", ":lang=ru", "--format=%{file}\n"],
            timeout=3, stderr=subprocess.DEVNULL,
        ).decode()
        for path in out.strip().splitlines():
            path = path.strip()
            if path.endswith((".ttf", ".otf")):
                try:
                    return ImageFont.truetype(path, size)
                except (IOError, OSError):
                    continue
    except Exception:
        pass

    print("[Subtitle] ⚠ TrueType шрифт не найден, текст может быть мелким")
    return ImageFont.load_default()


def _line_height(font) -> int:
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = draw.textbbox((0, 0), "Ай", font=font)
    return int((bbox[3] - bbox[1]) * 1.3)


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """Разбивает текст на строки, не превышающие max_width пикселей."""
    from PIL import Image, ImageDraw
    draw   = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words  = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test

    if current:
        lines.append(current)
    return lines or [text]


# ─────────────────────────────────────────────────────────────────────────────
# Главный пайплайн
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(topic: str, output_path: Path) -> None:
    """Запускает полный пайплайн: тема → сценарий → аудио → визуал → видео."""
    work_dir  = output_path.parent / f".shorts_{output_path.stem}"
    audio_out = work_dir / "audio.mp3"
    images_dir = work_dir / "images"
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  YouTube Shorts Generator")
    print(f"  Тема:  {topic}")
    print(f"  Выход: {output_path}")
    print(f"{'='*55}\n")

    # 1. Сценарий
    script = generate_script(topic)
    print()

    # 2. Озвучка
    await generate_audio(script, audio_out)
    print()

    # 3. Изображения
    image_paths = await generate_visuals(script, images_dir)
    print()

    # 4. Монтаж
    assemble_video(
        image_paths,
        script,
        audio_out if audio_out.exists() else None,
        output_path,
    )

    if output_path.exists():
        size_mb = output_path.stat().st_size / 1_048_576
        print(f"\n✅ final_short.mp4 готов ({size_mb:.1f} МБ) → {output_path}\n")
    else:
        print("\n⚠ Видео не было создано. Проверьте установку moviepy и ffmpeg.\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ИИ-генератор YouTube Shorts 9:16"
    )
    parser.add_argument(
        "--topic", required=True,
        help="Тема ролика (напр. «Факты о капибаре»)",
    )
    parser.add_argument(
        "--output", default="final_short.mp4", type=Path,
        help="Путь для сохранения (по умолчанию: final_short.mp4)",
    )
    args = parser.parse_args()
    asyncio.run(run_pipeline(args.topic, args.output))


if __name__ == "__main__":
    main()
