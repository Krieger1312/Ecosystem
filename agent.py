import anthropic


class AutonomousAgent:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.memory = []

    def _get_tools(self):
        return [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "cache_control": {"type": "ephemeral"}
            }
        ]

    def run(self, user_query: str):
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
