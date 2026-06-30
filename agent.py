import ipaddress
import socket
import time
import urllib.request
from urllib.parse import urlparse

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
        # суммарный расход токенов за всё время жизни агента (включая сжатие памяти и кэш)
        self.total_tokens_spent = 0

    def _track_usage(self, usage, step_label: str):
        """Логирует и накапливает токены, потраченные на один вызов API (включая кэш)."""
        cache_created = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        self.total_tokens_spent += usage.input_tokens + usage.output_tokens + cache_created + cache_read
        print(
            f"{step_label} завершён. Потрачено токенов: "
            f"{usage.input_tokens} / {usage.output_tokens} "
            f"(кэш: запись {cache_created} / чтение {cache_read}; всего за сессию: {self.total_tokens_spent})"
        )

    def _create_message(self, **kwargs):
        """Обёртка над messages.create с retry/backoff на временные ошибки API (429/529)."""
        max_retries = 3
        delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                return self.client.messages.create(**kwargs)
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 529) and attempt < max_retries:
                    print(f"Временная ошибка API ({e.status_code}), повтор через {delay}с...")
                    time.sleep(delay)
                    delay *= 2
                    continue
                print(f"Ошибка API: {e.status_code} {e.message}")
                raise

    @staticmethod
    def _block_type(block):
        """Достаёт type из блока контента независимо от того, dict это или SDK-объект."""
        if isinstance(block, dict):
            return block.get("type")
        return getattr(block, "type", None)

    def _has_tool_use(self, message) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(self._block_type(b) == "tool_use" for b in content)

    def _stringify_content(self, content) -> str:
        """Превращает content сообщения (строку, текстовый блок, tool_use/tool_result) в читаемый текст для лога."""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content)

        parts = []
        for block in content:
            block_type = self._block_type(block)
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                parts.append(text)
            elif block_type == "tool_use":
                name = block.get("name") if isinstance(block, dict) else getattr(block, "name", "?")
                tool_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                parts.append(f"[вызов инструмента {name}({tool_input})]")
            elif block_type == "tool_result":
                result = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                parts.append(f"[результат инструмента: {result}]")
            else:
                parts.append(str(block))
        return " ".join(parts)

    def _compact_memory(self):
        """Сжимает старые сообщения в self.memory в одну выжимку, чтобы не раздувать контекст и не платить за токены старой истории."""
        if len(self.memory) <= self.max_memory_len:
            return

        # если первым сообщением в памяти случайно оказался системный промпт — не трогаем его
        offset = 1 if self.memory and self.memory[0].get("role") == "system" else 0
        end = min(offset + self.messages_to_compact, len(self.memory))

        # не разрываем пару assistant(tool_use) -> user(tool_result): если граница среза
        # попадает сразу после сообщения с tool_use, забираем в срез и его tool_result
        while end < len(self.memory) and self._has_tool_use(self.memory[end - 1]):
            end += 1

        old_messages = self.memory[offset:end]
        remaining = self.memory[end:]

        # превращаем старые сообщения в читаемый текстовый лог для модели-сумматора
        log_text = "\n".join(
            f"{m['role']}: {self._stringify_content(m['content'])}" for m in old_messages
        )

        # дешёвая быстрая модель делает выжимку — полноценный Opus для этого не нужен
        summary_response = self._create_message(
            model="claude-haiku-4-5",
            max_tokens=500,
            system="Сделай максимально краткую техническую выжимку фактов из этого лога действий бота",
            messages=[{"role": "user", "content": log_text}]
        )
        self._track_usage(summary_response.usage, "Сжатие памяти")
        summary = summary_response.content[0].text
        archive_text = f"Архив предыдущих действий: {summary}"

        # вставляем архив так, чтобы не нарушить обязательное чередование ролей user/assistant
        if not remaining:
            # дальше в self.memory всегда добавляется новое user-сообщение (запрос или
            # tool_result) — поэтому архив оформляем от лица ассистента
            self.memory = self.memory[:offset] + [{"role": "assistant", "content": archive_text}]
        elif remaining[0]["role"] == "user":
            # сливаем архив в первое оставшееся user-сообщение вместо отдельной вставки
            first_content = remaining[0]["content"]
            if isinstance(first_content, list):
                remaining[0]["content"] = [{"type": "text", "text": archive_text}] + first_content
            else:
                remaining[0]["content"] = f"{archive_text}\n\n{first_content}"
            self.memory = self.memory[:offset] + remaining
        else:
            self.memory = self.memory[:offset] + [{"role": "user", "content": archive_text}] + remaining

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

    def _is_safe_url(self, url: str) -> bool:
        """Блокирует SSRF: только http/https и только публичные адреса (никаких localhost, метадаты облака, локальной сети, file://)."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        try:
            addrinfo = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror:
            return False
        for *_rest, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True

    def _fetch_webpage(self, url: str) -> str:
        if not self._is_safe_url(url):
            return f"Запрос заблокирован: небезопасный или внутренний адрес ({url})"
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
            response = self._create_message(
                model="claude-opus-4-8",
                max_tokens=1500,
                system=system_prompt,
                tools=self._get_tools(),
                messages=self.memory
            )

            self._track_usage(response.usage, f"Шаг {iteration}")
            self.memory.append({"role": "assistant", "content": response.content})

            # ответ обрезан лимитом max_tokens — продолжать опасно, отдаём как есть с предупреждением
            if response.stop_reason == "max_tokens":
                print(f"Внимание: ответ модели обрезан лимитом max_tokens на шаге {iteration}")
                return response

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

            # сжимаем память и внутри цикла — длинная задача не должна раздувать контекст
            self._compact_memory()
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
