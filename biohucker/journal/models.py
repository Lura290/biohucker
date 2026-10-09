from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

MIN_SLEEP_HOURS = 2
MAX_SLEEP_HOURS = 16

# Поля ежедневного опроса в порядке вопросов. experiment_done спрашивается отдельно,
# только при активном эксперименте.
CHECKIN_FIELDS = (
    "bedtime",
    "wake_time",
    "energy",
    "mood",
    "morning_walk_min",
    "steps",
    "workout_min",
)

FIELD_LABELS = {
    "day": "Дата",
    "bedtime": "Время отбоя",
    "wake_time": "Время подъёма",
    "energy": "Энергия",
    "mood": "Настроение",
    "morning_walk_min": "Утренняя прогулка, мин",
    "steps": "Шаги",
    "workout_min": "Тренировка, мин",
    "workout_type": "Тип тренировки",
    "experiment_done": "Эксперимент выполнен",
}


class CheckinEntry(BaseModel):
    """Одна дневная запись. Все поля, кроме дня, опциональны: лучше частичная запись, чем никакой.

    None — «не ответил», 0 — «не было» (прогулки, тренировки).
    """

    day: date
    bedtime: time | None = None
    wake_time: time | None = None
    energy: int | None = Field(default=None, ge=1, le=10)
    mood: int | None = Field(default=None, ge=1, le=10)
    morning_walk_min: int | None = Field(default=None, ge=0, le=300)
    steps: int | None = Field(default=None, ge=0, le=100_000)
    workout_min: int | None = Field(default=None, ge=0, le=300)
    workout_type: str | None = Field(default=None, max_length=100)
    experiment_done: bool | None = None

    @field_validator("day")
    @classmethod
    def _not_in_future(cls, day: date) -> date:
        if day > date.today():
            raise ValueError("дата не может быть в будущем")
        return day

    @field_validator("wake_time")
    @classmethod
    def _plausible_sleep(cls, wake_time: time | None, info: ValidationInfo) -> time | None:
        hours = sleep_hours(info.data.get("bedtime"), wake_time)
        if hours is not None and not MIN_SLEEP_HOURS <= hours <= MAX_SLEEP_HOURS:
            raise ValueError(
                f"сон получается {hours:g} ч — проверь время отбоя и подъёма "
                f"(ожидается от {MIN_SLEEP_HOURS} до {MAX_SLEEP_HOURS} ч)"
            )
        return wake_time

    @property
    def sleep_hours(self) -> float | None:
        return sleep_hours(self.bedtime, self.wake_time)

    def filled_fields(self) -> list[str]:
        return [name for name in CHECKIN_FIELDS if getattr(self, name) is not None]

    def missing_fields(self) -> list[str]:
        return [name for name in CHECKIN_FIELDS if getattr(self, name) is None]


def sleep_hours(bedtime: time | None, wake_time: time | None) -> float | None:
    """Часы сна с учётом перехода через полночь: 23:40 → 07:10 = 7.5."""
    if bedtime is None or wake_time is None:
        return None
    anchor = date(2000, 1, 1)
    delta = datetime.combine(anchor, wake_time) - datetime.combine(anchor, bedtime)
    if delta <= timedelta(0):
        delta += timedelta(days=1)
    return round(delta.total_seconds() / 3600, 2)


def describe_errors(error: ValidationError) -> dict[str, str]:
    """Ошибки валидации по полям, по-русски — для формы и для ответа модели."""
    return {
        ".".join(str(part) for part in item["loc"]) or "запись": _russian(item)
        for item in error.errors()
    }


def _russian(item: dict) -> str:
    ctx = item.get("ctx", {})
    match item["type"]:
        case "greater_than_equal":
            return f"должно быть не меньше {ctx['ge']}"
        case "less_than_equal":
            return f"должно быть не больше {ctx['le']}"
        case "string_too_long":
            return f"не больше {ctx['max_length']} символов"
        case "int_parsing" | "int_type" | "int_from_float":
            return "нужно целое число"
        case "time_parsing" | "time_type":
            return "нужно время в формате ЧЧ:ММ"
        case "date_parsing" | "date_from_datetime_parsing" | "date_type":
            return "нужна дата в формате ГГГГ-ММ-ДД"
        case "bool_parsing" | "bool_type":
            return "нужно «да» или «нет»"
        case "value_error":
            return str(ctx.get("error", item["msg"]))
        case _:
            return item["msg"]
