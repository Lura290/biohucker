from datetime import date, time

import pytest
from pydantic import ValidationError

from biohucker.journal.models import CHECKIN_FIELDS, CheckinEntry
from biohucker.journal.repo import JournalRepo, create_db_engine

DAY = date(2026, 10, 1)


def test_upsert_creates_and_get_returns_entry(repo) -> None:
    repo.upsert(CheckinEntry(day=DAY, energy=6, bedtime=time(23, 40), wake_time=time(7, 10)))

    entry = repo.get(DAY)

    assert entry is not None
    assert entry.energy == 6
    assert entry.sleep_hours == 7.5


def test_partial_upsert_keeps_saved_fields(repo) -> None:
    repo.upsert(CheckinEntry(day=DAY, energy=6, steps=8000))

    merged = repo.upsert(CheckinEntry(day=DAY, mood=7))

    assert (merged.energy, merged.steps, merged.mood) == (6, 8000, 7)
    assert repo.get(DAY) == merged


def test_merge_is_revalidated(repo) -> None:
    repo.upsert(CheckinEntry(day=DAY, bedtime=time(23, 0)))

    with pytest.raises(ValidationError):
        repo.upsert(CheckinEntry(day=DAY, wake_time=time(0, 30)))
    assert repo.get(DAY).wake_time is None


def test_get_missing_day_returns_none(repo) -> None:
    assert repo.get(DAY) is None


def test_delete(repo) -> None:
    repo.upsert(CheckinEntry(day=DAY, energy=5))

    assert repo.delete(DAY) is True
    assert repo.get(DAY) is None
    assert repo.delete(DAY) is False


def test_range_is_inclusive_and_sorted(repo) -> None:
    for day in (date(2026, 10, 3), date(2026, 10, 1), date(2026, 10, 5), date(2026, 9, 30)):
        repo.upsert(CheckinEntry(day=day, energy=5))

    days = [e.day for e in repo.range(date(2026, 10, 1), date(2026, 10, 5))]

    assert days == [date(2026, 10, 1), date(2026, 10, 3), date(2026, 10, 5)]


def test_missing_fields(repo) -> None:
    assert repo.missing_fields(DAY) == list(CHECKIN_FIELDS)

    repo.upsert(CheckinEntry(day=DAY, energy=6, workout_min=0))

    missing = repo.missing_fields(DAY)
    assert "energy" not in missing
    assert "workout_min" not in missing
    assert "steps" in missing


def test_data_survives_new_engine(db_url) -> None:
    JournalRepo(create_db_engine(db_url)).upsert(CheckinEntry(day=DAY, steps=9000))

    assert JournalRepo(create_db_engine(db_url)).get(DAY).steps == 9000


def test_sqlite_parent_directory_is_created(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'nested' / 'dir' / 'db.sqlite'}"

    JournalRepo(create_db_engine(url)).upsert(CheckinEntry(day=DAY, energy=4))

    assert (tmp_path / "nested" / "dir" / "db.sqlite").exists()
