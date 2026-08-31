## LocalAILite — структура проекта
> Локальный AI-ассистент: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор.
> Платформа: Linux (Manjaro, Fedora, Debian, openSUSE, Ubuntu), PyQt6, Python 3.10+.
> Ветки: **dev** (активная разработка), **main** (стабильная, для пользователей).

## Файлы проекта

    LocalAILite/
    ├── main.py                              # Точка входа: QApplication, валидация путей, запуск MainWindow
    ├── install.sh                           # Удобная точка входа инсталлера (проверка Python + запуск cli.py)
    ├── LocalAILite                          # Исполняемая обёртка для запуска приложения
    ├── LocalAILite.desktop                  # Ярлык для запуска из меню/рабочего стола
    ├── docs/                                # Документация
    │   ├── STRUCTURE.md                     # Этот файл (структура + raw-ссылки)
    │   ├── WORKLOG.md                       # Журнал разработки (сессии, баги, коммиты)
    │   ├── CHANGELOG.md                     # История версий (для пользователей)
    │   ├── PROJECT_MANIFEST.md              # Контракты и архитектура
    │   └── PHILOSOPHY.md                    # Философия проекта
        │
    ├── WORK/                                # Локальные файлы разработки (в .gitignore, не пушатся)
    │   └── HANDOFF.md                       # Передача контекста между сессиями (локально)
    │
    ├── core/                                # Ядро (логика без UI)
    │   ├── chat_manager.py                  # История чата (messages list)
    │   ├── chat_versions.py                # Нумерованные чаты (папки, варианты, навигация)
    │   ├── model_validator.py               # Проверка целостности моделей (HF cache, single-file, Ollama)
    │   ├── package_validator.py             # Проверка пакетов venv (баг #15: numpy race condition)
    │   ├── path_validator.py                # Валидация venv, моделей, output, Ollama URL/бинарник/модели
    │   ├── paths_manager.py                 # Единый модуль управления путями (v2.0)
    │   ├── checkpoint_manager.py            # Чекпоинты генерации: JSON + PT, архивация
    │   ├── diffusers_worker.py              # QProcess-обёртка для generate_diffusers.py
    │   ├── history_manager.py               # Менеджер истории: data/diffusers/history/{timestamp}/
    │   ├── image_processor.py               # Обработка изображений: resize, crop, letterbox, stretch
    │   ├── markdown_parser.py               # Markdown в HTML (подсветка кода, ссылки, списки, рендер карточек вложений)
    │   ├── models_registry.py               # Реестр моделей v2.0: короткое имя ↔ {path, full_name, type}
    │   ├── ollama_client.py                 # QThread-клиент к Ollama API (/api/chat)
    │   ├── ollama_manager.py                # Управление ollama serve (старт/стоп/конфликты портов)
    │   ├── ollama_model_info.py          # Кэш лимитов контекста моделей Ollama (TTL 5 мин, /api/show)
    │   ├── context_tracker.py             # Трекер контекста (подсчёт токенов, прогресс в статусбар)
    │   ├── file_reader.py                # Чтение и валидация файлов для вложений
    │   ├── model_downloader.py         # Общий контракт скачивания + OllamaDownloader + DiffusersDownloader
    │   ├── resource_manager.py              # Управление ресурсом: acquire/release, 2 арендатора
    │   ├── resource_monitor.py              # Мониторинг RAM/CPU, реальная проверка RAM, лимиты, PID
    │   └── updater.py                     # Модуль обновлений v2.1: проверка версий (асинхронно, QNetworkAccessManager) + скачивание/установка (QThread)
    │
    ├── scripts/                             # CLI-скрипты (запускаются в venv)
    │   ├── generate_diffusers.py            # Генерация SDXL: callback_on_step_end, чекпоинты, точный resume
    │   ├── compare_images.py                # Попиксельное сравнение изображений (numpy)
    │   ├── encode_image.py                  # Кодирование изображения в latents через VAE (для img2img)
    │   └── test_vae_roundtrip.py            # Тест VAE encode/decode roundtrip
    │
    ├── ui/                                  # PyQt6 интерфейс
    │   ├── main_window.py                   # Главное окно: 3 вкладки, меню, OllamaManager, SharedBottomBar
    │   ├── chat_widget.py                   # Append-only просмотрщик + копирование кода + сигналы вложений (open/remove)
    │   ├── chat_control_panel.py            # Панель управления чатом (4 кнопки: Новый, Отменить, Файл, Сохранить)
    │   ├── cleanup_dialog.py                # Диалог освобождения ресурсов при закрытии (5 шагов)
    │   ├── settings_panel.py                # Правая панель Ollama (модель, temperature, timeout)
    │   ├── shared_bottom_bar.py             # Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU, кнопка
    │   ├── dialogs/                         # Диалоги настроек
    │   │   ├── paths_dialog.py              # Стартовый диалог настройки путей
    │   │   ├── diffusers_models_dialog.py   # Управление моделями (список, удалить, открыть)
    │   │   ├── history_save_dialog.py       # Диалог сохранения истории генерации
    │   │   ├── folder_dialog.py             # Обёртка над QFileDialog с режимами (navigate/select)
    │   │   ├── model_manager_dialog.py      # Менеджер моделей: список, вердикты по железу, скачивание
    │   │   └── settings/
    │   │       ├── settings_dialog.py       # Окно настроек (вкладки)
    │   │       ├── paths_settings_widget.py         # Вкладка Общие
    │   │       ├── chat_settings_widget.py          # Вкладка Чат (формат сохранения, папка)
    │   │       ├── diffusers_settings_widget.py     # Вкладка Diffusers
    │   │       ├── resources_settings_widget.py     # Вкладка Ресурсы
 │   │       └── update_settings_widget.py        # Вкладка Обновления (v2.0)
    │   └── tabs/                            # Вкладки главного окна
    │       ├── ollama_tab.py                # Чат: ChatWidget + SettingsPanel + OllamaClient
    │       ├── diffusers_tab.py             # Генерация: preview + settings + DiffusersWorker
    │       ├── diffusers_settings_panel.py  # Настройки Diffusers + список архивных чекпоинтов
    │       ├── image_prep_tab.py            # Visual editor: превью + галерея + обработка
    │       └── image_prep_panel.py          # Правая панель Visual editor (пресет, crop mode)
    │
    ├── utils/
    │   └── config.py                        # JSON-конфиг (local_config.json) + пути к data/ по компонентам
    │
    ├── installer/                           # Инсталлятор (идемпотентный, 8 шагов + финальная проверка)
    │   ├── cli.py                           # Точка входа: python3 installer/cli.py
    │   ├── detector.py                      # Диагностика железа (ОС, CPU, RAM, GPU, Python, диск)
    │   ├── requirements.py                  # Пороги ресурсов
    │   ├── advisor.py                       # Вердикты (Python/Ollama/SDXL), подбор моделей
    │   ├── config.json                      # Конфигурация инсталлера (URL, пути, пакеты)
    │   ├── config_loader.py                 # Загрузка и валидация config.json
    │   ├── final_check.py                   # Единый модуль глубоких проверок (SDXL env, модели, Ollama)
    │   └── steps/                           # Идемпотентные шаги установки
    │       ├── base.py                      # Контракт шага (InstallStep, StepStatus)
    │       ├── step_config.py               # Создание data/ (5 служебных папок)
    │       ├── step_env.py                  # venv + гибридная стратегия PyQt6
    │       ├── step_paths.py                # Настройка путей (Ollama, SDXL venv, модели, output)
    │       ├── step_ollama.py               # Скачивание бинарника Ollama (~2.1 GB)
    │       ├── step_sdxl_env.py             # SDXL venv + torch/diffusers (~6 GB)
    │       └── step_models.py               # Скачивание моделей Ollama и SDXL
    │
    ├── Repo/                                # Git-репозиторий для ветки main (стабильная)
    │
    └── data/                                # Рабочие данные (в gitignore)
        ├── ollama/
        │   ├── models/                 # Модели Ollama (blobs/manifests)
        │   └── chats/                  # Сохранённые чаты (JSON/TXT)
        ├── diffusers/
        │   ├── history/                # История генерации (timestamp/step_NNNN.{pt,json})
        │   ├── init_images/            # Подготовленные изображения
        │   ├── models/                 # Модели SDXL (чекпоинты)
        │   └── previews/               # Промежуточные превью
        ├── image_prep/
        │   └── presets/                # Зарезервировано для визуального редактора
        └── shared/
            ├── config/                 # local_config.json
            ├── registry/               # model_sources.json, models_registry.json
            ├── logs/                   # Логи (ollama_*.log, diffusers_*.log)
            └── pids/                   # PID-файлы

