from datetime import date, time

import pytest

from biohucker.checkin.agent import CheckinAgent
from biohucker.journal.models import CheckinEntry
from biohucker.llm import FakeLLM, LLMUnavailable

DAY = date(2026, 10, 1)
FULL = dict(
    bedtime="23:40",
    wake_time="07:10",
    energy=6,
    mood=7,
    morning_walk_min=15,
    steps=8500,
    workout_min=0,
)


def agent_with(repo, script) -> tuple[CheckinAgent, FakeLLM]:
    llm = FakeLLM(script)
    return CheckinAgent(llm, repo), llm


def test_greeting_asks_every_question_and_allows_one_phrase(repo) -> None:
    agent, llm = agent_with(repo, [])

    session = agent.start(DAY)

    greeting = session.messages[-1]["content"]
    for word in ("лёг", "встал", "Энергия", "Настроение", "прогулка", "шагов", "Тренировка"):
        assert word in greeting
    assert "одной фразой" in greeting
    assert llm.requests == 0


def test_full_answer_is_ready_after_one_request_and_nothing_saved_yet(repo) -> None:
    agent, llm = agent_with(repo, [FakeLLM.tool_call("propose_checkin", **FULL)])
    session = agent.start(DAY)

    turn = agent.reply(
        session,
        "лёг 23:40, встал 7:10, энергия 6, настроение 7, гулял 15 мин, 8500 шагов, без тренировки",
    )

    assert turn.ready is True
    assert llm.requests == 1
    assert session.draft.energy == 6
    assert session.draft.sleep_hours == 7.5
    assert repo.get(DAY) is None


def test_partial_answer_asks_only_for_missing_fields(repo) -> None:
    agent, _ = agent_with(repo, [FakeLLM.tool_call("propose_checkin", energy=6, mood=7)])
    session = agent.start(DAY)

    turn = agent.reply(session, "энергия 6, настроение 7")

    assert turn.ready is False
    assert set(turn.missing) == {"bedtime", "wake_time", "morning_walk_min", "steps", "workout_min"}
    assert "шаг" in turn.reply.lower()
    assert "энерг" not in turn.reply.lower()
    assert "настроен" not in turn.reply.lower()


def test_follow_up_answer_merges_into_draft(repo) -> None:
    rest = {k: v for k, v in FULL.items() if k not in ("energy", "mood")}
    agent, llm = agent_with(
        repo,
        [
            FakeLLM.tool_call("propose_checkin", energy=6, mood=7),
            FakeLLM.tool_call("propose_checkin", **rest),
        ],
    )
    session = agent.start(DAY)

    agent.reply(session, "энергия 6, настроение 7")
    turn = agent.reply(
        session, "лёг 23:40, встал 7:10, гулял 15 минут, 8500 шагов, не тренировался"
    )

    assert turn.ready is True
    assert (session.draft.energy, session.draft.steps) == (6, 8500)
    # модель видит всю переписку, а не только последнее сообщение
    assert any("энергия 6" in str(m.get("content")) for m in llm.received[1])


def test_out_of_range_value_never_reaches_draft(repo) -> None:
    agent, _ = agent_with(
        repo,
        [
            FakeLLM.tool_call("propose_checkin", energy=15),
            FakeLLM.text("Энергия бывает от 1 до 10 — сколько поставишь?"),
        ],
    )
    session = agent.start(DAY)

    turn = agent.reply(session, "энергия 15")

    assert session.draft.energy is None
    assert "от 1 до 10" in turn.reply
    assert turn.ready is False


def test_implausible_sleep_is_rejected_and_model_is_told_why(repo) -> None:
    agent, llm = agent_with(
        repo,
        [
            FakeLLM.tool_call("propose_checkin", bedtime="07:00", wake_time="07:30"),
            FakeLLM.text("Получилось полчаса сна — точно в 7 утра лёг?"),
        ],
    )
    session = agent.start(DAY)

    agent.reply(session, "лёг в 7, встал в 7:30")

    assert session.draft.bedtime is None
    tool_reply = next(m for m in llm.received[1] if m["role"] == "tool")
    assert "сон" in tool_reply["content"]


def test_skip_rest_makes_draft_ready_with_missing_fields(repo) -> None:
    agent, _ = agent_with(repo, [FakeLLM.tool_call("propose_checkin", energy=5, finish=True)])
    session = agent.start(DAY)

    turn = agent.reply(session, "энергия 5, остальное пропусти")

    assert turn.ready is True
    assert "steps" in turn.missing


def test_text_reply_is_passed_through_and_draft_unchanged(repo) -> None:
    agent, _ = agent_with(repo, [FakeLLM.text("Я не советую добавки — лучше спроси врача.")])
    session = agent.start(DAY)

    turn = agent.reply(session, "какой магний пить?")

    assert "врача" in turn.reply
    assert session.draft.filled_fields() == []


def test_unavailable_model_degrades_with_form_hint(repo) -> None:
    agent, _ = agent_with(repo, [LLMUnavailable("429")])
    session = agent.start(DAY)

    turn = agent.reply(session, "энергия 6")

    assert turn.degraded is True
    assert "форм" in turn.reply


def test_confirm_saves_draft_to_journal(repo) -> None:
    agent, _ = agent_with(repo, [FakeLLM.tool_call("propose_checkin", **FULL)])
    session = agent.start(DAY)
    agent.reply(session, "всё сразу")

    saved = agent.confirm(session)

    assert repo.get(DAY) == saved
    assert saved.steps == 8500
    assert session.saved is True


def test_confirm_before_ready_is_refused(repo) -> None:
    agent, _ = agent_with(repo, [])
    session = agent.start(DAY)

    with pytest.raises(ValueError):
        agent.confirm(session)
    assert repo.get(DAY) is None


def test_existing_entry_skips_questions(repo) -> None:
    repo.upsert(CheckinEntry(day=DAY, energy=6, bedtime=time(23, 0), wake_time=time(7, 0)))
    agent, _ = agent_with(repo, [])

    session = agent.start(DAY)

    assert session.already_saved is True
    assert "уже" in session.messages[-1]["content"]


def test_system_prompt_contains_date_and_safety_rules(repo) -> None:
    agent, llm = agent_with(repo, [FakeLLM.text("ок")])
    session = agent.start(DAY)

    agent.reply(session, "привет")

    system = llm.received[0][0]["content"]
    assert "2026-10-01" in system
    assert "врач" in system
