from datetime import date, time
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from biohucker.checkin.agent import CheckinAgent, CheckinSession
from biohucker.config import load_settings
from biohucker.journal.models import FIELD_LABELS, CheckinEntry, describe_errors
from biohucker.journal.repo import JournalRepo, create_db_engine
from biohucker.llm import ChatModel
from biohucker.llm.openrouter import OpenRouterModel

WEB_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=WEB_DIR / "templates")
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


def create_app(database_url: str | None = None, model: ChatModel | None = None) -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="biohucker")
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.state.journal = JournalRepo(create_db_engine(database_url or settings.database_url))
    app.state.agent = CheckinAgent(
        model or OpenRouterModel(settings.openrouter_api_key, settings.openrouter_model),
        app.state.journal,
    )
    # Один пользователь и локальный запуск: переписка дня живёт в памяти процесса.
    app.state.sessions = {}

    def today_session() -> CheckinSession:
        today = date.today()
        if today not in app.state.sessions:
            app.state.sessions[today] = app.state.agent.start(today)
        return app.state.sessions[today]

    def render_chat(request: Request, session: CheckinSession, status: int = 200) -> Response:
        if not request.headers.get("HX-Request"):
            if request.method == "POST":
                # Без JavaScript: после отправки — на главную, чтобы F5 не слал форму повторно.
                return RedirectResponse("/", status_code=303)
            return TEMPLATES.TemplateResponse(request, "chat.html", _chat_context(session))
        return TEMPLATES.TemplateResponse(
            request, "_chat.html", _chat_context(session), status_code=status
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        return render_chat(request, today_session())

    @app.post("/chat", response_class=HTMLResponse)
    def chat(request: Request, text: str = Form("")) -> Response:
        session = today_session()
        if text.strip():
            app.state.agent.reply(session, text.strip())
        return render_chat(request, session)

    @app.post("/checkin/confirm", response_class=HTMLResponse)
    def confirm(request: Request) -> Response:
        session = today_session()
        if not session.ready:
            return render_chat(request, session, status=409)
        app.state.agent.confirm(session)
        return render_chat(request, session)

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


def _chat_context(session: CheckinSession) -> dict:
    return {"session": session, "messages": _visible(session), "draft": _draft_rows(session)}


def _visible(session: CheckinSession) -> list[dict]:
    """Только реплики для человека: без системных и служебных сообщений с tool calls."""
    return [m for m in session.messages if m["role"] in ("user", "assistant") and m.get("content")]


def _draft_rows(session: CheckinSession) -> list[tuple[str, str]]:
    values = _form_values(session.draft)
    return [
        (FIELD_LABELS[name], values[name] or "—")
        for name in FORM_FIELDS
        if name != "day" and (values[name] or name != "workout_type")
    ]


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
