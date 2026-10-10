from datetime import date

from fastapi.testclient import TestClient

from biohucker.journal.models import CheckinEntry
from biohucker.llm import FakeLLM, LLMUnavailable
from biohucker.web.app import create_app

FULL = dict(
    bedtime="23:40",
    wake_time="07:10",
    energy=6,
    mood=7,
    morning_walk_min=15,
    steps=8500,
    workout_min=0,
)


def client_with(db_url, script) -> TestClient:
    return TestClient(create_app(database_url=db_url, model=FakeLLM(script)))


def test_home_starts_checkin_with_questions(db_url) -> None:
    client = client_with(db_url, [])

    page = client.get("/")

    assert page.status_code == 200
    assert "Во сколько лёг" in page.text
    assert 'name="text"' in page.text


def test_chat_shows_summary_and_saves_only_after_confirm(db_url) -> None:
    client = client_with(db_url, [FakeLLM.tool_call("propose_checkin", **FULL)])
    client.get("/")

    answer = client.post("/chat", data={"text": "всё сразу"}, headers={"HX-Request": "true"})

    assert answer.status_code == 200
    assert "Сохранить" in answer.text
    assert "8500" in answer.text
    journal = client.app.state.journal
    assert journal.get(date.today()) is None

    saved = client.post("/checkin/confirm", headers={"HX-Request": "true"})

    assert "Сохранено" in saved.text
    assert journal.get(date.today()).steps == 8500


def test_htmx_request_gets_fragment_and_plain_post_gets_full_page(db_url) -> None:
    client = client_with(db_url, [FakeLLM.text("Привет!"), FakeLLM.text("Ещё раз привет!")])
    client.get("/")

    fragment = client.post("/chat", data={"text": "привет"}, headers={"HX-Request": "true"})
    full = client.post("/chat", data={"text": "привет"})

    assert "<html" not in fragment.text
    assert "<html" in full.text


def test_missing_fields_are_asked_in_chat(db_url) -> None:
    client = client_with(db_url, [FakeLLM.tool_call("propose_checkin", energy=6)])
    client.get("/")

    answer = client.post("/chat", data={"text": "энергия 6"}, headers={"HX-Request": "true"})

    assert "Осталось" in answer.text
    assert "Сохранить" not in answer.text


def test_degraded_model_shows_form_link(db_url) -> None:
    client = client_with(db_url, [LLMUnavailable("429")])
    client.get("/")

    answer = client.post("/chat", data={"text": "энергия 6"}, headers={"HX-Request": "true"})

    assert 'href="/checkin/form"' in answer.text


def test_confirm_before_ready_does_not_save(db_url) -> None:
    client = client_with(db_url, [])
    client.get("/")

    answer = client.post("/checkin/confirm", headers={"HX-Request": "true"})

    assert answer.status_code == 409
    assert client.app.state.journal.get(date.today()) is None


def test_second_visit_same_day_keeps_conversation(db_url) -> None:
    client = client_with(db_url, [FakeLLM.text("Понял, а шаги?")])
    client.get("/")
    client.post("/chat", data={"text": "энергия 6"}, headers={"HX-Request": "true"})

    page = client.get("/")

    assert "Понял, а шаги?" in page.text
    assert page.text.count("Во сколько лёг") == 1


def test_existing_entry_after_restart_is_shown_instead_of_questions(db_url) -> None:
    create_app(database_url=db_url, model=FakeLLM([])).state.journal.upsert(
        CheckinEntry(day=date.today(), energy=6)
    )
    client = client_with(db_url, [])

    page = client.get("/")

    assert "уже есть" in page.text
    assert "Во сколько лёг" not in page.text


def test_model_text_is_html_escaped(db_url) -> None:
    client = client_with(db_url, [FakeLLM.text("<script>alert(1)</script>")])
    client.get("/")

    answer = client.post("/chat", data={"text": "<b>я</b>"}, headers={"HX-Request": "true"})

    assert "<script>alert(1)</script>" not in answer.text
    assert "&lt;script&gt;" in answer.text
    assert "<b>я</b>" not in answer.text


def test_empty_message_is_ignored(db_url) -> None:
    client = client_with(db_url, [])
    client.get("/")

    answer = client.post("/chat", data={"text": "   "}, headers={"HX-Request": "true"})

    assert answer.status_code == 200


def test_works_without_javascript(db_url) -> None:
    client = client_with(db_url, [FakeLLM.tool_call("propose_checkin", **FULL)])
    client.get("/")

    after_chat = client.post("/chat", data={"text": "всё сразу"}, follow_redirects=False)
    assert after_chat.status_code == 303
    assert after_chat.headers["location"] == "/"

    page = client.get("/")
    assert '<form method="post" action="/checkin/confirm"' in page.text

    after_save = client.post("/checkin/confirm", follow_redirects=False)
    assert after_save.status_code == 303
    assert client.app.state.journal.get(date.today()).steps == 8500


def test_htmx_is_served_locally_not_from_cdn(db_url) -> None:
    client = client_with(db_url, [])

    page = client.get("/")
    script = client.get("/static/htmx.min.js")

    assert 'src="/static/htmx.min.js"' in page.text
    assert "unpkg.com" not in page.text
    assert script.status_code == 200
    assert "htmx" in script.text
