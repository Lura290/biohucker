# Spec: llm

Карта: [SPEC.md → Capability Map](SPEC.md#capability-map). Зависит от: —.

## Objective

Тонкая обёртка над OpenRouter: отправить сообщения с описанием инструментов,
выполнить цикл tool use, вернуть итог. Остальные модули не знают про HTTP и
OpenRouter. Плюс `FakeLLM`, чтобы тесты работали без сети.

## Интерфейс

```python
class Tool(BaseModel):
    name: str
    description: str
    args_model: type[BaseModel]                # JSON Schema для API берётся из pydantic
    handler: Callable[[BaseModel], dict]       # получает уже провалидированные аргументы

class LLMClient(Protocol):
    def run(self, system: str, messages: list[Message], tools: list[Tool]) -> RunResult: ...

@dataclass
class RunResult:
    reply: str                       # итоговый текст ассистента пользователю
    messages: list[Message]          # история с tool calls — для продолжения диалога
    tool_calls_made: list[str]       # имена вызванных инструментов
    degraded: bool                   # True → модель недоступна/сломалась, UI показывает форму
```

Реализации: `OpenRouterClient` (пакет `openai`, `base_url=https://openrouter.ai/api/v1`) и
`FakeLLM` (сценарий: список заранее заданных ответов и tool calls).

## Поведение

- Максимум **4 запроса к модели** за один `run`. После этого `degraded=True`.
- Невалидные аргументы tool call (pydantic `ValidationError`) возвращаются модели как
  результат инструмента с текстом ошибки. Так она может исправиться: это засчитывается
  как один из 4 запросов.
- Ответ текстом вместо ожидаемого tool call — это нормально (модель задаёт вопрос
  пользователю). Решение «чего не хватает» принимает вызывающий модуль, не `llm`.
- HTTP 429, 5xx, таймаут (20 с) → одна повторная попытка через 2 с, затем `degraded=True`.
- Ключ и модель берутся из окружения. Без ключа клиент сразу `degraded=True` и не падает.
- В лог пишутся имя модели, число запросов и токенов, ошибки. Содержимое дневника в лог
  не пишется.

## Acceptance Criteria

1. `FakeLLM` позволяет описать сценарий «модель вызвала `save_checkin` с аргументами X» в 3 строки теста.
2. Невалидные аргументы не доходят до `handler`.
3. Цикл гарантированно останавливается на 4 запросах.
4. Отсутствие ключа, 429 и таймаут дают `degraded=True`, без исключения наружу.

## Тесты

Unit: цикл tool use на `FakeLLM` (валидные/невалидные аргументы, лимит). Сетевой клиент —
через подменённый HTTP-транспорт (`httpx.MockTransport`), без реальных запросов.
