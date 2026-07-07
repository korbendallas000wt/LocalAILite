
# LocalAILite — Локальный AI-ассистент

Приложение для работы с локальными AI-моделями: чат с Ollama + генерация изображений (SDXL/Diffusers).

**Платформа:** Manjaro Linux, PyQt6, Python 3.14

---

## 🧩 Статус модулей

| Модуль | Версия | Роль |
|--------|--------|------|
| main.py | v1.0.0 | Точка входа: QApplication, валидация путей, запуск MainWindow |
| ui/main_window.py | v1.0.0 | Главное окно: табы, меню, OllamaManager, SharedBottomBar |
| ui/tabs/ollama_tab.py | v1.0.0 | Чат: ChatWidget + SettingsPanel + OllamaClient |
| ui/tabs/diffusers_tab.py | v1.0.0 | Генерация: preview + settings + DiffusersWorker |
| ui/shared_bottom_bar.py | v1.0.0 | Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU |
| ui/cleanup_dialog.py | v1.0.0 | Диалог освобождения ресурсов при закрытии (5 шагов) |
| ui/chat_widget.py | v1.0.0 | QTextBrowser + стриминг токенов + копирование кода |
| ui/settings_panel.py | v1.0.0 | Правая панель Ollama (модель, temperature, timeout) |
| ui/tabs/diffusers_settings_panel.py | v1.0.0 | Настройки Diffusers + список чекпоинтов |
| core/chat_manager.py | v1.0.0 | История чата (messages list) |
| core/ollama_client.py | v1.0.0 | QThread-клиент к Ollama API (/api/chat) |
| core/ollama_manager.py | v1.0.0 | Управление ollama serve (старт/стоп/конфликты портов) |
| core/diffusers_worker.py | v1.0.0 | QProcess-обёртка для generate_diffusers.py |
| core/checkpoint_manager.py | v1.0.0 | Чекпоинты генерации: JSON + PT, архивация |
| core/resource_manager.py | v1.0.0 | Переключение табов + выгрузка неактивных модулей |
| core/resource_monitor.py | v1.0.0 | Мониторинг RAM/CPU, оценка потребления, лимиты |
| core/path_validator.py | v1.0.0 | Валидация venv, моделей, output, Ollama URL |
| core/markdown_parser.py | v1.0.0 | Markdown в HTML (подсветка кода, ссылки, списки) |
| scripts/generate_diffusers.py | v1.0.0 | CLI-генерация SDXL: модель, loop, callback, чекпоинты |
| utils/config.py | v1.0.0 | QSettings-обёртка + пути (data/, bin/ollama/, previews/) |

---

## 📁 Структура проекта

