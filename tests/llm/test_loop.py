from pydantic import BaseModel, Field

from biohucker.llm import FakeLLM, LLMUnavailable, Tool, run_tool_loop


class EnergyArgs(BaseModel):
    energy: int = Field(ge=1, le=10)


def make_tool(calls: list[EnergyArgs]) -> Tool:
    def handler(args: EnergyArgs) -> dict:
        calls.append(args)
        return {"saved": True}

    return Tool(
        name="save_energy", description="Сохранить энергию", args_model=EnergyArgs, handler=handler
    )


def test_text_reply_ends_loop_after_one_request() -> None:
    llm = FakeLLM([FakeLLM.text("Во сколько ты лёг?")])

    result = run_tool_loop(llm, "system", [{"role": "user", "content": "привет"}], tools=[])

    assert result.reply == "Во сколько ты лёг?"
    assert result.degraded is False
    assert result.tool_calls_made == []
    assert llm.requests == 1


def test_valid_tool_call_reaches_handler_and_result_goes_back_to_model() -> None:
    calls: list[EnergyArgs] = []
    llm = FakeLLM([FakeLLM.tool_call("save_energy", energy=7), FakeLLM.text("Записал.")])

    result = run_tool_loop(
        llm, "system", [{"role": "user", "content": "энергия 7"}], [make_tool(calls)]
    )

    assert calls == [EnergyArgs(energy=7)]
    assert result.reply == "Записал."
    assert result.tool_calls_made == ["save_energy"]
    tool_messages = [m for m in result.messages if m["role"] == "tool"]
    assert '"saved": true' in tool_messages[0]["content"]


def test_invalid_arguments_never_reach_handler_and_model_sees_the_error() -> None:
    calls: list[EnergyArgs] = []
    llm = FakeLLM(
        [
            FakeLLM.tool_call("save_energy", energy=15),
            FakeLLM.tool_call("save_energy", energy=9),
            FakeLLM.text("Готово."),
        ]
    )

    result = run_tool_loop(
        llm, "system", [{"role": "user", "content": "энергия 15"}], [make_tool(calls)]
    )

    assert calls == [EnergyArgs(energy=9)]
    first_tool_reply = next(m for m in result.messages if m["role"] == "tool")
    assert "ошибка" in first_tool_reply["content"].lower()
    assert result.reply == "Готово."


def test_unknown_tool_is_reported_to_model() -> None:
    llm = FakeLLM([FakeLLM.tool_call("delete_everything"), FakeLLM.text("Ок.")])

    result = run_tool_loop(llm, "system", [], tools=[])

    tool_reply = next(m for m in result.messages if m["role"] == "tool")
    assert "delete_everything" in tool_reply["content"]
    assert result.tool_calls_made == []


def test_loop_stops_after_four_requests_and_degrades() -> None:
    llm = FakeLLM([FakeLLM.tool_call("save_energy", energy=15)] * 10)

    result = run_tool_loop(llm, "system", [], [make_tool([])])

    assert llm.requests == 4
    assert result.degraded is True


def test_unavailable_model_degrades_without_raising() -> None:
    llm = FakeLLM([LLMUnavailable("429")])

    result = run_tool_loop(llm, "system", [], tools=[])

    assert result.degraded is True
    assert result.reply == ""


def test_input_messages_are_not_mutated() -> None:
    history = [{"role": "user", "content": "привет"}]

    run_tool_loop(FakeLLM([FakeLLM.text("Привет!")]), "system", history, tools=[])

    assert history == [{"role": "user", "content": "привет"}]
