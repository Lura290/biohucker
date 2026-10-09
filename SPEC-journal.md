# Spec: journal

Карта: [SPEC.md → Capability Map](SPEC.md#capability-map). Зависит от: —.

## Objective

Хранить по одной дневной записи на дату, валидировать значения и отдавать записи
другим модулям. Это единственный модуль, который пишет в таблицу записей.

## Модель данных

`CheckinEntry` (pydantic, пример в SPEC.md → Code Style), поля:

| Поле | Тип | Правило |
|---|---|---|
| `day` | `date` | ключ; не в будущем |
| `bedtime` | `time \| None` | время отбоя накануне вечером (может быть после полуночи) |
| `wake_time` | `time \| None` | время подъёма в `day` |
| `energy`, `mood` | `int \| None` | 1–10 |
| `morning_walk_min` | `int \| None` | 0–300; `0` = не было прогулки |
| `steps` | `int \| None` | 0–100 000 |
| `workout_min` | `int \| None` | 0–300; `0` = тренировки не было |
| `workout_type` | `str \| None` | ≤ 100 символов, например «сила» |
| `experiment_done` | `bool \| None` | отмечается, только если активен эксперимент |

Вычисляемое (не хранится): `sleep_hours` — из `bedtime` и `wake_time` с учётом
перехода через полночь (`23:40 → 07:10` = 7.5 ч). Если результат вне 2–16 ч,
запись не валидна (скорее всего перепутаны AM/PM).

**Соглашение:** `None` значит «не ответил», `0` значит «не было». Без этого агент не отличит
«тренировки не было» от «ещё не спросили» и не поймёт, что переспрашивать.

## Интерфейс

```python
class JournalRepo:
    def upsert(self, entry: CheckinEntry) -> CheckinEntry: ...      # частичное обновление: None не затирает сохранённое
    def get(self, day: date) -> CheckinEntry | None: ...
    def delete(self, day: date) -> bool: ...
    def range(self, start: date, end: date) -> list[CheckinEntry]: ...  # включительно, по возрастанию дат
    def missing_fields(self, day: date) -> list[str]: ...           # для переспроса в checkin
```

- Схема создаётся при старте (`SQLModel.metadata.create_all`), без миграций в v1.
- Одна таблица `checkin_entries`, первичный ключ `day`.

## Acceptance Criteria

1. Значения вне диапазонов отклоняются с `ValidationError` и понятным сообщением на русском.
2. `upsert` с частичными данными дополняет запись, а не перезаписывает её `None`.
3. `sleep_hours` корректен через полночь и `None`, если нет одного из времён.
4. `range` возвращает только существующие дни, отсортированные по дате.
5. Запись на будущую дату отклоняется.

## Тесты

Unit: валидация и `sleep_hours` (через полночь, граница 2/16 ч). Integration: репозиторий на
временной SQLite (`tmp_path`).
