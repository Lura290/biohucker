import logging
import time
from collections.abc import Callable

import httpx
import openai

from biohucker.llm.types import LLMUnavailable, Message, ModelResponse, ToolCall

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 20.0
RETRY_DELAY_SECONDS = 2.0

log = logging.getLogger(__name__)


class OpenRouterModel:
    """ChatModel поверх OpenRouter. Один повтор на 429/5xx/таймаут, дальше LLMUnavailable."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._model = model
        self._sleep = sleep
        self._client = (
            openai.OpenAI(
                api_key=api_key,
                base_url=BASE_URL,
                timeout=TIMEOUT_SECONDS,
                max_retries=0,
                http_client=http_client,
            )
            if api_key
            else None
        )

    def complete(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        if self._client is None:
            raise LLMUnavailable("Не задан OPENROUTER_API_KEY")
        try:
            return self._request(messages, tools)
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError) as e:
            log.warning(
                "openrouter: %s, повтор через %.0f с", type(e).__name__, RETRY_DELAY_SECONDS
            )
            self._sleep(RETRY_DELAY_SECONDS)
        try:
            return self._request(messages, tools)
        except openai.OpenAIError as error:
            raise _unavailable(error) from error

    def _request(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        extra = {"tools": tools} if tools else {}
        try:
            completion = self._client.chat.completions.create(
                model=self._model, messages=messages, **extra
            )
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError):
            raise
        except openai.OpenAIError as error:
            raise _unavailable(error) from error

        usage = completion.usage
        log.info(
            "openrouter: model=%s tokens=%s",
            self._model,
            usage.total_tokens if usage else "?",
        )
        if not completion.choices:
            raise LLMUnavailable("OpenRouter вернул пустой ответ")
        message = completion.choices[0].message
        calls = [
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
            for call in message.tool_calls or []
        ]
        return ModelResponse(content=message.content, tool_calls=calls)


def _unavailable(error: openai.OpenAIError) -> LLMUnavailable:
    status = getattr(error, "status_code", None)
    reason = _provider_reason(error)
    log.warning("openrouter: недоступен (%s, status=%s): %s", type(error).__name__, status, reason)
    return LLMUnavailable(f"{type(error).__name__} (status={status}): {reason}")


def _provider_reason(error: openai.OpenAIError) -> str:
    """Текст причины от OpenRouter: какой лимит сработал, у кого и до какого времени."""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        details = body.get("error", body)
        if isinstance(details, dict) and details.get("message"):
            return str(details["message"])
    return str(error)
