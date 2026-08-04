## LocalAILite — структура проекта
> Локальный AI-ассистент: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор.
> Платформа: Manjaro Linux, PyQt6, Python 3.14.

## Файлы проекта

    LocalAILite/
    ├── main.py                              # Точка входа: QApplication, валидация путей, запуск MainWindow
    ├── full_context.py                      # Склеенный контекст всех файлов (для LLM)
    ├── full_docs.py                         # Склеенная документация (для LLM)
    ├── get_context.sh                       # Точечная выгрузка файлов для LLM
    ├── save_context.sh                      # Скрипт обновления full_context.py
    ├── sync_repo.sh                         # Синхронизация рабочей папки -> Repo
    ├── backup.sh                            # Полный бэкап в Backup/
    ├── merge_docs.py                        # Скрипт склейки документации в full_docs.py
    ├── docs/                                # Документация
    │   ├── CHANGELOG.md                     # История версий
    │   ├── PROJECT_MANIFEST.md              # Контракты и архитектура
    │   ├── STRUCTURE.md                     # Этот файл
    │   ├── PHILOSOPHY.md                    # Философия проекта
│   └── ROADMAP.md                       # План развития
    │
    ├── core/                                # Ядро (логика без UI)
    │   ├── chat_manager.py                  # История чата (messages list)
    │   ├── checkpoint_manager.py            # Чекпоинты генерации: JSON + PT, архивация
    │   ├── diffusers_worker.py              # QProcess-обёртка для generate_diffusers.py
    │   ├── history_manager.py               # Менеджер истории: data/history/{timestamp}/
    │   ├── image_processor.py               # Обработка изображений: resize, crop, letterbox, stretch
    │   ├── markdown_parser.py               # Markdown в HTML (подсветка кода, ссылки, списки)
    │   ├── models_registry.py               # Реестр моделей: красивое имя ↔ путь
    │   ├── ollama_client.py                 # QThread-клиент к Ollama API (/api/chat)
    │   ├── ollama_manager.py                # Управление ollama serve (старт/стоп/конфликты портов)
    │   ├── path_validator.py                # Валидация venv, моделей, output, Ollama URL
    │   ├── resource_manager.py              # Управление ресурсом: acquire/release, 2 арендатора
    │   └── resource_monitor.py              # Мониторинг RAM/CPU, реальная проверка RAM, лимиты, PID
    │
    ├── scripts/                             # CLI-скрипты (запускаются в venv)
    │   ├── generate_diffusers.py            # Генерация SDXL: callback_on_step_end, чекпоинты, точный resume
    │   ├── compare_images.py                # Попиксельное сравнение изображений (numpy)
    │   ├── encode_image.py                  # Кодирование изображения в latents через VAE (для img2img)
    │   └── test_vae_roundtrip.py            # Тест VAE encode/decode roundtrip
    │
    ├── ui/                                  # PyQt6 интерфейс
    │   ├── main_window.py                   # Главное окно: 3 вкладки, меню, OllamaManager, SharedBottomBar
    │   ├── chat_widget.py                   # QTextBrowser + стриминг токенов + копирование кода
    │   ├── cleanup_dialog.py                # Диалог освобождения ресурсов при закрытии (5 шагов)
    │   ├── settings_panel.py                # Правая панель Ollama (модель, temperature, timeout)
    │   ├── shared_bottom_bar.py             # Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU, кнопка
    │   ├── dialogs/                         # Диалоги настроек
    │   │   ├── paths_dialog.py              # Стартовый диалог настройки путей
    │   │   ├── diffusers_models_dialog.py   # Управление моделями (список, удалить, открыть)
    │   │   ├── history_save_dialog.py       # Диалог сохранения истории генерации
    │   │   └── settings/
    │   │       ├── settings_dialog.py       # Окно настроек (вкладки)
    │   │       ├── paths_settings_widget.py         # Вкладка Общие
    │   │       ├── diffusers_settings_widget.py     # Вкладка Diffusers
    │   │       └── resources_settings_widget.py     # Вкладка Ресурсы
    │   └── tabs/                            # Вкладки главного окна
    │       ├── ollama_tab.py                # Чат: ChatWidget + SettingsPanel + OllamaClient
    │       ├── diffusers_tab.py             # Генерация: preview + settings + DiffusersWorker
    │       ├── diffusers_settings_panel.py  # Настройки Diffusers + список архивных чекпоинтов
    │       ├── image_prep_tab.py            # Visual editor: превью + галерея + обработка
    │       └── image_prep_panel.py          # Правая панель Visual editor (пресет, crop mode)
    │
    ├── utils/
    │   └── config.py                        # QSettings-обёртка + пути (data/, bin/ollama/, history/, previews/)
    │
    ├── Repo/                                # Git-репозиторий (GitHub)
    │   ├── README.md                        # README для GitHub
    │   └── docs/                            # Копия docs/ для merge_docs.py
    │
    ├── bin/ollama/                          # Локальные бинарники Ollama + CUDA/Vulkan libs (в gitignore)
    └── data/                                # Рабочие данные (в gitignore)
        ├── cache/                           # Кэш моделей HuggingFace
        ├── checkpoints/                     # Архивные чекпоинты (YYYY-MM-DD_HH-MM-SS.json/.pt)
        ├── history/                         # История генерации: {timestamp}/step_NNNN.{pt,json} + metadata.json
        ├── init_images/                     # Подготовленные изображения для img2img
        ├── logs/                            # Логи diffusers_*.log и ollama.log
        ├── ollama/                          # Данные Ollama (ключи, история)
        ├── pids/                            # PID-файлы (ollama.pid, diffusers.pid)
        └── previews/                        # Промежуточные PNG превью шагов (технические)

## Потоки данных

    Чат с Ollama: SharedBottomBar -> MainWindow.on_prompt_submitted -> OllamaTab.handle_prompt -> OllamaClient (QThread) -> ChatWidget.append_token
    Генерация SDXL: SharedBottomBar -> DiffusersTab.handle_prompt -> DiffusersWorker (QProcess) -> scripts/generate_diffusers.py -> callback_on_step_end -> history_manager
    Старт Ollama: MainWindow.init -> OllamaManager.start -> проверка порта -> QProcess("ollama serve") с LD_LIBRARY_PATH
    Закрытие: MainWindow.closeEvent -> CleanupDialog -> CleanupThread: стоп Diffusers -> выгрузка Ollama -> стоп сервера -> gc.collect()
    Чекпоинты: data/history/{timestamp}/step_NNNN.pt (latents + scheduler + generator) + step_NNNN.json (метаданные)
    Resume: DiffusersTab -> DiffusersWorker (--resume --resume-step-file) -> generate_diffusers.py (срез timesteps + компенсация init_noise_sigma)

## Управление ресурсами

    ResourceManager управляет двумя арендаторами: Ollama, Diffusers.
    Только один модуль может генерировать одновременно (кнопка "Запустить" блокируется).
    Табы переключаются свободно, выгрузка неактивных модулей через unload() (не останавливает активную генерацию).
    ResourceMonitor проверяет реальную RAM перед запуском (psutil.virtual_memory), применяет CPU affinity и nice-приоритет.
