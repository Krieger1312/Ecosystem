"""Общие утилиты для работы с Puppeteer MCP-сервером.

Puppeteer MCP даёт только puppeteer_evaluate (произвольный JS в контексте страницы),
puppeteer_fill (мгновенное заполнение без задержки) и puppeteer_click.
Node-уровневый page.type(selector, text, {delay}) здесь недоступен — его аналог
реализован внутри type_and_submit() через JS с setTimeout(40мс) между символами.
"""
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import AutonomousAgent

# Биржи фриланса вёрстают форму отклика по-разному; пробуем по очереди
# самые распространённые CSS-селекторы поля ввода
PROPOSAL_FIELD_SELECTORS = [
    "textarea[name*='message' i]",
    "textarea[name*='response' i]",
    "textarea[name*='body' i]",
    "textarea[placeholder*='отклик' i]",
    "textarea[placeholder*='сообщ' i]",
    "textarea[id*='proposal' i]",
    "textarea[id*='response' i]",
    "textarea[class*='proposal' i]",
    "[contenteditable='true']",
    "textarea",
]

SUBMIT_BUTTON_SELECTORS = [
    "button[type='submit']",
    "button[class*='submit' i]",
    "button[class*='send' i]",
    "input[type='submit']",
]

# Puppeteer по умолчанию запускает headed-браузер (headless:false);
# на сервере без X-дисплея и при работе под root нужны явные опции
HEADLESS_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--no-sandbox", "--disable-setuid-sandbox"],
}


def parse_evaluate_result(raw: str) -> dict:
    """Извлекает JSON из текстового ответа puppeteer_evaluate.

    Формат MCP-сервера (выяснен живой проверкой, в документации отсутствует):
      "Execution result:\\n<JSON>\\n\\nConsole output:\\n<логи>"
    Транспортные ошибки (session.call_tool бросает исключение) попадают в raw
    как "Ошибка вызова инструмента …" — обрабатываем и их.
    """
    if is_tool_error(raw):
        return {"ok": False, "error": raw}
    marker = "Execution result:\n"
    json_part = raw
    if marker in raw:
        json_part = raw.split(marker, 1)[1]
    json_part = json_part.split("\n\nConsole output:")[0]
    try:
        return json.loads(json_part)
    except (json.JSONDecodeError, ValueError):
        return {"ok": False, "error": f"Не удалось разобрать ответ puppeteer_evaluate: {raw}"}


def is_tool_error(result: str) -> bool:
    """Возвращает True для любого вида ошибок, которые _execute_tool кладёт в строку.

    _execute_tool порождает два разных префикса:
      "[ОШИБКА ИНСТРУМЕНТА] …" — инструмент вернул isError=True (MCP result);
      "Ошибка вызова инструмента …" — session.call_tool бросил исключение.
    Также обрабатываем "инструмент не найден" (нет маршрутизации).
    """
    lower = result.lower()
    return (
        lower.startswith("[ошибка")
        or lower.startswith("ошибка вызова инструмента")
        or "не найден ни на одном" in lower
    )


async def navigate(agent: "AutonomousAgent", url: str, launch_options: dict | None = None) -> None:
    """Переходит по url и бросает RuntimeError при неудаче."""
    opts = launch_options or HEADLESS_LAUNCH_OPTIONS
    result = await agent._execute_tool(
        "puppeteer_navigate",
        {"url": url, "launchOptions": opts, "allowDangerous": True},
    )
    if is_tool_error(result):
        raise RuntimeError(f"Не удалось открыть {url}: {result}")


async def type_and_submit(
    agent: "AutonomousAgent",
    message: str,
    field_selectors: list[str] | None = None,
    button_selectors: list[str] | None = None,
) -> None:
    """Печатает message в первое найденное текстовое поле, затем нажимает submit.

    Использует puppeteer_evaluate с JS-таймером (40мс/символ) вместо
    Node-уровневого page.type() — последний у MCP-сервера недоступен.
    """
    fields = field_selectors or PROPOSAL_FIELD_SELECTORS
    buttons = button_selectors or SUBMIT_BUTTON_SELECTORS

    type_script = f"""
        (async () => {{
            const candidates = {json.dumps(fields)};
            let field = null;
            for (const sel of candidates) {{
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {{ field = el; break; }}
            }}
            if (!field) return {{ ok: false, error: 'Текстовое поле отклика не найдено' }};
            field.focus();
            const text = {json.dumps(message)};
            const isEditable = field.isContentEditable;
            for (const ch of text) {{
                if (isEditable) {{
                    document.execCommand('insertText', false, ch);
                }} else {{
                    field.value += ch;
                    field.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                await new Promise(r => setTimeout(r, 40));
            }}
            return {{ ok: true }};
        }})()
    """
    raw = await agent._execute_tool("puppeteer_evaluate", {"script": type_script})
    result = parse_evaluate_result(raw)
    if not result.get("ok"):
        raise RuntimeError(f"Не удалось напечатать текст: {result.get('error', raw)}")

    last_err = None
    for selector in buttons:
        click_result = await agent._execute_tool("puppeteer_click", {"selector": selector})
        if not is_tool_error(click_result):
            return
        last_err = click_result
    raise RuntimeError(f"Не удалось нажать кнопку отправки: {last_err}")
