"""GameDirectorAgent — ИИ-геймдизайнер, выбирающий жанр и тему игры по тренду.

Единственный публичный метод: analyze_and_route_trend(trend_topic) -> dict
Возвращает:
  {
    "selected_genre":  "clicker" | "runner" | "falling_objects" | "quiz" | "merge",
    "justification":   "Короткое объяснение выбора жанра",
    "theme_settings":  { ... плейсхолдеры для выбранного шаблона ... },
    "icon_prompt":     "Описание для DALL-E 3"
  }
"""
import json
import os
import re

_MODEL = "claude-sonnet-4-6"

_DIRECTOR_SYSTEM = """\
Ты — ведущий геймдизайнер. Я дам тебе актуальный интернет-тренд.
Твоя задача:
1. Проанализировать суть тренда.
2. Выбрать из пяти жанров тот, который лучше всего передаёт эмоции тренда:
   - clicker       — тренды про накопление, фарм, «нажми N раз»
   - runner        — тренды про движение, скорость, побег
   - falling_objects — тренды про реакцию, сортировку, выбор
   - quiz          — тренды про информацию, знания, сериалы, исторических \
или публичных личностей; генерируй ровно 10 тематических вопросов с 4 \
вариантами ответа (поле "questions" в theme_settings)
   - merge         — тренды про развитие, рост или эволюцию чего-либо; \
генерируй цепочку из ровно 11 стадий эволюции объекта (поле "stages" \
в theme_settings)
3. Вернуть JSON строгого формата с полями: selected_genre (строка), \
justification (короткое объяснение выбора), theme_settings \
(объект со всеми полями выбранного шаблона), \
icon_prompt (детальное описание на английском для DALL-E 3: сочная, \
кликабельная 2D-иконка в flat/vector стиле без текста, передающая \
суть игры и тренда).

Отвечай СТРОГО валидным JSON — без пояснений до или после JSON.
"""

# ── Схемы theme_settings (показываются Claude как образец) ────────────────────

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

_SCHEMA_QUIZ = """\
{
  "game_title": "...",
  "score_label": "очки",
  "bg_color": "#rrggbb",
  "primary_color": "#rrggbb",
  "secondary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "text_color": "#rrggbb",
  "questions": [
    {"q": "Вопрос 1?", "o": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"], "a": 0},
    {"q": "Вопрос 2?", "o": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"], "a": 2},
    ... (ровно 10 вопросов; a = индекс правильного ответа 0–3)
  ]
}"""

_SCHEMA_MERGE = """\
{
  "game_title": "...",
  "score_label": "очки",
  "bg_color": "#rrggbb",
  "primary_color": "#rrggbb",
  "secondary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "text_color": "#rrggbb",
  "stages": [
    {"emoji": "🌱", "name": "Стадия 1"},
    {"emoji": "🌿", "name": "Стадия 2"},
    ... (ровно 11 стадий от простейшей до финальной)
  ]
}"""

