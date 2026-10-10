import json

from pydantic import ValidationError

from biohucker.llm.types import (
    ChatModel,
    LLMUnavailable,
    Message,
    RunResult,
    Tool,
    ToolCall,
    ToolError,
)

MAX_REQUESTS = 4


def run_tool_loop(
    model: ChatModel,
    system: str,
    messages: list[Message],
    tools: list[Tool],
    max_requests: int = MAX_REQUESTS,
    stop_on: frozenset[str] | set[str] = frozenset(),
) -> RunResult:
    """Гоняет модель, пока она вызывает инструменты, но не больше max_requests запросов.

    Успешный вызов инструмента из stop_on завершает цикл сразу, без ещё одного запроса
    за текстом ответа: дальше решает вызывающий код.
    """
    history = [*messages]
    by_name = {tool.name: tool for tool in tools}
    schemas = [tool.schema() for tool in tools]
    called: list[str] = []

    for _ in range(max_requests):
        try:
            response = model.complete([{"role": "system", "content": system}, *history], schemas)
        except LLMUnavailable:
            return RunResult(reply="", messages=history, tool_calls_made=called, degraded=True)

        history.append(_assistant_message(response.content, response.tool_calls))
        if not response.tool_calls:
            return RunResult(
                reply=response.content or "",
                messages=history,
                tool_calls_made=called,
                degraded=False,
            )

        for call in response.tool_calls:
            content, ok = _execute(call, by_name)
            if ok:
                called.append(call.name)
            history.append({"role": "tool", "tool_call_id": call.id, "content": content})
        if stop_on.intersection(called):
            return RunResult(reply="", messages=history, tool_calls_made=called, degraded=False)

    return RunResult(reply="", messages=history, tool_calls_made=called, degraded=True)


def _execute(call: ToolCall, tools: dict[str, Tool]) -> tuple[str, bool]:
    tool = tools.get(call.name)
    if tool is None:
        return f"Ошибка: инструмента {call.name} нет. Доступны: {', '.join(tools) or 'нет'}.", False
    try:
        args = tool.args_model.model_validate_json(call.arguments or "{}")
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'аргументы'}: {e['msg']}"
            for e in error.errors()
        )
        return f"Ошибка валидации аргументов: {problems}. Исправь и вызови снова.", False
    try:
        result = tool.handler(args)
    except ToolError as error:
        return f"Ошибка: {error}", False
    return json.dumps(result, ensure_ascii=False, default=str), True


def _assistant_message(content: str | None, tool_calls: list[ToolCall]) -> Message:
    message: Message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in tool_calls
        ]
    return message
