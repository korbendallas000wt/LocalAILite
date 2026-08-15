# LocalAILite — Контекст для передачи (Handoff)

> Точка входа для нового чата. Всё о проекте, текущем состоянии, планах и принципах работы.
> Обновлено: 2026-08-06

## 1. Проект

**LocalAILite** — локальный AI-ассистент для Manjaro Linux: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор. PyQt6, Python 3.14.

**Философия**: локальные нейросети доступны даже на слабом железе. Принцип «не навязываем, но помогаем максимально» — детектор честно говорит, что потянет машина, и предлагает лучший путь.

**GitHub**: korbendallas000wt/LocalAILite, ветка main.

## 2. Железо Корбена (тестовый стенд)

- CPU: Intel Xeon E5450 (4 ядра) — **без AVX2, без SSE4.2, без POPCNT**
- RAM: 15.6 GB
- ОС: Manjaro Linux, Python 3.14.6 системный, pyenv 3.12.8
- GPU: AMD (без CUDA, для SDXL не используется)

Это **самое сложное тестовое железо**. Если работает здесь — работает везде. На этом CPU pip-PyQt6 падает (нет sse4_2/popcnt), системный PyQt6 из pacman работает.

## 3. Текущее состояние (v1.3.0-dev)

Уровень 1 инсталлятора (бутстрап) **закрыт и закоммичен** (0594cff, f266f08).
Приложение: `venv/bin/python main.py`. Бутстрап: `python3 installer/cli.py`.

## 4. Что сделано (большой блок работы)

### 4.1. Инсталлятор, уровень 1
- installer/detector.py — диагностика ОС/CPU/RAM/GPU/Python/диск; флаги sse4_2, popcnt, avx, avx2, fma; методы can_use_pip_pyqt6(), detect_system_pyqt6()
- installer/requirements.py — пороги ресурсов
- installer/advisor.py — вердикты (Python/Ollama/SDXL), подбор моделей
- installer/steps/base.py — контракт идемпотентного шага (InstallStep, StepStatus)
- installer/steps/step_config.py — создание data/ (5 папок)
- installer/steps/step_env.py — venv + гибридная стратегия PyQt6
- installer/cli.py — точка входа бутстрапа

### 4.2. Гибридная стратегия PyQt6 (ключевое решение)
- Современный CPU (sse4_2+popcnt) → PyQt6 из pip
- Старый CPU → системный PyQt6 из pacman, venv с --system-site-packages
- Финальная проверка: глубокий импорт QtWidgets (не поверхностный import PyQt6)

### 4.3. Ревизия data/
Удалены призраки: cache/, checkpoints/, ollama/. Осталось 5 служебных папок. Ollama хранит данные в ~/.ollama (OLLAMA_DATA_DIR игнорировался).

### 4.4. Настраиваемые пути Ollama
utils/config.py: ключи ollama/binary_path, ollama/lib_path. Убран get_ollama_data_dir().

### 4.5. Документация
Обновлены CHANGELOG.md (раздел 1.3.0), STRUCTURE.md, PROJECT_MANIFEST.md (+ раздел «Концепция усечённого приложения»), Repo/README.md.

## 5. Концепция усечённого приложения (уровень 2)

Все компоненты опциональны. Приложение читает флаги из QSettings и создаёт только нужные табы.

### Флаги features/* в QSettings
| Флаг | Что включает | Обвязка |
|---|---|---|
| features/ollama | Таб Ollama Chat | бинарник Ollama + модели |
| features/sdxl | Таб Diffusers | SDXL venv + torch + модели |
| features/image_prep | Таб Visual editor | не требует обвязки |
| features/upscaler | Апскейлер (будущее) | Real-ESRGAN или аналог |

### Ключевые решения
- Visual editor **независим от Diffusers** — просто готовит изображения; бэкенд (img2img / апскейлинг) зависит от установленного
- Visual editor **отключается**, если нужна только LLM
- Минимум один компонент должен быть установлен; иначе заглушка
- Апскейлер в будущем: **Real-ESRGAN** (~64 MB, быстрый на CPU, не диффузионный)

### Порядок шагов уровня 2 инсталлера
Принцип: **сначала инфраструктура, потом данные** (модели качаем в конце).
1. step_paths — настройка путей
2. step_ollama — бинарник Ollama (2.1 GB)
3. step_sdxl_env — SDXL venv + torch/diffusers (тяжёлый, подшаги)
4. step_models — скачивание моделей (SDXL ~7 GB + Ollama)

