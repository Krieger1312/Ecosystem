"""GameDirectorAgent — ИИ-геймдизайнер, выбирающий жанр и тему игры по тренду.

Единственный публичный метод: analyze_and_route_trend(trend_topic) -> dict
Возвращает:
  {
    "selected_genre":  "clicker" | "runner" | "falling_objects",
    "justification":   "Короткое объяснение выбора жанра",
    "theme_settings":  { ... плейсхолдеры для выбранного шаблона ... }
  }
"""
import json
import os
import re

# Claude 3.7 Sonnet отозван — используем актуальную модель того же уровня
_MODEL = "claude-sonnet-4-6"

_DIRECTOR_SYSTEM = """\
Ты — ведущий геймдизайнер. Я дам тебе актуальный интернет-тренд.
Твоя задача:
1. Проанализировать суть тренда.
2. Выбрать из доступных жанров (clicker, runner, falling_objects) тот, \
который лучше всего передает эмоции тренда.
3. Вернуть JSON строгого формата с полями: selected_genre (строка), \
justification (короткое объяснение выбора), theme_settings \
(объект с цветами, emoji и названиями для подстановки в шаблон), \
icon_prompt (детальное описание на английском для DALL-E 3: сочная, \
кликабельная 2D-иконка в flat/vector стиле без текста, передающая \
суть игры и тренда).

Отвечай СТРОГО валидным JSON — без пояснений до или после JSON.
"""

# Схемы theme_settings по жанрам (показываются Claude в промпте как пример)
_SCHEMA_CLICKER = """\
{
  "game_title": "...",
  "hero_name": "...",
  "click_emoji": "...",
  "currency_name": "...",
  "bg_color": "#rrggbb",
  "primary_color": "#rrggbb",
  "secondary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "text_color": "#rrggbb",
  "upgrade_1_name": "...", "upgrade_1_desc": "+1/сек", "upgrade_1_emoji": "...",
  "upgrade_2_name": "...", "upgrade_2_desc": "+8/сек", "upgrade_2_emoji": "...",
  "upgrade_3_name": "...", "upgrade_3_desc": "+50/сек", "upgrade_3_emoji": "..."
}"""

_SCHEMA_RUNNER = """\
{
  "game_title": "...",
  "player_emoji": "...",
  "obstacle_emoji": "...",
  "collectible_emoji": "...",
  "score_label": "метры | монеты | etc.",
  "bg_color": "#rrggbb",
  "ground_color": "#rrggbb",
  "primary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "text_color": "#rrggbb"
}"""

_SCHEMA_FALLING = """\
{
  "game_title": "...",
  "hero_name": "...",
  "player_emoji": "...",
  "good_object_emoji": "...",
  "bad_object_emoji": "...",
  "score_label": "очки | монеты | etc.",
  "lives_label": "жизни | попытки | etc.",
  "bg_color": "#rrggbb",
  "primary_color": "#rrggbb",
  "secondary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "text_color": "#rrggbb"
}"""

_USER_TMPL = """\
Тренд: «{trend}»

Выбери один жанр из трёх и заполни theme_settings по его схеме:

CLICKER (кликер/идл) — подходит для трендов про накопление, фарм, "нажми N раз":
{schema_clicker}

RUNNER (раннер с прыжками) — подходит для трендов про движение, скорость, побег:
{schema_runner}

FALLING_OBJECTS (ловилка) — подходит для трендов про реакцию, сортировку, выбор:
{schema_falling}

Вернуть строго:
{{
  "selected_genre": "clicker" | "runner" | "falling_objects",
  "justification": "<одно предложение: почему именно этот жанр>",
  "theme_settings": {{ ... схема выбранного жанра ... }},
  "icon_prompt": "<детальное описание на английском для DALL-E 3, без текста, flat/vector стиль>"
}}
"""


