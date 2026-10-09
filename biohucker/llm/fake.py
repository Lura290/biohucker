import json
from itertools import count

from biohucker.llm.types import LLMUnavailable, Message, ModelResponse, ToolCall

_ids = count(1)


class FakeLLM:
    """Модель для тестов: отдаёт заранее заданные ответы по очереди и запоминает запросы."""

    def __init__(self, script: list[ModelResponse | LLMUnavailable]) -> None:
        self._script = list(script)
        self.received: list[list[Message]] = []

    @property
    def requests(self) -> int:
        return len(self.received)

    def complete(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        self.received.append(messages)
        if not self._script:
            raise AssertionError("FakeLLM: сценарий закончился, а модель снова вызвана")
        step = self._script.pop(0)
        if isinstance(step, LLMUnavailable):
            raise step
        return step

    @staticmethod
    def text(content: str) -> ModelResponse:
        return ModelResponse(content=content)

    @staticmethod
    def tool_call(name: str, **arguments: object) -> ModelResponse:
        call = ToolCall(id=f"call_{next(_ids)}", name=name, arguments=json.dumps(arguments))
        return ModelResponse(content=None, tool_calls=[call])