Если torch не встанет на шаге 3 — модели ещё не скачаны, потерь нет.

## 6. Аудит конфликтов усечённого приложения

8 файлов с жёсткими предположениями о трёх табах. Нужно доработать:

| Файл | Конфликт | Доработка |
|---|---|---|
| main.py | validate_all() требует все 4 пути | validate_installed() по флагам |
| ui/main_window.py | Создаёт все 3 таба | Условное создание по флагам |
| ui/main_window.py | QTimer запускает Ollama всегда | Не запускать, если features/ollama=false |
| ui/main_window.py | _save_bar_state: жёсткие индексы | Имя таба вместо индекса |
| ui/main_window.py | on_generation_stopped: жёсткие индексы | Динамический поиск |
| ui/cleanup_dialog.py | Обращение к tab.worker без проверки None | if tab and tab.worker |
| core/resource_manager.py | on_tab_changed по индексу | Принимать имя модуля |
| ui/dialogs/settings/settings_dialog.py | 3 вкладки всегда | Условные вкладки |

### План доработок (снизу вверх)
1. utils/config.py — get_feature/set_feature
2. core/path_validator.py — validate_installed
3. core/resource_manager.py — on_tab_changed по имени
4. ui/cleanup_dialog.py — обработка None
5. ui/main_window.py — условные табы (самый большой блок)
6. main.py — условный диалог настроек
7. ui/dialogs/settings/settings_dialog.py — условные вкладки
8. installer/ — запись флагов

## 7. Принципы работы с Корбеном

- Общение неформальное, на ты, имя Корбен
- Цикл: Отчёт → блоки документации → команды → «готово»
- Все правки — командой для терминала с проверкой применения
- Бэкапы в /home/lin/Scripts/LocalAILite/Backup
- Не спеша, в удовольствие — дедлайнов нет
- Корбен внимателен к нюансам, ценит честность и тщательность
- Перед правкой файла — посмотреть его актуальное состояние

## 8. Подводные камни

- Git-репозиторий в Repo/, не в рабочей папке
- sync_repo.sh копирует main.py, core/, ui/, scripts/, utils/, installer/ в Repo/. НЕ копирует docs/, Repo/, full_context.py, PHILOSOPHY.md
- PHILOSOPHY.md в корне Repo/ (для GitHub) + копия в docs/; не синхронизируется автоматически
- docs/ из рабочей папки вручную копировать в Repo/docs/ перед коммитом
- full_context.py перегенерируется через ./save_context.sh
- pip-PyQt6 падает на CPU без sse4_2/popcnt — использовать системный из pacman
- Ollama данные в ~/.ollama, не в data/ollama
- Xeon E5450: SDXL очень медленный (~1-2 мин/шаг на 512×512), без AVX2

## 9. Где что лежит

/home/lin/Scripts/LocalAILite/          # Рабочая папка
├── installer/                           # Инсталлятор (уровень 1 готов)
├── core/, ui/, scripts/, utils/         # Приложение
├── data/                                # Рабочие данные (5 папок)
├── docs/                                # Документация
├── Repo/                                # Git-репозиторий (GitHub)
├── Backup/                              # Бэкапы
├── full_context.py                      # Контекст кода для LLM
└── save_context.sh                      # Перегенерация full_context.py

## 10. Быстрые команды

cd /home/lin/Scripts/LocalAILite
python3 installer/cli.py                 # Бутстрап (уровень 1)
venv/bin/python main.py                  # Запуск приложения
./save_context.sh                        # Перегенерация full_context.py
cd Repo && git status                    # Git-статус

## 11. Что делать дальше

1. Реализация усечённого приложения — план из раздела 6 (начать с utils/config.py)
2. Уровень 2 инсталлятора — step_paths, step_ollama, step_sdxl_env, step_models, UI-визард
3. Публикация — скрины UI в README, анонсы перед открытием на GitHub

Перед началом кода — прочитать разделы 5, 6 этого документа и docs/PROJECT_MANIFEST.md (раздел «КОНЦЕПЦИЯ УСЕЧЁННОГО ПРИЛОЖЕНИЯ»).
