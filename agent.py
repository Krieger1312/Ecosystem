import urllib.request

import anthropic


class AutonomousAgent:
    def __init__(
        self,
        api_key: str | None = None,
        max_memory_len: int = 10,
        messages_to_compact: int = 6,
        max_iterations: int = 15,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.memory = []
        # после скольких сообщений в истории запускаем сжатие
        self.max_memory_len = max_memory_len
        # сколько самых старых сообщений сжимаем за один раз
        self.messages_to_compact = messages_to_compact
        # жёсткий лимит шагов агент-цикла на одну задачу — защита от зацикливания
        self.max_iterations = max_iterations
        # суммарный расход токенов за всё время жизни агента (включая сжатие памяти)
        self.total_tokens_spent = 0

    def _track_usage(self, usage, step_label: str):
        """Логирует и накапливает токены, потраченные на один вызов API."""
        self.total_tokens_spent += usage.input_tokens + usage.output_tokens
        print(
            f"{step_label} завершён. Потрачено токенов: "
            f"{usage.input_tokens} / {usage.output_tokens} "
            f"(всего за сессию: {self.total_tokens_spent})"
        )

    def _compact_memory(self):
        """Сжимает старые сообщения в self.memory в одну выжимку, чтобы не раздувать контекст и не платить за токены старой истории."""
        if len(self.memory) <= self.max_memory_len:
            return

        # если первым сообщением в памяти случайно оказался системный промпт — не трогаем его
        offset = 1 if self.memory and self.memory[0].get("role") == "system" else 0
        old_messages = self.memory[offset:offset + self.messages_to_compact]

        # превращаем старые сообщения в простой текстовый лог для модели-сумматора
        log_text = "\n".join(f"{m['role']}: {m['content']}" for m in old_messages)

        # дешёвая быстрая модель делает выжимку — полноценный Opus для этого не нужен
        summary_response = self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            system="Сделай максимально краткую техническую выжимку фактов из этого лога действий бота",
            messages=[{"role": "user", "content": log_text}]
        )
        self._track_usage(summary_response.usage, "Сжатие памяти")
        summary = summary_response.content[0].text

        # заменяем сжатые сообщения одним архивным сообщением, остальная история остаётся как есть
        archive_message = {"role": "user", "content": f"Архив предыдущих действий: {summary}"}
        self.memory = (
            self.memory[:offset]
            + [archive_message]
            + self.memory[offset + self.messages_to_compact:]
        )

    def _get_tools(self):
        return [
            {
                # клиентский (не серверный) инструмент — нужен, чтобы самим
                # контролировать и обрезать результат до отправки его обратно в API
                "name": "fetch_webpage",
                "description": "Загружает содержимое веб-страницы по URL и возвращает её текст.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL страницы для загрузки"}
                    },
                    "required": ["url"]
                },
                "cache_control": {"type": "ephemeral"}
            }
        ]

    def _fetch_webpage(self, url: str) -> str:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return f"Ошибка загрузки {url}: {e}"

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполняет инструмент и жёстко обрезает результат — защита от огромных HTML-портянок в контексте."""
        if tool_name == "fetch_webpage":
            result = self._fetch_webpage(tool_input.get("url", ""))
        else:
            result = f"Неизвестный инструмент: {tool_name}"

        max_len = 4000
        if len(result) > max_len:
            result = result[:max_len] + "\n...[ТЕКСТ ОБРЕЗАН ДЛЯ ЭКОНОМИИ ТОКЕНОВ]..."
        return result

    def run(self, user_query: str):
        # сжимаем историю до того, как добавим новый запрос и обратимся к основной модели
        self._compact_memory()

        self.memory.append({"role": "user", "content": user_query})

        system_prompt = [
            {
                "type": "text",
                "text": (
                    "Ты — автономный ИИ-агент. Твоя цель — выполнять задачи пользователя, "
                    "используя доступные инструменты. Думай логически и пошагово."
                ),
                "cache_control": {"type": "ephemeral"}
            }
        ]

        response = None
        for iteration in range(1, self.max_iterations + 1):
            print(f"Агент думает (шаг {iteration}/{self.max_iterations})...")
            try:
                response = self.client.messages.create(
                    model="claude-opus-4-8",
                    max_tokens=1500,
                    system=system_prompt,
                    tools=self._get_tools(),
                    messages=self.memory
                )
            except anthropic.APIStatusError as e:
                print(f"Ошибка API: {e.status_code} {e.message}")
                raise

            self._track_usage(response.usage, f"Шаг {iteration}")
            self.memory.append({"role": "assistant", "content": response.content})

            # модель закончила без запроса инструментов — задача выполнена
            if response.stop_reason != "tool_use":
                return response

            # модель запросила один или несколько инструментов — выполняем и возвращаем результаты
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text
                    })
            self.memory.append({"role": "user", "content": tool_results})
        else:
            # цикл исчерпал все итерации, не дойдя до финального ответа модели
            print("Достигнут лимит итераций. Остановка для экономии бюджета")

        return response


if __name__ == "__main__":
    agent = AutonomousAgent(api_key="invalid_test_key")
    try:
        agent.run("Найди последние новости про ИИ")
    except anthropic.APIStatusError as e:
        print(f"Ожидаемая ошибка авторизации (ключ тестовый): {e.status_code}")
