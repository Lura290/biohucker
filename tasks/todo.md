# Todo: biohucker

План и решения: [plan.md](plan.md). Каждая задача закрывается, только если выполнены её
критерии **и** Definition of Done (`.claude/references/definition-of-done.md`): сначала
тест (red), потом код (green), `uv run pytest` и `uv run ruff check . && uv run ruff format
--check .` зелёные, отдельный коммит.

Обозначения размера: S = 1–2 файла кода, M = 3–5.

---

## Фаза 0: Каркас и LLM-ядро

### - [x] T1: Каркас проекта — приложение стартует

**Description:** `pyproject.toml` (uv, Python 3.12, зависимости из plan.md, ruff line-length 100,
pytest с маркером `eval` и `addopts = -m "not eval"`), `.gitignore` (`.env`, `data/`, `.venv/`),
`.env.example`, пакет `biohucker/` с подпакетами из SPEC, FastAPI-приложение с базовым
шаблоном и главной страницей-заглушкой.

**Acceptance criteria:**
- [ ] `uv sync` ставит зависимости; `uv run uvicorn biohucker.web.app:create_app --factory` отдаёт `/` с кодом 200
- [ ] `uv run pytest` зелёный (1 тест на `/`), `pytest -m eval` по умолчанию не собирается
- [ ] Конфиг (`biohucker/config.py`) читает `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `DATABASE_URL` с дефолтами из SPEC

**Verification:** `uv run pytest` · `uv run ruff check .` · ручной `curl 127.0.0.1:8000/`

**Dependencies:** нет

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `biohucker/config.py`,
`biohucker/web/app.py`, `biohucker/web/templates/base.html`, `tests/web/test_app.py`

**Scope:** M (много мелких конфигов)

### - [x] T2: LLM-ядро — цикл tool use + FakeLLM

**Description:** Типы `Tool`, `Message`, `RunResult`, протокол `LLMClient`, общий цикл tool
use (валидация аргументов pydantic, ошибка валидации возвращается модели, лимит 4 запроса)
и `FakeLLM` со сценарием ответов. Сеть не нужна.

**Acceptance criteria:**
- [ ] Валидный tool call → вызван `handler` с pydantic-объектом, результат ушёл в историю
- [ ] Невалидные аргументы → `handler` не вызван, модель получает текст ошибки; цикл стоп на 4 запросах → `degraded=True`
- [ ] Сценарий FakeLLM описывается в ≤ 3 строки теста

**Verification:** `uv run pytest tests/llm`

**Dependencies:** T1

**Files:** `biohucker/llm/types.py`, `biohucker/llm/loop.py`, `biohucker/llm/fake.py`, `tests/llm/test_loop.py`

**Scope:** M

### - [x] T3: OpenRouter-клиент + smoke-скрипт

**Description:** `OpenRouterClient` на пакете `openai` (`base_url` OpenRouter) поверх цикла из
T2: таймаут 20 с, один повтор на 429/5xx/таймаут, без ключа сразу `degraded`. Логи без
содержимого дневника. Скрипт `scripts/smoke_llm.py`: один реальный запрос с инструментом
`propose_checkin`-подобной схемой и печать «tool use работает / нет».

**Acceptance criteria:**
- [ ] Через `httpx.MockTransport`: успешный tool call; 429 → повтор → `degraded`; таймаут → `degraded`; без исключений наружу
- [ ] Без `OPENROUTER_API_KEY` клиент возвращает `degraded=True`, не делая запросов
- [ ] `uv run python scripts/smoke_llm.py` понятно сообщает результат (запускает пользователь)

**Verification:** `uv run pytest tests/llm` · smoke-скрипт у пользователя (Checkpoint 1)

**Dependencies:** T2

**Files:** `biohucker/llm/openrouter.py`, `scripts/smoke_llm.py`, `tests/llm/test_openrouter.py`

**Scope:** S

### Checkpoint 0
- [x] `uv run pytest` и ruff зелёные
- [x] Приложение стартует на пустом окружении без ключа

---

## Фаза 1: Дневник через форму

### - [x] T4: Модель дневной записи и валидация

**Description:** `CheckinEntry` по SPEC-journal (включая `experiment_done`) и вычисляемый
`sleep_hours` с переходом через полночь и правилом 2–16 ч; запрет будущей даты; сообщения
об ошибках на русском.

**Acceptance criteria:**
- [ ] Диапазоны полей и запрет будущей даты дают `ValidationError` с русским текстом
- [ ] `sleep_hours`: `23:40→07:10 = 7.5`, `01:00→09:00 = 8.0`, нет одного времени → `None`, `20:00→07:00`(11 ч) ок, `23:00→00:30` (1.5 ч) → ошибка
- [ ] Все случаи — табличный параметризованный тест

**Verification:** `uv run pytest tests/journal/test_models.py`

**Dependencies:** T1

**Files:** `biohucker/journal/models.py`, `tests/journal/test_models.py`

**Scope:** S

### - [x] T5: Репозиторий SQLite + форма чек-ина

**Description:** `JournalRepo` (`upsert` с частичным слиянием, `get`, `delete`, `range`,
`missing_fields`) на SQLModel, создание схемы при старте. Страница `/checkin/form`: форма
→ валидация → `upsert` → «Сохранено», ошибки у полей.

**Acceptance criteria:**
- [ ] `upsert` частичной записи не затирает сохранённые поля; `range` отсортирован и включителен
- [ ] POST валидной формы создаёт запись; невалидной → 200 с ошибкой у поля, в БД ничего
- [ ] Тесты используют временную БД (`tmp_path`), реальный `data/` не трогают

**Verification:** `uv run pytest tests/journal tests/web` · вручную: заполнить форму, перезапустить сервер, запись на месте

**Dependencies:** T4

**Files:** `biohucker/journal/repo.py`, `biohucker/web/app.py`, `biohucker/web/templates/checkin_form.html`,
`tests/journal/test_repo.py`, `tests/web/test_checkin_form.py`

**Scope:** M

### Checkpoint 1 — первая польза
- [x] Тесты и ruff зелёные (61 тест)
- [x] Дневник можно вести формой; данные переживают перезапуск (проверено вручную)
- [ ] **Пользователь:** `cp .env.example .env`, вписать ключ, `uv run python scripts/smoke_llm.py`
      → результат определяет стратегию T6 (tool use или JSON-в-тексте)

---

## Фаза 2: Чек-ин в чате

### - [x] T6: Агент чек-ина — промпт, инструменты, недостающие поля

**Description:** `CheckinAgent`: системный промпт (суть из SPEC-checkin), инструменты
`propose_checkin` (частичный `CheckinEntry` без `day` → черновик + список недостающих) и
контекст дня в системном промпте; приветственное сообщение со всеми вопросами; черновик в памяти.
Модели не даётся инструмент записи в БД.

**Acceptance criteria:**
- [ ] FakeLLM вызывает `propose_checkin` со всеми полями → состояние «готово к подтверждению» после 1 ответа модели
- [ ] Частичные поля → ответ агента перечисляет **только** недостающие
- [ ] Невалидное значение (energy=15) не попадает в черновик; модели возвращена ошибка

**Verification:** `uv run pytest tests/checkin`

**Dependencies:** T3, T5 (и итог smoke-проверки)

**Files:** `biohucker/checkin/agent.py`, `biohucker/checkin/prompt.py`, `tests/checkin/test_agent.py`

**Scope:** M

### - [x] T7: Страница чата — диалог → итог → сохранение

**Description:** `/` с HTMX-чатом: если записи за сегодня нет, агент пишет первым; `POST /chat`;
карточка итога с «Сохранить»/«Исправить»; `POST /checkin/confirm` → `upsert`. Если запись
уже есть — показ записи и предложение изменить. При `degraded` — заметная ссылка на форму.

**Acceptance criteria:**
- [ ] Без нажатия «Сохранить» в БД пусто; после — запись есть (TestClient + FakeLLM)
- [ ] `degraded` → в ответе ссылка на `/checkin/form`
- [ ] Повторный заход в тот же день не запускает опрос заново

**Verification:** `uv run pytest tests/web` · вручную с ключом: один чек-ин фразой

**Dependencies:** T6

**Files:** `biohucker/web/app.py` (или `routes_checkin.py`), `biohucker/web/templates/chat.html`,
`biohucker/web/templates/_messages.html`, `tests/web/test_chat.py`

**Scope:** M

### - [ ] T8: Эвалы чек-ина (пишутся, не запускаются)

**Description:** `evals/test_checkin_eval.py` с маркером `eval`: 5 фраз разной формы → ожидаемый
черновик; неполная фраза → переспрос только недостающего; «какой магний пить?» → отказ без
препаратов и дозировок (проверка кодом по стоп-словам + список ожидаемых полей, без
LLM-judge там, где хватает детерминированной проверки).

**Acceptance criteria:**
- [ ] `uv run pytest -m eval --collect-only` собирает ≥ 7 сценариев
- [ ] Обычный `uv run pytest` их не запускает
- [ ] Без ключа эвалы скипаются с понятной причиной, а не падают

**Verification:** `uv run pytest -m eval --collect-only` · **пользователь** запускает `-m eval` по желанию

**Dependencies:** T6

**Files:** `evals/test_checkin_eval.py`, `evals/conftest.py`

**Scope:** S

### Checkpoint 2 — основной ежедневный сценарий
- [ ] Тесты и ruff зелёные
- [ ] **Пользователь:** чек-ин одной фразой с живой моделью; сообщить, что получилось
- [ ] Ревью с пользователем перед фазой 3

---

## Фаза 3: История и связи

### - [ ] T9: История — таблица, правка, удаление

**Description:** `/history`: таблица записей (новые сверху), правка строки (полная замена —
`JournalRepo.replace`, позволяет очистить поле) и удаление с подтверждением. Добавить
`replace` в SPEC-journal.

**Acceptance criteria:**
- [ ] Правка с очищенным полем сохраняет `None` (в отличие от `upsert`)
- [ ] `DELETE /entries/{day}` удаляет запись; несуществующий день → 404
- [ ] Невалидная правка не меняет запись

**Verification:** `uv run pytest tests/journal tests/web`

**Dependencies:** T5

**Files:** `biohucker/journal/repo.py`, `biohucker/web/app.py`, `biohucker/web/templates/history.html`,
`tests/web/test_history.py`, `SPEC-journal.md`

**Scope:** M

### - [ ] T10: Поиск связей (insights)

**Description:** Чистый модуль по SPEC-insights: Спирмен с рангами при совпадениях,
пермутационный p (1000 перестановок, seed), Бонферрони, бинарные факторы с разницей средних,
лаг 1 день, ≤ 3 связей, шаблонные тексты с n и «связь, не причина».

**Acceptance criteria:**
- [ ] ρ совпадает с вручную посчитанным на маленьком наборе (с совпадающими рангами)
- [ ] Синтетика с заложенной связью → связь найдена; 200 случайных прогонов (n = 7–14) → находки в ≤ 5%
- [ ] n < 7 → пусто; константный ряд → не падает и связей нет

**Verification:** `uv run pytest tests/insights`

**Dependencies:** T4

**Files:** `biohucker/insights/stats.py`, `biohucker/insights/find.py`, `tests/insights/test_stats.py`,
`tests/insights/test_find.py`

**Scope:** M

### - [ ] T11: Графики и блок «Связи» на /history

**Description:** Chart.js (CDN, фиксированная версия): энергия, настроение, часы сна по дням.
Блок «Связи»: результаты `find_insights` по последним 28 дням или «нужно ещё N дней» /
«явных связей нет».

**Acceptance criteria:**
- [ ] При < 7 записях на странице текст «нужно ещё N дней записей» с верным N
- [ ] При данных с заложенной связью на странице её текст
- [ ] Данные для графика отдаются в странице как JSON, без ошибок на пустой БД

**Verification:** `uv run pytest tests/web/test_history.py` · вручную: страница на демо-данных

**Dependencies:** T9, T10

**Files:** `biohucker/web/app.py`, `biohucker/web/templates/history.html`, `tests/web/test_history.py`

**Scope:** S

### Checkpoint 3
- [ ] Тесты и ruff зелёные
- [ ] История, правка и графики работают вручную

---

## Фаза 4: Эксперименты

### - [ ] T12: Библиотека советов (library.yaml)

**Description:** ~15 советов по схеме SPEC-experiments (сон, свет, движение, кофеин,
NSDR/дыхание, холод, зона 2). У каждого конкретный источник: эпизод, статья или книга. Без
добавок и дозировок. Загрузчик с pydantic-схемой.

**Acceptance criteria:**
- [ ] Каждый элемент проходит схему, `id` уникальны, `source` не пустой, `target_metric` ∈ {energy, mood, sleep_hours}
- [ ] Тест-стоп-лист: в протоколах нет «мг», «таблет», названий добавок и препаратов
- [ ] 12–18 элементов

**Verification:** `uv run pytest tests/experiments/test_library.py`

**Dependencies:** T1

**Files:** `biohucker/experiments/library.yaml`, `biohucker/experiments/library.py`, `tests/experiments/test_library.py`

**Scope:** S

### - [ ] T13: Отчёт «до / во время» с вердиктом

**Description:** Чистая `build_report(baseline, trial, target_metric) -> Report` по правилам
SPEC-experiments: средние/SD/n/Δ по всем метрикам, adherence, вердикт и направление,
шаблонный текст.

**Acceptance criteria:**
- [ ] Таблица граничных случаев: adherence 4 → `insufficient_data`, 5 → оценивается; n 4/5; |Δ| = SD → `noise`; SD = 0 и |Δ| ≥ 1 → `effect`
- [ ] Направление «лучше/хуже» верно для всех метрик (сон, энергия, настроение — больше = лучше)
- [ ] Текст не содержит «эффект», если вердикт не `effect`

**Verification:** `uv run pytest tests/experiments/test_report.py`

**Dependencies:** T4

**Files:** `biohucker/experiments/report.py`, `tests/experiments/test_report.py`

**Scope:** S

### - [ ] T14: Жизненный цикл эксперимента и ранжирование кандидатов

**Description:** Таблица `experiments` и `ExperimentRepo` со статусами
suggested → active → finished / rejected / abandoned (не больше одного suggested/active).
`rank_candidates`: исключить пройденные/отклонённые за 30 дней, поднять совпадающие с
инсайтами и «проседающей» метрикой. Условие старта: ≥ 7 записей за 10 дней.

**Acceptance criteria:**
- [ ] Недопустимые переходы статусов → ошибка; второй активный эксперимент создать нельзя
- [ ] Отклонённый 10 дней назад не в кандидатах; 31 день назад — снова в кандидатах
- [ ] < 7 базовых записей → «нужно ещё N дней»

**Verification:** `uv run pytest tests/experiments`

**Dependencies:** T5, T10, T12

**Files:** `biohucker/experiments/repo.py`, `biohucker/experiments/select.py`,
`tests/experiments/test_repo.py`, `tests/experiments/test_select.py`

**Scope:** M

### - [ ] T15: Выбор эксперимента через LLM + страница /experiments

**Description:** LLM получает топ-3 кандидата и инсайты, возвращает `library_id` из этих трёх
и 2–3 предложения объяснения; id не из списка или `degraded` → топ-1 с шаблонным текстом.
Страница `/experiments`: предложение с протоколом и источником, кнопки «Принять» / «Другой».

**Acceptance criteria:**
- [ ] FakeLLM вернул id не из топ-3 → использован топ-1 (тест)
- [ ] «Принять» → active со `start_day` = завтра; «Другой» → rejected и новое предложение
- [ ] Предложенный id всегда есть в библиотеке

**Verification:** `uv run pytest tests/experiments tests/web`

**Dependencies:** T14

**Files:** `biohucker/experiments/suggest.py`, `biohucker/web/app.py`,
`biohucker/web/templates/experiments.html`, `tests/experiments/test_suggest.py`, `tests/web/test_experiments.py`

**Scope:** M

### - [ ] T16: Эксперимент в чек-ине + авто-отчёт + архив

**Description:** При активном эксперименте он попадает в системный промпт, чек-ин задаёт
`done_question` и пишет `experiment_done`; на `/` карточка «день N из 7» (и в форме — чекбокс).
Первое открытие после `end_day` → `finished` + `build_report` сохраняется в `report_json`.
Архив отчётов на `/experiments`; «Бросить» → abandoned.

**Acceptance criteria:**
- [ ] При активном эксперименте черновик требует `experiment_done`, без активного — нет
- [ ] Открытие приложения на день после `end_day` создаёт отчёт ровно один раз
- [ ] Архив показывает вердикт и adherence

**Verification:** `uv run pytest` · вручную на демо-данных (T18)

**Dependencies:** T7, T13, T15

**Files:** `biohucker/checkin/agent.py`, `biohucker/experiments/lifecycle.py`, `biohucker/web/app.py`,
`biohucker/web/templates/experiments.html`, `tests/experiments/test_lifecycle.py`

**Scope:** M

### - [ ] T17: Эвал объяснения эксперимента

**Description:** Эвал с маркером `eval`: объяснение выбора не содержит чисел, препаратов и
утверждений, которых нет в `protocol`/`source`/инсайтах. LLM-judge только здесь, на 3
сценариях.

**Acceptance criteria:**
- [ ] `pytest -m eval --collect-only` собирает 3 новых сценария; обычный `pytest` их не запускает
- [ ] Без ключа — skip с причиной

**Verification:** `uv run pytest -m eval --collect-only`

**Dependencies:** T15

**Files:** `evals/test_experiment_eval.py`

**Scope:** S

### - [ ] T18: Демо-данные и README запуска

**Description:** `scripts/seed_demo.py --db data/demo.db`: 21 день правдоподобных записей с
заложенной связью «прогулка → энергия» и завершённым экспериментом, чтобы руками увидеть
весь цикл. README: установка, `.env`, запуск, тесты, эвалы.

**Acceptance criteria:**
- [ ] `DATABASE_URL=sqlite:///data/demo.db uv run uvicorn …` показывает графики, связь и отчёт
- [ ] Скрипт не трогает основную БД без явного `--db`
- [ ] Команды из README выполняются как написано

**Verification:** прогон команд из README · `uv run pytest`

**Dependencies:** T16

**Files:** `scripts/seed_demo.py`, `README.md`

**Scope:** S

### Checkpoint 4 — готово к /review
- [ ] Все Success Criteria из SPEC.md выполнены или явно перечислены как непроверенные (живая модель)
- [ ] Тесты и ruff зелёные, эвалы собираются
- [ ] Пользователь прошёл цикл на демо-данных