## Быстрый доступ к модулям (raw-ссылки)

> Формат: raw-ссылка на ветку **dev** (актуальная разработка).
> Модель может попробовать прочитать файл по ссылке через web-инструмент.
> Если не работает (сеть / rate limit / 404) — попросить Корбена показать файл через `cat`.

### Точка входа и корневые файлы

- **main.py** — точка входа: QApplication, валидация путей, запуск MainWindow
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/main.py
- **install.sh** — удобная точка входа инсталлера (проверка Python + запуск cli.py)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/install.sh

### core/ — ядро (логика без UI)

- **chat_manager.py** — история чата (messages list)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/chat_manager.py
- **chat_versions.py** — нумерованные чаты (папки, варианты, навигация)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/chat_versions.py
- **model_validator.py** — проверка целостности моделей (HF cache, single-file, Ollama)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/model_validator.py
- **package_validator.py** — проверка пакетов venv (баг #15: numpy race condition)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/package_validator.py
- **path_validator.py** — валидация venv, моделей, output, Ollama
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/path_validator.py
- **paths_manager.py** — единый модуль управления путями (v2.0)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/paths_manager.py
- **checkpoint_manager.py** — чекпоинты генерации: JSON + PT, архивация
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/checkpoint_manager.py
- **diffusers_worker.py** — QProcess-обёртка для generate_diffusers.py
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/diffusers_worker.py
- **history_manager.py** — менеджер истории: data/diffusers/history/{timestamp}/
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/history_manager.py
- **image_processor.py** — обработка изображений: resize, crop, letterbox, stretch
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/image_processor.py
- **markdown_parser.py** — Markdown в HTML (подсветка кода, ссылки, списки, рендер карточек вложений)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/markdown_parser.py
- **models_registry.py** — реестр моделей v2.0
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/models_registry.py
- **ollama_client.py** — QThread-клиент к Ollama API (/api/chat)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/ollama_client.py
- **ollama_manager.py** — управление ollama serve (старт/стоп/конфликты портов)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/ollama_manager.py
- **ollama_model_info.py** — кэш лимитов контекста моделей Ollama (TTL 5 мин, /api/show)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/ollama_model_info.py
- **context_tracker.py** — трекер контекста (подсчёт токенов, прогресс в статусбар)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/context_tracker.py
- **file_reader.py** — чтение и валидация файлов для вложений
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/file_reader.py
- **model_downloader.py** — общий контракт скачивания (прогресс, отмена, верификация) + OllamaDownloader (QProcess) + DiffusersDownloader (huggingface_hub/requests)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/model_downloader.py
- **resource_manager.py** — управление ресурсом: acquire/release, 2 арендатора
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/resource_manager.py
- **resource_monitor.py** — мониторинг RAM/CPU, лимиты, PID
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/resource_monitor.py
- **updater.py** — модуль обновлений v2.1: проверка версий (асинхронно, QNetworkAccessManager) + скачивание/установка (QThread)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/core/updater.py


### installer/ — инсталлятор

- **cli.py** — точка входа инсталлера, оркестрация шагов, финальная проверка
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/cli.py
- **detector.py** — диагностика железа (ОС, CPU, RAM, GPU, Python, диск)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/detector.py
- **requirements.py** — пороги ресурсов
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/requirements.py
- **advisor.py** — вердикты (Python/Ollama/SDXL), подбор моделей
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/advisor.py
- **config.json** — конфигурация инсталлера (URL, пути, пакеты)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/config.json
- **config_loader.py** — загрузка и валидация config.json
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/config_loader.py
- **final_check.py** — единый модуль глубоких проверок (SDXL env, модели, Ollama)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/final_check.py
- **steps/base.py** — контракт шага (InstallStep, StepStatus)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/base.py
- **steps/step_config.py** — создание data/ (5 служебных папок)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_config.py
- **steps/step_env.py** — venv + гибридная стратегия PyQt6
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_env.py
- **steps/step_paths.py** — настройка путей (Ollama, SDXL venv, модели, output)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_paths.py
- **steps/step_ollama.py** — скачивание бинарника Ollama (~2.1 GB)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_ollama.py
- **steps/step_sdxl_env.py** — SDXL venv + torch/diffusers (~6 GB)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_sdxl_env.py
- **steps/step_models.py** — скачивание моделей Ollama и SDXL
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/installer/steps/step_models.py

### scripts/ — CLI-скрипты (запускаются в venv)

- **generate_diffusers.py** — генерация SDXL: чекпоинты, точный resume
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/scripts/generate_diffusers.py
- **compare_images.py** — попиксельное сравнение изображений (numpy)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/scripts/compare_images.py
- **encode_image.py** — кодирование изображения в latents через VAE (для img2img)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/scripts/encode_image.py
- **test_vae_roundtrip.py** — тест VAE encode/decode roundtrip
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/scripts/test_vae_roundtrip.py

### ui/ — PyQt6 интерфейс

- **main_window.py** — главное окно: 3 вкладки, меню, OllamaManager, SharedBottomBar
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/main_window.py
- **chat_widget.py** — Append-only просмотрщик + копирование кода + сигналы вложений (open/remove)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/chat_widget.py
- **chat_control_panel.py** — панель управления чатом (4 кнопки: Новый, Отменить, Файл, Сохранить)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/chat_control_panel.py
- **cleanup_dialog.py** — диалог освобождения ресурсов при закрытии (5 шагов)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/cleanup_dialog.py
- **settings_panel.py** — правая панель Ollama (модель, temperature, timeout)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/settings_panel.py
- **shared_bottom_bar.py** — общая нижняя панель: промпт, прогресс, таймер, RAM/CPU
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/shared_bottom_bar.py
- **dialogs/paths_dialog.py** — стартовый диалог настройки путей
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/paths_dialog.py
- **dialogs/diffusers_models_dialog.py** — управление моделями (список, удалить, открыть)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/diffusers_models_dialog.py
- **dialogs/history_save_dialog.py** — диалог сохранения истории генерации
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/history_save_dialog.py
- **dialogs/folder_dialog.py** — обёртка над QFileDialog с режимами (navigate/select)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/folder_dialog.py
dialogs/model_manager_dialog.py — менеджер моделей: список, вердикты по железу, скачивание с прогрессом и отменой
https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/model_manager_dialog.py
- **dialogs/settings/settings_dialog.py** — окно настроек (вкладки)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/settings/settings_dialog.py
dialogs/settings/update_settings_widget.py — вкладка Обновления (v2.0)
https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/dialogs/settings/update_settings_widget.py
- **tabs/ollama_tab.py** — чат: ChatWidget + SettingsPanel + OllamaClient
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/tabs/ollama_tab.py
- **tabs/diffusers_tab.py** — генерация: preview + settings + DiffusersWorker
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/tabs/diffusers_tab.py
- **tabs/diffusers_settings_panel.py** — настройки Diffusers + архивные чекпоинты
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/tabs/diffusers_settings_panel.py
- **tabs/image_prep_tab.py** — Visual editor: превью + галерея + обработка
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/tabs/image_prep_tab.py
- **tabs/image_prep_panel.py** — правая панель Visual editor (пресет, crop mode)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/ui/tabs/image_prep_panel.py

### utils/

- **config.py** — JSON-конфиг (local_config.json) + пути к data/ по компонентам
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/utils/config.py

### docs/ — документация

- **STRUCTURE.md** — этот файл (структура + raw-ссылки)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/docs/STRUCTURE.md
- **WORKLOG.md** — журнал разработки (сессии, баги, коммиты)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/docs/WORKLOG.md
- **CHANGELOG.md** — история версий (для пользователей)
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/docs/CHANGELOG.md
- **PROJECT_MANIFEST.md** — контракты и архитектура
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/docs/PROJECT_MANIFEST.md
- **PHILOSOPHY.md** — философия проекта
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/dev/docs/PHILOSOPHY.md

## Потоки данных

    Чат с Ollama: SharedBottomBar -> MainWindow.on_prompt_submitted -> OllamaTab.handle_prompt -> OllamaClient (QThread) -> буфер в OllamaTab -> live-строка в статусбар (серым) -> готовый HTML в ChatWidget.append_assistant_message (append-only)
    Генерация SDXL: SharedBottomBar -> DiffusersTab.handle_prompt -> DiffusersWorker (QProcess) -> scripts/generate_diffusers.py -> callback_on_step_end -> history_manager
    Старт Ollama: MainWindow.init -> OllamaManager.start -> проверка порта -> QProcess("ollama serve") с LD_LIBRARY_PATH
    Закрытие: MainWindow.closeEvent -> CleanupDialog -> CleanupThread: стоп Diffusers -> выгрузка Ollama -> стоп сервера -> gc.collect()
    Чекпоинты: data/diffusers/history/{timestamp}/step_NNNN.pt (latents + scheduler + generator) + step_NNNN.json (метаданные)
    Resume: DiffusersTab -> DiffusersWorker (--resume --resume-step-file) -> generate_diffusers.py (срез timesteps + компенсация init_noise_sigma)
    Инсталлер: cli.py -> detector -> advisor -> шаги 0-8 -> final_check (глубокие проверки) -> итог

## Управление ресурсами

    ResourceManager управляет двумя арендаторами: Ollama, Diffusers.
    Только один модуль может генерировать одновременно (кнопка "Запустить" блокируется).
    Табы переключаются свободно, выгрузка неактивных модулей через unload() (не останавливает активную генерацию).
    ResourceMonitor проверяет реальную RAM перед запуском (psutil.virtual_memory), применяет CPU affinity и nice-приоритет.

## Примечание для модели

При вхождении в проект:
1. Прочитай docs/STRUCTURE.md (этот файл — структура + raw-ссылки)
2. Если нужен конкретный модуль — попробуй raw-ссылку из раздела "Быстрый доступ"
3. Если raw-ссылка не работает (сеть/rate limit/404) — попроси Корбена: `cat {путь}`
4. WORK/HANDOFF.md — локальный файл (не в git), проси Корбена показать при необходимости