```
LocalAILite/
├── main.py                              # Точка входа
├── full_context.py                      # Склеенный контекст всех файлов (для LLM)
├── save_context.sh                      # Скрипт обновления full_context.py
├── STRUCTURE.md                         # Структура проекта
├── README.md                            # Этот файл
├── CHANGELOG.md                         # История версий
├── PROJECT_MANIFEST.md                  # Контракты и архитектура
│
├── core/                                # Ядро (логика без UI)
│   ├── chat_manager.py                  # История чата
│   ├── checkpoint_manager.py            # Чекпоинты генерации
│   ├── diffusers_worker.py              # QProcess-обёртка для generate_diffusers.py
│   ├── markdown_parser.py               # Markdown в HTML
│   ├── ollama_client.py                 # QThread-клиент к Ollama API
│   ├── ollama_manager.py                # Управление ollama serve
│   ├── path_validator.py                # Валидация путей
│   ├── resource_manager.py              # Переключение табов + выгрузка
│   └── resource_monitor.py              # Мониторинг RAM/CPU
│
├── scripts/                             # CLI-скрипты (запускаются в venv)
│   └── generate_diffusers.py            # Генерация SDXL
│
├── ui/                                  # PyQt6 интерфейс
│   ├── main_window.py                   # Главное окно
│   ├── chat_widget.py                   # QTextBrowser + стриминг
│   ├── cleanup_dialog.py                # Диалог очистки ресурсов
│   ├── settings_panel.py                # Панель настроек Ollama
│   ├── shared_bottom_bar.py             # Общая нижняя панель
│   ├── dialogs/                         # Диалоги настроек
│   │   ├── paths_dialog.py              # Стартовый диалог путей
│   │   ├── diffusers_models_dialog.py   # Управление моделями
│   │   └── settings/
│   │       ├── settings_dialog.py       # Окно настроек (вкладки)
│   │       ├── paths_settings_widget.py         # Вкладка Общие
│   │       ├── diffusers_settings_widget.py     # Вкладка Diffusers
│   │       └── resources_settings_widget.py     # Вкладка Ресурсы
│   └── tabs/                            # Вкладки главного окна
│       ├── ollama_tab.py                # Чат
│       ├── diffusers_tab.py             # Генерация
│       └── diffusers_settings_panel.py  # Настройки Diffusers
│
├── utils/
│   └── config.py                        # QSettings-обёртка
│
├── bin/ollama/                          # Локальные бинарники Ollama (в gitignore)
└── data/                                # Рабочие данные (в gitignore)
    ├── cache/                           # Кэш моделей HuggingFace
    ├── checkpoints/                     # Чекпоинты (JSON + PT)
    ├── logs/                            # Логи
    ├── ollama/                          # Данные Ollama
    ├── pids/                            # PID-файлы
    └── previews/                        # Промежуточные PNG превью
```

---

## 🛠️ Запуск

### Зависимости

```
pip install PyQt6 requests psutil diffusers torch torchvision torchaudio
```

### Запуск приложения

```
python main.py
```

При первом запуске откроется диалог настройки путей (venv, модели, папка сохранения, Ollama URL).

---

## 🔄 Git-воркфлоу

- **main** — стабильные релизы
- **dev** — активная разработка

Формат коммитов: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`, `chore: ...`

---

## 📊 Ключевые возможности

- **Два режима работы**: чат с Ollama + генерация изображений SDXL
- **Модульная архитектура**: SRP, сигнальная маршрутизация, изолированные потоки
- **Чекпоинты генерации**: сохранение/восстановление прогресса (latents + scheduler + generator)
- **Управление ресурсами**: мониторинг RAM/CPU, лимиты, выгрузка неактивных модулей
- **Ollama Manager**: автоматический запуск/остановка сервера, обработка конфликтов портов
- **SharedBottomBar**: единая нижняя панель для обоих табов (промпт, прогресс, таймер, RAM/CPU)
- **CleanupDialog**: корректное освобождение ресурсов при закрытии (5 шагов)
- **Markdown-парсер**: подсветка кода, копирование блоков, адаптация под системную тему
- **Нативная тема KDE**: без артефактов, адаптивный UI

---

## 📈 Архитектурные принципы

| Принцип | Реализация | Выгода |
|---------|------------|--------|
| **UI = View** | Вкладки не делают requests/socket, только отрисовка и маршрутизация сигналов | Устранение UI-фризов, безопасность потоков |
| **Ядро = Бизнес-логика** | Чекпоинты, Ollama API, генерация вынесены в core/ | Переиспользование, изоляция багов |
| **QProcess для тяжёлых задач** | Diffusers запускается в отдельном процессе через QProcess | Изоляция, возможность остановки, логирование |
| **QThread для сетевых запросов** | OllamaClient работает в отдельном потоке | Не блокирует UI |
| **Сигнальная шина** | pyqtSignal для навигации и передачи данных между вкладками | Слабая связность, безопасное переключение контекста |
| **Единый конфиг** | QSettings-обёртка (utils/config.py) | Централизованное управление настройками |
| **Чекпоинты = атомарность** | JSON + PT, архивация с timestamp | Защита от потери прогресса |

---

## 📜 Лицензия

MIT
