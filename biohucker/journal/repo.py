from datetime import date, time
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select

from biohucker.journal.models import CHECKIN_FIELDS, CheckinEntry


class CheckinRow(SQLModel, table=True):
    __tablename__ = "checkin_entries"

    day: date = Field(primary_key=True)
    bedtime: time | None = None
    wake_time: time | None = None
    energy: int | None = None
    mood: int | None = None
    morning_walk_min: int | None = None
    steps: int | None = None
    workout_min: int | None = None
    workout_type: str | None = None
    experiment_done: bool | None = None


def create_db_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return engine


class JournalRepo:
    """Единственное место, которое пишет дневные записи в БД."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert(self, entry: CheckinEntry) -> CheckinEntry:
        """Частичное обновление: поля со значением None не затирают сохранённые."""
        with Session(self._engine) as session:
            row = session.get(CheckinRow, entry.day)
            saved = _to_entry(row).model_dump() if row else {}
            update = entry.model_dump(exclude_none=True)
            merged = CheckinEntry.model_validate({**saved, **update})
            session.merge(CheckinRow(**merged.model_dump()))
            session.commit()
        return merged

    def get(self, day: date) -> CheckinEntry | None:
        with Session(self._engine) as session:
            row = session.get(CheckinRow, day)
            return _to_entry(row) if row else None

    def delete(self, day: date) -> bool:
        with Session(self._engine) as session:
            row = session.get(CheckinRow, day)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def range(self, start: date, end: date) -> list[CheckinEntry]:
        """Записи с start по end включительно, по возрастанию дат."""
        query = (
            select(CheckinRow)
            .where(CheckinRow.day >= start, CheckinRow.day <= end)
            .order_by(CheckinRow.day)
        )
        with Session(self._engine) as session:
            return [_to_entry(row) for row in session.exec(query)]

    def missing_fields(self, day: date) -> list[str]:
        entry = self.get(day)
        return entry.missing_fields() if entry else list(CHECKIN_FIELDS)


def _to_entry(row: CheckinRow) -> CheckinEntry:
    # model_construct: данные из БД уже прошли валидацию при записи, а повторная проверка
    # «не в будущем» сломала бы чтение, если часы на компьютере уйдут назад.
    return CheckinEntry.model_construct(**row.model_dump())