class GameDirectorAgent:
    """ИИ-агент, принимающий решение о жанре и оформлении игры по тренду."""

    def __init__(self, api_key: str | None = None):
        import anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            self._client = anthropic.Anthropic(api_key=key)
        else:
            self._client = None   # dry-run режим

    def analyze_and_route_trend(self, trend_topic: str) -> dict:
        """Анализирует тренд, выбирает жанр и возвращает параметры оформления.

        Возвращает:
          {
            "selected_genre":  "clicker" | "runner" | "falling_objects",
            "justification":   str,
            "theme_settings":  dict   # плейсхолдеры для шаблона
          }
        При отсутствии API-ключа возвращает детерминированную заглушку.
        """
        if self._client is None:
            print("[Director] API-ключ не задан, используем dry-run данные")
            return self._dry_run(trend_topic)

        prompt = _USER_TMPL.format(
            trend=trend_topic,
            schema_clicker=_SCHEMA_CLICKER,
            schema_runner=_SCHEMA_RUNNER,
            schema_falling=_SCHEMA_FALLING,
        )
        print(f"[Director] Запрашиваю Claude для тренда «{trend_topic}»...")
        msg = self._client.messages.create(
            model=_MODEL,
            max_tokens=1500,
            system=_DIRECTOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$",          "", raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[Director] ⚠ Невалидный JSON от Claude ({exc}), откат на dry-run")
            return self._dry_run(trend_topic)

        genre = result.get("selected_genre", "clicker")
        just  = result.get("justification", "—")
        print(f"[Director] ✦ Выбран жанр: {genre.upper()}")
        print(f"[Director] ✦ Обоснование: {just}")
        return result

    # ── dry-run заглушки ──────────────────────────────────────────────────────
    _DRY_GENRE_CYCLE = ["clicker", "runner", "falling_objects"]
    _dry_counter = 0

    def _dry_run(self, trend: str) -> dict:
        """Циклически перебирает жанры, чтобы в тестах можно было увидеть все три."""
        genre = self._DRY_GENRE_CYCLE[self._dry_counter % 3]
        GameDirectorAgent._dry_counter += 1

        just = {
            "clicker": "Тренд про накопление — идеально для кликера.",
            "runner":  "Тренд динамичный — раннер передаёт движение.",
            "falling_objects": "Тренд про выбор/реакцию — ловилка в тему.",
        }[genre]
        print(f"[Director] ✦ Выбран жанр (dry-run): {genre.upper()}")
        print(f"[Director] ✦ Обоснование: {just}")

        ts = self._base_settings(trend)
        if genre == "clicker":
            ts.update({
                "click_emoji":     "🎮", "currency_name":   "Очки",
                "upgrade_1_name":  "Помощник",  "upgrade_1_desc":  "+1/сек", "upgrade_1_emoji": "🐾",
                "upgrade_2_name":  "Завод",     "upgrade_2_desc":  "+8/сек", "upgrade_2_emoji": "🏭",
                "upgrade_3_name":  "Мегабот",   "upgrade_3_desc":  "+50/сек","upgrade_3_emoji": "🤖",
            })
        elif genre == "runner":
            ts.update({
                "player_emoji": "🏃", "obstacle_emoji": "🪨",
                "collectible_emoji": "⭐", "score_label": "м",
                "ground_color": "#5d4037",
            })
        else:
            ts.update({
                "player_emoji": "🧺", "good_object_emoji": "⭐",
                "bad_object_emoji": "💣", "score_label": "Очки",
                "lives_label": "жизни",
            })

        icon_prompts = {
            "clicker":         "flat vector 2D game icon, cute idle clicker game, colorful coins and upgrade buttons, no text, vibrant colors, mobile game style",
            "runner":          "flat vector 2D game icon, endless runner game, character jumping over obstacles, dynamic pose, no text, bright cartoon style",
            "falling_objects": "flat vector 2D game icon, catch falling objects game, basket catching stars, colorful falling items, no text, flat design",
        }
        return {
            "selected_genre": genre,
            "justification":  just,
            "theme_settings": ts,
            "icon_prompt":    icon_prompts[genre],
        }

    @staticmethod
    def _base_settings(trend: str) -> dict:
        return {
            "game_title":      f"{trend[:12]}-Игра",
            "hero_name":       trend,
            "bg_color":        "#1a1a2e",
            "primary_color":   "#16213e",
            "secondary_color": "#0f3460",
            "accent_color":    "#e94560",
            "text_color":      "#ffffff",
        }
