"""Проверка живой модели: умеет ли она tool use.

Запуск: uv run python scripts/smoke_llm.py
Нужен OPENROUTER_API_KEY в .env. Делает 1–2 запроса к модели.
"""

import json
import sys

from pydantic import BaseModel, Field, ValidationError

from biohucker.config import load_settings
from biohucker.llm import LLMUnavailable, Tool
from biohucker.llm.openrouter import OpenRouterModel


class SmokeCheckin(BaseModel):
    bedtime: str | None = Field(default=None, description="Время отбоя, HH:MM")
    wake_time: str | None = Field(default=None, description="Время подъёма, HH:MM")
    energy: int | None = Field(default=None, ge=1, le=10)
    steps: int | None = Field(default=None, ge=0)


TOOL = Tool(
    name="propose_checkin",
    description="Сохранить черновик дневной записи из ответа пользователя.",
    args_model=SmokeCheckin,
    handler=lambda args: {"missing": []},
)
SYSTEM = "Ты помощник дневника. Извлеки данные из ответа пользователя и вызови propose_checkin."
USER = "Лёг в 23:40, встал в 7:10, энергия 6, прошёл 8500 шагов."


def main() -> int:
    settings = load_settings()
    print(f"Модель: {settings.openrouter_model}")
    model = OpenRouterModel(settings.openrouter_api_key, settings.openrouter_model)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]

    try:
        response = model.complete(messages, [TOOL.schema()])
    except LLMUnavailable as error:
        print(f"❌ Модель недоступна: {error}")
        return 2

    if not response.tool_calls:
        print("⚠️  Модель ответила текстом, а не вызовом инструмента:")
        print(f"   {response.content!r}")
        print("   → tool use не работает; в T6 используем JSON-в-тексте.")
        return 1

    call = response.tool_calls[0]
    print(f"Вызван инструмент: {call.name}")
    print(f"Аргументы: {call.arguments}")
    try:
        args = SmokeCheckin.model_validate_json(call.arguments)
    except ValidationError as error:
        print(f"⚠️  Аргументы не прошли валидацию: {error}")
        return 1

    expected = {"bedtime": "23:40", "wake_time": "07:10", "energy": 6, "steps": 8500}
    got = args.model_dump()
    wrong = {k: got[k] for k, v in expected.items() if str(got[k]).zfill(5) != str(v).zfill(5)}
    if wrong:
        print(
            f"⚠️  Tool use работает, но значения неточные: {json.dumps(wrong, ensure_ascii=False)}"
        )
        return 1
    print("✅ Tool use работает, все поля извлечены верно.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
