from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

# Сообщения в формате OpenAI Chat Completions — его же понимает OpenRouter.
Message = dict[str, Any]


class LLMUnavailable(Exception):
    """Модель недоступна: нет ключа, лимит (429), ошибка сервера или таймаут."""


class ToolError(Exception):
    """Инструмент отклонил аргументы; текст уходит модели, чтобы она исправилась."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any], dict]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON-строка, как её прислала модель


@dataclass(frozen=True)
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    """Один запрос к модели. Бросает LLMUnavailable, если ответа не будет."""

    def complete(self, messages: list[Message], tools: list[dict]) -> ModelResponse: ...


@dataclass(frozen=True)
class RunResult:
    reply: str
    messages: list[Message]
    tool_calls_made: list[str]
    degraded: bool
