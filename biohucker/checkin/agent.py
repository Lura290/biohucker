import re
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field, ValidationError, field_validator

from biohucker.checkin import prompt
from biohucker.journal.models import FIELD_LABELS, CheckinEntry, describe_errors
from biohucker.journal.repo import JournalRepo
from biohucker.llm import ChatModel, Message, Tool, ToolError, run_tool_loop

PROPOSE = "propose_checkin"
_SHORT_TIME = re.compile(r"^(\d{1,2})[:.](\d{2})$")


class CheckinProposal(BaseModel):
    """Аргументы propose_checkin. Диапазоны проверяет CheckinEntry — источник правды один."""

    bedtime: str | None = Field(default=None, description="Время отбоя, ЧЧ:ММ")
    wake_time: str | None = Field(default=None, description="Время подъёма, ЧЧ:ММ")
    energy: int | None = Field(default=None, description="Энергия 1–10")
    mood: int | None = Field(default=None, description="Настроение 1–10")
    morning_walk_min: int | None = Field(
        default=None, description="Утренняя прогулка, минут; 0 — не было"
    )
    steps: int | None = Field(default=None, description="Шагов за день")
    workout_min: int | None = Field(default=None, description="Тренировка, минут; 0 — не было")
    workout_type: str | None = Field(default=None, description="Тип тренировки: сила, бег…")
    finish: bool = Field(
        default=False, description="true — пользователь просит пропустить остальное"
    )

    @field_validator("bedtime", "wake_time", mode="before")
    @classmethod
    def _pad_time(cls, value: object) -> object:
        if isinstance(value, str) and (match := _SHORT_TIME.match(value.strip())):
            return f"{int(match[1]):02d}:{match[2]}"
        return value


@dataclass
class CheckinSession:
    day: date
    draft: CheckinEntry
    messages: list[Message] = field(default_factory=list)
    ready: bool = False
    saved: bool = False
    already_saved: bool = False
    finish_requested: bool = False
    degraded: bool = False


@dataclass(frozen=True)
class CheckinTurn:
    reply: str
    ready: bool
    missing: list[str]
    degraded: bool = False


class CheckinAgent:
    """Ежедневный опрос: модель извлекает значения, код решает, что переспросить и когда готово."""

    def __init__(self, model: ChatModel, journal: JournalRepo) -> None:
        self._model = model
        self._journal = journal

    def start(self, day: date) -> CheckinSession:
        existing = self._journal.get(day)
        if existing:
            session = CheckinSession(day=day, draft=existing, already_saved=True)
            text = prompt.ALREADY_SAVED.format(day=day.isoformat(), summary=summarize(existing))
        else:
            session = CheckinSession(day=day, draft=CheckinEntry(day=day))
            text = prompt.GREETING.format(day=day.isoformat())
        session.messages.append({"role": "assistant", "content": text})
        return session

    def reply(self, session: CheckinSession, text: str) -> CheckinTurn:
        session.messages.append({"role": "user", "content": text})
        result = run_tool_loop(
            self._model,
            prompt.system_prompt(session.day),
            session.messages,
            [self._propose_tool(session)],
            stop_on={PROPOSE},
        )
        session.messages = result.messages
        session.degraded = result.degraded
        missing = session.draft.missing_fields()

        if result.degraded:
            turn = CheckinTurn(prompt.DEGRADED, ready=False, missing=missing, degraded=True)
        elif PROPOSE in result.tool_calls_made:
            session.ready = session.finish_requested or not missing
            turn = CheckinTurn(_after_proposal(session.ready, missing), session.ready, missing)
        else:
            turn = CheckinTurn(result.reply, ready=session.ready, missing=missing)

        session.messages.append({"role": "assistant", "content": turn.reply})
        return turn

    def confirm(self, session: CheckinSession) -> CheckinEntry:
        """Сохраняет черновик. Пишет в БД только этот метод — по кнопке, не по решению модели."""
        if not session.ready:
            raise ValueError("Черновик ещё не готов к сохранению")
        saved = self._journal.upsert(session.draft)
        session.draft, session.saved = saved, True
        return saved

    def _propose_tool(self, session: CheckinSession) -> Tool:
        def handler(proposal: CheckinProposal) -> dict:
            values = proposal.model_dump(exclude_none=True, exclude={"finish"})
            try:
                merged = CheckinEntry.model_validate(
                    {**session.draft.model_dump(exclude_none=True), **values}
                )
            except ValidationError as error:
                problems = "; ".join(
                    f"{FIELD_LABELS.get(name, name)}: {message}"
                    for name, message in describe_errors(error).items()
                )
                raise ToolError(problems) from error
            session.draft = merged
            session.finish_requested = proposal.finish
            return {"missing": merged.missing_fields()}

        return Tool(
            name=PROPOSE,
            description="Сохранить в черновик значения, которые пользователь назвал.",
            args_model=CheckinProposal,
            handler=handler,
        )


def summarize(entry: CheckinEntry) -> str:
    parts = []
    for name in entry.filled_fields() + (["workout_type"] if entry.workout_type else []):
        value = getattr(entry, name)
        shown = value.strftime("%H:%M") if hasattr(value, "strftime") else value
        parts.append(f"{FIELD_LABELS[name].lower()} {shown}")
    return ", ".join(parts) or "пока пусто"


def _after_proposal(ready: bool, missing: list[str]) -> str:
    if not ready:
        return prompt.follow_up(missing)
    if missing:
        return prompt.READY_WITH_GAPS.format(
            gaps=", ".join(FIELD_LABELS[name].lower() for name in missing)
        )
    return prompt.READY
