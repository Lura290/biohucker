from datetime import date

import pytest
from fastapi.testclient import TestClient

from biohucker.web.app import create_app


@pytest.fixture
def client(db_url) -> TestClient:
    return TestClient(create_app(database_url=db_url))


def form(**overrides: str) -> dict[str, str]:
    data = {
        "day": "2026-10-01",
        "bedtime": "23:40",
        "wake_time": "07:10",
        "energy": "6",
        "mood": "7",
        "morning_walk_min": "15",
        "steps": "8500",
        "workout_min": "0",
        "workout_type": "",
    }
    data.update(overrides)
    return data


def test_form_page_renders_with_today_by_default(client) -> None:
    response = client.get("/checkin/form")

    assert response.status_code == 200
    assert date.today().isoformat() in response.text


def test_valid_form_saves_entry(client) -> None:
    response = client.post("/checkin/form", data=form())

    assert response.status_code == 200
    assert "Сохранено" in response.text
    entry = client.app.state.journal.get(date(2026, 10, 1))
    assert (entry.energy, entry.steps, entry.workout_min) == (6, 8500, 0)
    assert entry.sleep_hours == 7.5


def test_invalid_form_shows_field_error_and_saves_nothing(client) -> None:
    response = client.post("/checkin/form", data=form(energy="12"))

    assert response.status_code == 200
    assert "не больше 10" in response.text
    assert 'value="12"' in response.text  # введённое не теряется
    assert client.app.state.journal.get(date(2026, 10, 1)) is None


def test_empty_fields_are_skipped_not_errors(client) -> None:
    response = client.post("/checkin/form", data=form(steps="", mood=""))

    assert "Сохранено" in response.text
    entry = client.app.state.journal.get(date(2026, 10, 1))
    assert entry.steps is None
    assert entry.mood is None


def test_form_is_prefilled_with_saved_entry(client) -> None:
    client.post("/checkin/form", data=form())

    response = client.get("/checkin/form", params={"day": "2026-10-01"})

    assert 'value="8500"' in response.text
    assert 'value="23:40"' in response.text
