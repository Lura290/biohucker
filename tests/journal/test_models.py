from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError

from biohucker.journal.models import CheckinEntry, describe_errors

DAY = date(2026, 10, 1)


@pytest.mark.parametrize(
    ("bedtime", "wake_time", "hours"),
    [
        (time(23, 40), time(7, 10), 7.5),
        (time(1, 0), time(9, 0), 8.0),
        (time(20, 0), time(7, 0), 11.0),
        (time(22, 0), time(12, 0), 14.0),
        (None, time(7, 0), None),
        (time(23, 0), None, None),
    ],
)
def test_sleep_hours_handles_midnight(bedtime, wake_time, hours) -> None:
    entry = CheckinEntry(day=DAY, bedtime=bedtime, wake_time=wake_time)

    assert entry.sleep_hours == hours


@pytest.mark.parametrize(
    ("bedtime", "wake_time"),
    [
        (time(23, 0), time(0, 30)),  # 1.5 ч
        (time(7, 0), time(7, 30)),  # перепутаны AM/PM
        (time(22, 0), time(22, 0)),  # 0 ч
        (time(18, 0), time(10, 30)),  # 16.5 ч
    ],
)
def test_implausible_sleep_is_rejected(bedtime, wake_time) -> None:
    with pytest.raises(ValidationError) as error:
        CheckinEntry(day=DAY, bedtime=bedtime, wake_time=wake_time)

    assert "сон" in describe_errors(error.value)["wake_time"].lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("energy", 0),
        ("energy", 11),
        ("mood", 15),
        ("morning_walk_min", -1),
        ("morning_walk_min", 301),
        ("steps", -5),
        ("steps", 100_001),
        ("workout_min", -1),
        ("workout_min", 301),
        ("workout_type", "x" * 101),
    ],
)
def test_out_of_range_values_are_rejected_in_russian(field, value) -> None:
    with pytest.raises(ValidationError) as error:
        CheckinEntry(day=DAY, **{field: value})

    message = describe_errors(error.value)[field]
    assert any(word in message for word in ("от", "до", "не больше", "не меньше"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("energy", 1), ("energy", 10), ("morning_walk_min", 0), ("steps", 100_000)],
)
def test_boundary_values_are_accepted(field, value) -> None:
    assert getattr(CheckinEntry(day=DAY, **{field: value}), field) == value


def test_future_day_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        CheckinEntry(day=date.today() + timedelta(days=1))

    assert "будущ" in describe_errors(error.value)["day"]


def test_today_is_allowed() -> None:
    assert CheckinEntry(day=date.today()).day == date.today()


def test_only_day_is_required() -> None:
    entry = CheckinEntry(day=DAY)

    assert entry.filled_fields() == []


def test_zero_means_answered_no_and_none_means_not_answered() -> None:
    entry = CheckinEntry(day=DAY, morning_walk_min=0, workout_min=0)

    assert entry.filled_fields() == ["morning_walk_min", "workout_min"]
    assert "steps" in entry.missing_fields()
    assert "workout_min" not in entry.missing_fields()