_USER_TMPL = """\
Тренд: «{trend}»

Выбери один жанр из пяти и заполни theme_settings по его схеме:

CLICKER (кликер/идл) — накопление, фарм:
{schema_clicker}

RUNNER (раннер) — движение, скорость, побег:
{schema_runner}

FALLING_OBJECTS (ловилка) — реакция, сортировка:
{schema_falling}

QUIZ (викторина) — знания, факты, сериалы, личности:
{schema_quiz}

MERGE (слияние/эволюция) — рост, развитие, эволюция:
{schema_merge}

Вернуть строго:
{{
  "selected_genre": "clicker" | "runner" | "falling_objects" | "quiz" | "merge",
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
        self._client = anthropic.Anthropic(api_key=key) if key else None

    def analyze_and_route_trend(self, trend_topic: str) -> dict:
        """Анализирует тренд, выбирает жанр и возвращает параметры оформления."""
        if self._client is None:
            print("[Director] API-ключ не задан, используем dry-run данные")
            return self._dry_run(trend_topic)

        prompt = _USER_TMPL.format(
            trend=trend_topic,
            schema_clicker=_SCHEMA_CLICKER,
            schema_runner=_SCHEMA_RUNNER,
            schema_falling=_SCHEMA_FALLING,
            schema_quiz=_SCHEMA_QUIZ,
            schema_merge=_SCHEMA_MERGE,
        )
        print(f"[Director] Запрашиваю Claude для тренда «{trend_topic}»...")
        msg = self._client.messages.create(
            model=_MODEL,
            max_tokens=2000,
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
    _DRY_GENRE_CYCLE = ["clicker", "runner", "falling_objects", "quiz", "merge"]
    _dry_counter = 0

    def _dry_run(self, trend: str) -> dict:
        """Циклически перебирает жанры для тестирования без API."""
        genre = self._DRY_GENRE_CYCLE[self._dry_counter % len(self._DRY_GENRE_CYCLE)]
        GameDirectorAgent._dry_counter += 1

        just = {
            "clicker":         "Тренд про накопление — идеально для кликера.",
            "runner":          "Тренд динамичный — раннер передаёт движение.",
            "falling_objects": "Тренд про выбор/реакцию — ловилка в тему.",
            "quiz":            "Тренд информационный — викторина проверит знания.",
            "merge":           "Тренд про эволюцию — merge передаёт рост.",
        }[genre]
        print(f"[Director] ✦ Выбран жанр (dry-run): {genre.upper()}")
        print(f"[Director] ✦ Обоснование: {just}")

        ts = self._base_settings(trend)

        if genre == "clicker":
            ts.update({
                "click_emoji":    "🎮", "currency_name":   "Очки",
                "upgrade_1_name": "Помощник", "upgrade_1_desc": "+1/сек", "upgrade_1_emoji": "🐾",
                "upgrade_2_name": "Завод",    "upgrade_2_desc": "+8/сек", "upgrade_2_emoji": "🏭",
                "upgrade_3_name": "Мегабот",  "upgrade_3_desc": "+50/сек","upgrade_3_emoji": "🤖",
            })
        elif genre == "runner":
            ts.update({
                "player_emoji": "🏃", "obstacle_emoji": "🪨",
                "collectible_emoji": "⭐", "score_label": "м",
                "ground_color": "#5d4037",
            })
        elif genre == "falling_objects":
            ts.update({
                "player_emoji": "🧺", "good_object_emoji": "⭐",
                "bad_object_emoji": "💣", "score_label": "Очки",
                "lives_label": "жизни",
            })
        elif genre == "quiz":
            ts.update({
                "score_label": "Очки",
                "questions": [
                    {
                        "q": f"Вопрос {i + 1} по теме «{trend[:20]}»?",
                        "o": ["Ответ А", "Ответ Б", "Ответ В", "Ответ Г"],
                        "a": i % 4,
                    }
                    for i in range(10)
                ],
            })
        else:  # merge
            ts.update({
                "score_label": "Очки",
                "stages": [
                    {"emoji": e, "name": n}
                    for e, n in [
                        ("🌱", "Начало"),  ("🌿", "Рост"),     ("🌾", "Развитие"),
                        ("🌳", "Зрелость"),("🌲", "Сила"),     ("🌴", "Расцвет"),
                        ("🌺", "Красота"), ("🌻", "Яркость"),  ("🌹", "Совершенство"),
                        ("🏆", "Победа"),  ("👑", "Легенда"),
                    ]
                ],
            })

        icon_prompts = {
            "clicker":         "flat vector 2D game icon, cute idle clicker game, colorful coins and upgrade buttons, no text, vibrant colors, mobile game style",
            "runner":          "flat vector 2D game icon, endless runner game, character jumping over obstacles, dynamic pose, no text, bright cartoon style",
            "falling_objects": "flat vector 2D game icon, catch falling objects game, basket catching stars, colorful falling items, no text, flat design",
            "quiz":            "flat vector 2D game icon, trivia quiz game, question mark and lightbulb, bright colorful icons, no text, knowledge theme",
            "merge":           "flat vector 2D game icon, merge evolution game, glowing tiles merging, progression chain, no text, gradient colors",
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
