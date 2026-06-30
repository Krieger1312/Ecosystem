import asyncio
import os
from contextlib import AsyncExitStack

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# рабочая папка filesystem-сервера — единственная зона, куда агенту разрешено писать файлы
AGENT_WORKSPACE_DIR = "agent_workspace"


class AutonomousAgent:
    def __init__(
        self,
        api_key: str | None = None,
        max_memory_len: int = 10,
        messages_to_compact: int = 6,
        max_iterations: int = 15,
    ):
        # MCP работает через async-потоки (anyio), поэтому и клиент Anthropic тоже асинхронный
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.memory = []
        # после скольких сообщений в истории запускаем сжатие
        self.max_memory_len = max_memory_len
        # сколько самых старых сообщений сжимаем за один раз
        self.messages_to_compact = messages_to_compact
        # жёсткий лимит шагов агент-цикла на одну задачу — защита от зацикливания
        self.max_iterations = max_iterations
        # суммарный расход токенов за всё время жизни агента (включая сжатие памяти и кэш)
        self.total_tokens_spent = 0

        # подключённые MCP-сессии по имени сервера (заполняются через connect_mcp_server())
        self.mcp_sessions: dict[str, ClientSession] = {}
        # маршрутизация: имя инструмента -> сессия сервера, который его предоставляет
        # (пересобирается заново при каждом вызове _get_tools())
        self._tool_routing: dict[str, ClientSession] = {}
        # держит подпроцессы серверов и сессии открытыми между вызовами run()
        self._exit_stack = AsyncExitStack()

    async def connect_mcp_server(self, name: str, command: str, args: list[str]):
        """Запускает внешний MCP-сервер как подпроцесс (stdio) и открывает с ним ClientSession.

        Ошибка подключения одного сервера не должна обрушивать всего агента —
        остальные серверы (и работа агента в целом) должны остаться рабочими.
        """
        try:
            server_params = StdioServerParameters(command=command, args=args)

            # stdio_client поднимает подпроцесс и отдаёт пару потоков чтения/записи
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            # ClientSession — это и есть протокольный уровень MCP поверх этих потоков
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            # обязательное рукопожатие перед тем, как сервером можно пользоваться
            await session.initialize()
        except Exception as e:
            print(f"Не удалось подключить MCP-сервер '{name}' ({command} {' '.join(args)}): {e}")
            return

        self.mcp_sessions[name] = session
        print(f"MCP-сервер '{name}' подключён")

    async def connect_default_servers(self):
        """Подключает три стандартных MCP-сервера агента: fetch (чтение веб-страниц),
        filesystem (чтение/запись файлов в изолированной рабочей папке) и puppeteer
        (управление полноценным браузером). Подключения независимы — отказ одного
        сервера не мешает остальным (см. connect_mcp_server)."""
        # рабочая папка filesystem-сервера должна существовать до запуска сервера
        os.makedirs(AGENT_WORKSPACE_DIR, exist_ok=True)

        # официальный fetch-сервер от Anthropic распространяется как пакет PyPI,
        # а не npm — запускается через uvx, а не через npx
        await self.connect_mcp_server("fetch", "uvx", ["mcp-server-fetch"])

        await self.connect_mcp_server(
            "filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", AGENT_WORKSPACE_DIR]
        )

        await self.connect_mcp_server(
            "puppeteer", "npx", ["-y", "@modelcontextprotocol/server-puppeteer"]
        )

    async def close(self):
        """Корректно закрывает MCP-сессию и завершает подпроцесс сервера."""
        await self._exit_stack.aclose()

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

    async def _create_message(self, **kwargs):
        """Обёртка над messages.create с retry/backoff на временные ошибки API (429/529)."""
        max_retries = 3
        delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                return await self.client.messages.create(**kwargs)
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 529) and attempt < max_retries:
                    print(f"Временная ошибка API ({e.status_code}), повтор через {delay}с...")
                    await asyncio.sleep(delay)
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

    async def _compact_memory(self):
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
        summary_response = await self._create_message(
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

    async def _get_tools(self) -> list[dict]:
        """Запрашивает списки инструментов у всех подключённых MCP-серверов и объединяет
        их в один список в формате Anthropic API. Заодно пересобирает маршрутизацию
        tool_name -> сессия, которая нужна _execute_tool() для вызова нужного сервера."""
        self._tool_routing = {}
        tools: list[dict] = []

        for session in self.mcp_sessions.values():
            mcp_tools = await session.list_tools()
            for tool in mcp_tools.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    # MCP отдаёт JSON Schema входных параметров — Anthropic ждёт её в input_schema
                    "input_schema": tool.inputSchema,
                })
                self._tool_routing[tool.name] = session

        # метка кэширования ставится на последний инструмент в ОБЪЕДИНЁННОМ списке —
        # кэшируется весь блок tools целиком, это обязательное условие Prompt Caching
        if tools:
            tools[-1]["cache_control"] = {"type": "ephemeral"}

        return tools

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Вызывает инструмент через нужную MCP-сессию (по таблице маршрутизации) и жёстко
        обрезает результат — защита от огромных ответов в контексте."""
        session = self._tool_routing.get(tool_name)
        if session is None:
            return f"Инструмент '{tool_name}' не найден ни на одном подключённом MCP-сервере"

        try:
            result = await session.call_tool(tool_name, tool_input)
        except Exception as e:
            return f"Ошибка вызова инструмента {tool_name}: {e}"

        # результат MCP — список content-блоков (обычно текстовых), склеиваем их в строку
        parts = [getattr(block, "text", None) or str(block) for block in result.content]
        result_text = "\n".join(parts)

        if result.isError:
            result_text = f"[ОШИБКА ИНСТРУМЕНТА] {result_text}"

        max_len = 4000
        if len(result_text) > max_len:
            result_text = result_text[:max_len] + "\n...[ТЕКСТ ОБРЕЗАН ДЛЯ ЭКОНОМИИ ТОКЕНОВ]..."
        return result_text

    async def run(self, user_query: str):
        # сжимаем историю до того, как добавим новый запрос и обратимся к основной модели
        await self._compact_memory()

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
            response = await self._create_message(
                model="claude-opus-4-8",
                max_tokens=1500,
                system=system_prompt,
                tools=await self._get_tools(),
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

            # модель запросила один или несколько инструментов — выполняем их через MCP
            # и собираем результаты для возврата модели
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = await self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text
                    })
            self.memory.append({"role": "user", "content": tool_results})

            # сжимаем память и внутри цикла — длинная задача не должна раздувать контекст
            await self._compact_memory()
        else:
            # цикл исчерпал лимит max_iterations, не дойдя до финального ответа модели —
            # это и есть защита от бесконечного цикла и неконтролируемого расхода бюджета
            print("Достигнут лимит итераций. Остановка для экономии бюджета")

        return response


async def main():
    agent = AutonomousAgent(api_key="invalid_test_key")
    try:
        # подключаем три стандартных сервера: fetch (чтение веб-страниц),
        # filesystem (чтение/запись в agent_workspace) и puppeteer (браузер)
        await agent.connect_default_servers()
        await agent.run("Найди последние новости про ИИ")
    except anthropic.APIStatusError as e:
        print(f"Ожидаемая ошибка авторизации (ключ тестовый): {e.status_code}")
    except Exception as e:
        print(f"Демо без реального MCP-сервера: {e}")
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
