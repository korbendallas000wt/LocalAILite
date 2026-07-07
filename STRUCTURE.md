# LocalAILite — структура проекта

> Локальный AI-ассистент: чат с Ollama + генерация изображений (SDXL/Diffusers).
> Платформа: Manjaro Linux, PyQt6, Python 3.14.

## Файлы проекта

LocalAILite/
├── main.py                              # Точка входа: QApplication, валидация путей, запуск MainWindow
├── full_context.py                      # Склеенный контекст всех файлов (для LLM)
── STRUCTURE.md                         # Этот файл
├── save_context.sh                      # Скрипт обновления full_context.py
│
├── core/                                # Ядро (логика без UI)
│   ├── chat_manager.py                  # История чата (messages list)
│   ├── checkpoint_manager.py            # Чекпоинты генерации: JSON + PT, архивация
│   ├── diffusers_worker.py              # QProcess-обёртка для generate_diffusers.py
│   ├── markdown_parser.py               # Markdown в HTML (подсветка кода, ссылки, списки)
│   ├── ollama_client.py                 # QThread-клиент к Ollama API (/api/chat)
│   ├── ollama_manager.py                # Управление ollama serve (старт/стоп/конфликты портов)
│   ├── path_validator.py                # Валидация venv, моделей, output, Ollama URL
│   ├── resource_manager.py              # Переключение табов + выгрузка неактивных модулей
│   └── resource_monitor.py              # Мониторинг RAM/CPU, оценка потребления, лимиты
│
├── scripts/                             # CLI-скрипты (запускаются в venv)
│   └── generate_diffusers.py            # Генерация SDXL: модель, loop, callback, чекпоинты
│
── ui/                                  # PyQt6 интерфейс
│   ├── main_window.py                   # Главное окно: табы, меню, OllamaManager, SharedBottomBar
│   ├── chat_widget.py                   # QTextBrowser + стриминг токенов + копирование кода
│   ├── cleanup_dialog.py                # Диалог освобождения ресурсов при закрытии
│   ├── settings_panel.py                # Правая панель Ollama (модель, temperature, timeout)
│   ├── shared_bottom_bar.py             # Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU
│   ├── dialogs/                         # Диалоги настроек
│   │   ├── paths_dialog.py              # Стартовый диалог настройки путей
│   │   ├── diffusers_models_dialog.py   # Управление моделями (список, удалить, открыть)
│   │   └── settings/
│   │       ├── settings_dialog.py       # Окно настроек (вкладки)
│   │       ├── paths_settings_widget.py         # Вкладка Общие
│   │       ├── diffusers_settings_widget.py     # Вкладка Diffusers
│   │       └── resources_settings_widget.py     # Вкладка Ресурсы
│   └── tabs/                            # Вкладки главного окна
│       ├── ollama_tab.py                # Чат: ChatWidget + SettingsPanel + OllamaClient
│       ├── diffusers_tab.py             # Генерация: preview + settings + DiffusersWorker
│       └── diffusers_settings_panel.py  # Настройки Diffusers + список чекпоинтов
│
├── utils/
│   └── config.py                        # QSettings-обёртка + пути (data/, bin/ollama/, previews/)
│
├── bin/ollama/                          # Локальные бинарники Ollama + CUDA/Vulkan libs
└── data/                                # Рабочие данные (в gitignore)
    ├── cache/                           # Кэш моделей HuggingFace
    ├── checkpoints/                     # Чекпоинты (checkpoint.json/.pt + архив)
    ├── logs/                            # Логи diffusers_*.log и ollama.log
    ├── ollama/                          # Данные Ollama (ключи, история)
    ├── pids/                            # PID-файлы (ollama.pid)
    └── previews/                        # Промежуточные PNG превью шагов

## Потоки данных

- Чат с Ollama: SharedBottomBar -> MainWindow.on_prompt_submitted -> OllamaTab.handle_prompt -> OllamaClient (QThread) -> ChatWidget.append_token
- Генерация SDXL: SharedBottomBar -> DiffusersTab.handle_prompt -> DiffusersWorker (QProcess) -> scripts/generate_diffusers.py -> callback -> checkpoint_manager + превью
- Старт Ollama: MainWindow.__init__ -> OllamaManager.start -> проверка порта -> QProcess("ollama serve") с LD_LIBRARY_PATH
- Закрытие: MainWindow.closeEvent -> CleanupDialog -> CleanupThread: стоп Diffusers -> выгрузка Ollama -> стоп сервера -> gc.collect()
- Чекпоинты: Активный: data/checkpoints/checkpoint.json/.pt -> Архив: data/checkpoints/YYYY-MM-DD_HH-MM-SS.json/.pt
