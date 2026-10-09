from datetime import date, time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from biohucker.config import load_settings
from biohucker.journal.models import FIELD_LABELS, CheckinEntry, describe_errors
from biohucker.journal.repo import JournalRepo, create_db_engine

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.globals["labels"] = FIELD_LABELS

FORM_FIELDS = (
    "day",
    "bedtime",
    "wake_time",
    "energy",
    "mood",
    "morning_walk_min",
    "steps",
    "workout_min",
    "workout_type",
)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="biohucker")
    app.state.journal = JournalRepo(create_db_engine(database_url or settings.database_url))

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "home.html")

    @app.get("/checkin/form", response_class=HTMLResponse)
    def checkin_form(request: Request, day: date | None = None) -> HTMLResponse:
        day = day or date.today()
        entry = app.state.journal.get(day)
        values = _form_values(entry) if entry else {"day": day.isoformat()}
        return _render_form(request, values)

    @app.post("/checkin/form", response_class=HTMLResponse)
    async def save_checkin_form(request: Request) -> HTMLResponse:
        submitted = await request.form()
        values = {name: str(submitted.get(name, "")).strip() for name in FORM_FIELDS}
        try:
            entry = CheckinEntry.model_validate({k: v for k, v in values.items() if v})
        except ValidationError as error:
            return _render_form(request, values, errors=describe_errors(error))
        saved = app.state.journal.upsert(entry)
        return _render_form(request, _form_values(saved), saved=True)

    return app


def _render_form(
    request: Request, values: dict[str, str], errors: dict[str, str] | None = None, saved=False
) -> HTMLResponse:
    context = {"values": values, "errors": errors or {}, "saved": saved, "today": date.today()}
    return TEMPLATES.TemplateResponse(request, "checkin_form.html", context)


def _form_values(entry: CheckinEntry) -> dict[str, str]:
    values = {}
    for name in FORM_FIELDS:
        value = getattr(entry, name)
        if value is None:
            values[name] = ""
        elif isinstance(value, time):
            values[name] = value.strftime("%H:%M")
        else:
            values[name] = str(value)
    return values
