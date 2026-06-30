import anthropic


class AutonomousAgent:
    def __init__(self, api_key: str | None = None, max_memory_len: int = 10, messages_to_compact: int = 6):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.memory = []
        # после скольких сообщений в истории запускаем сжатие
        self.max_memory_len = max_memory_len
        # сколько самых старых сообщений сжимаем за один раз
        self.messages_to_compact = messages_to_compact

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
                "type": "web_search_20260209",
                "name": "web_search",
                "cache_control": {"type": "ephemeral"}
            }
        ]

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

        print("Агент думает (используется кэш промптов)...")
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

        self.memory.append({"role": "assistant", "content": response.content})
        return response


if __name__ == "__main__":
    agent = AutonomousAgent(api_key="invalid_test_key")
    try:
        agent.run("Найди последние новости про ИИ")
    except anthropic.APIStatusError as e:
        print(f"Ожидаемая ошибка авторизации (ключ тестовый): {e.status_code}")
