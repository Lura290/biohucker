import json

import httpx
import pytest

from biohucker.llm import LLMUnavailable
from biohucker.llm.openrouter import OpenRouterModel


def completion(message: dict) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test/model",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def make_model(handler, sleeps: list[float] | None = None) -> OpenRouterModel:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterModel(
        api_key="sk-test",
        model="test/model",
        http_client=client,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_parses_tool_call_and_sends_model_and_tools() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "propose_checkin", "arguments": '{"energy": 6}'},
                        }
                    ],
                }
            ),
        )

    tools = [{"type": "function", "function": {"name": "propose_checkin", "parameters": {}}}]
    response = make_model(handler).complete([{"role": "user", "content": "энергия 6"}], tools)

    assert response.tool_calls[0].name == "propose_checkin"
    assert json.loads(response.tool_calls[0].arguments) == {"energy": 6}
    assert seen[0]["model"] == "test/model"
    assert seen[0]["tools"] == tools


def test_text_reply_without_tools_omits_tools_field() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion({"role": "assistant", "content": "Привет!"}))

    response = make_model(handler).complete([{"role": "user", "content": "привет"}], [])

    assert response.content == "Привет!"
    assert response.tool_calls == []
    assert "tools" not in seen[0]


def test_rate_limit_is_retried_once_after_two_seconds() -> None:
    statuses = iter([429, 200])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status == 429:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=completion({"role": "assistant", "content": "ок"}))

    response = make_model(handler, sleeps).complete([], [])

    assert response.content == "ок"
    assert sleeps == [2.0]


@pytest.mark.parametrize("status", [429, 502])
def test_repeated_transient_error_raises_unavailable(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(LLMUnavailable):
        make_model(handler).complete([], [])
    assert calls == 2


def test_timeout_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMUnavailable):
        make_model(handler).complete([], [])


def test_bad_key_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(LLMUnavailable):
        make_model(handler).complete([], [])
    assert calls == 1


def test_missing_key_raises_without_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("запроса быть не должно")

    model = OpenRouterModel(
        api_key=None, model="m", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(LLMUnavailable, match="OPENROUTER_API_KEY"):
        model.complete([], [])


def test_empty_choices_raise_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = completion({"role": "assistant", "content": "x"})
        body["choices"] = []
        return httpx.Response(200, json=body)

    with pytest.raises(LLMUnavailable):
        make_model(handler).complete([], [])


def test_unavailable_error_carries_provider_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "google/gemma is temporarily rate-limited upstream"}}
        )

    with pytest.raises(LLMUnavailable, match="rate-limited upstream"):
        make_model(handler).complete([], [])
