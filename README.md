# LocalAILite — Локальный AI-ассистент

Приложение для работы с локальными AI-моделями: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор.

**Платформа:** Manjaro Linux, PyQt6, Python 3.14

---

## 🧩 Статус модулей

### Оболочка и UI

| Модуль | Версия | Роль |
|--------|--------|------|
| main.py | v1.2.0 | Точка входа: QApplication, валидация путей, запуск MainWindow |
| ui/main_window.py | v1.2.0 | Главное окно: 3 вкладки, меню, OllamaManager, SharedBottomBar |
| ui/shared_bottom_bar.py | v1.2.0 | Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU, индикатор ресурса, радиокнопки, единая кнопка действия |
| ui/cleanup_dialog.py | v1.2.0 | Диалог освобождения ресурсов при закрытии (5 шагов) |
| ui/chat_widget.py | v1.0.0 | QTextBrowser + стриминг токенов + копирование кода |
| ui/settings_panel.py | v1.0.0 | Правая панель Ollama (модель, temperature, timeout) |

### Вкладки

| Модуль | Версия | Роль |
|--------|--------|------|
| ui/tabs/ollama_tab.py | v1.2.0 | Чат: ChatWidget + SettingsPanel + OllamaClient, acquire/release ресурса |
| ui/tabs/diffusers_tab.py | v1.2.0 | Генерация: preview + settings + DiffusersWorker, управление чекпоинтами и историей |
| ui/tabs/diffusers_settings_panel.py | v1.0.0 | Настройки Diffusers + список архивных чекпоинтов |
| ui/tabs/image_prep_tab.py | v1.1.0 | Visual editor: превью + галерея + обработка изображений |
| ui/tabs/image_prep_panel.py | v1.1.0 | Правая панель Visual editor (пресет, crop mode) |

### Ядро (core/)

| Модуль | Версия | Роль |
|--------|--------|------|
| core/chat_manager.py | v1.0.0 | История чата (messages list), экспорт в Markdown |
| core/ollama_client.py | v1.0.0 | QThread-клиент к Ollama API (/api/chat), стриминг токенов |
| core/ollama_manager.py | v1.2.0 | Управление ollama serve, проверка RAM, CPU affinity, nice-приоритет |
| core/diffusers_worker.py | v1.2.0 | QProcess-обёртка для generate_diffusers.py, проверка RAM, CPU limits, history_dir |
| core/checkpoint_manager.py | v1.0.0 | Чекпоинты: JSON + PT, архивация с timestamp |
| core/history_manager.py | v1.1.0 | Менеджер истории: data/history/{timestamp}/, метаданные, PNG на каждом шаге |
| core/resource_manager.py | v1.2.0 | Управление ресурсом (GPU/RAM): acquire/release, 2 арендатора (Ollama, Diffusers) |
| core/resource_monitor.py | v1.2.0 | Мониторинг RAM/CPU, оценка потребления, лимиты, CPU affinity |
| core/image_processor.py | v1.1.0 | Обработка изображений: resize, crop (center/letterbox/stretch) |
| core/path_validator.py | v1.0.0 | Валидация venv, моделей, output, Ollama URL |
| core/markdown_parser.py | v1.0.0 | Markdown в HTML с адаптацией под системную тему KDE |

### Скрипты (scripts/)

| Модуль | Версия | Роль |
|--------|--------|------|
| scripts/generate_diffusers.py | v1.2.0 | CLI-генерация SDXL, callback_on_step_end, history_dir, resume, оптимизация CPU |
| scripts/encode_image.py | v1.1.0 | Кодирование изображения в latents через VAE (для img2img) |
| scripts/test_vae_roundtrip.py | v1.1.0 | Тест VAE encode/decode roundtrip |

### Утилиты

| Модуль | Версия | Роль |
|--------|--------|------|
| utils/config.py | v1.1.0 | QSettings-обёртка + пути (data/, bin/ollama/, history/, init_images/) |

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
│   ├── history_manager.py               # Менеджер истории генерации
│   ├── image_processor.py               # Обработка изображений
│   ├── markdown_parser.py               # Markdown в HTML
│   ├── ollama_client.py                 # QThread-клиент к Ollama API
│   ├── ollama_manager.py                # Управление ollama serve
│   ├── path_validator.py                # Валидация путей
│   ├── resource_manager.py              # Управление ресурсом (GPU/RAM)
│   └── resource_monitor.py              # Мониторинг RAM/CPU, лимиты
│
├── scripts/                             # CLI-скрипты (запускаются в venv)
│   ├── generate_diffusers.py            # Генерация SDXL
│   ├── encode_image.py                  # Кодирование изображения в latents
│   └── test_vae_roundtrip.py            # Тест VAE roundtrip
│
├── ui/                                  # PyQt6 интерфейс
│   ├── main_window.py                   # Главное окно (3 вкладки)
│   ├── chat_widget.py                   # QTextBrowser + стриминг
│   ├── cleanup_dialog.py                # Диалог очистки ресурсов
│   ├── settings_panel.py                # Панель настроек Ollama
│   ├── shared_bottom_bar.py             # Общая нижняя панель
│   ├── dialogs/                         # Диалоги настроек
│   │   ├── paths_dialog.py              # Стартовый диалог путей
│   │   ├── diffusers_models_dialog.py   # Управление моделями
│   │   ├── history_save_dialog.py       # Диалог сохранения истории
│   │   └── settings/
│   │       ├── settings_dialog.py       # Окно настроек
│   │       ├── paths_settings_widget.py
│   │       ├── diffusers_settings_widget.py
│   │       └── resources_settings_widget.py
│   └── tabs/                            # Вкладки главного окна
│       ├── ollama_tab.py                # Чат
│       ├── diffusers_tab.py             # Генерация
│       ├── diffusers_settings_panel.py  # Настройки Diffusers
│       ├── image_prep_tab.py            # Visual editor
│       └── image_prep_panel.py          # Панель Visual editor
│
├── utils/
│   └── config.py                        # QSettings-обёртка
│
├── bin/ollama/                          # Локальные бинарники Ollama (в gitignore)
└── data/                                # Рабочие данные (в gitignore)
    ├── cache/                           # Кэш моделей HuggingFace
    ├── checkpoints/                     # Архивные чекпоинты
    ├── history/                         # История генерации: {timestamp}/step_NNNN.{png,pt,json}
    ├── init_images/                     # Подготовленные изображения для img2img
    ├── logs/                            # Логи
    ├── ollama/                          # Данные Ollama
    ├── pids/                            # PID-файлы
    └── previews/                        # Промежуточные PNG превью
```

---

## 🛠️ Запуск

### Зависимости

```
pip install PyQt6 requests psutil diffusers torch torchvision torchaudio pillow
```

### Запуск приложения

```
python main.py
```

При первом запуске откроется диалог настройки путей (venv, модели, output, Ollama URL).

---

## 🔄 Git-воркфлоу

- **main** — стабильные релизы
- **dev** — активная разработка

Формат коммитов: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`, `chore: ...`

---

## 📊 Ключевые возможности

- **Три режима работы**: чат с Ollama + генерация изображений SDXL + визуальный редактор
- **Модульная архитектура**: SRP, сигнальная маршрутизация, изолированные потоки
- **Управление ресурсами**: 2 арендатора (Ollama, Diffusers), только один генерирует одновременно
- **Чекпоинты генерации**: сохранение/восстановление прогресса (latents + scheduler + generator)
- **История генерации**: PNG + PT + JSON на каждом шаге в data/history/{timestamp}/
- **Ollama Manager**: автоматический запуск/остановка сервера, обработка конфликтов портов
- **SharedBottomBar**: единая нижняя панель для всех табов (промпт, прогресс, таймер, RAM/CPU, индикатор ресурса, единая кнопка действия)
- **CleanupDialog**: корректное освобождение ресурсов при закрытии (5 шагов)
- **Markdown-парсер**: подсветка кода, копирование блоков, адаптация под системную тему KDE
- **Нативная тема KDE**: без артефактов, адаптивный UI
- **Контроль ресурсов**: проверка RAM перед запуском, CPU affinity, nice-приоритет, env-переменные
- **Цветовая подсветка статусов**: серый (логи), золотой (статусы), оранжевый (предупреждения), красный (ошибки), зелёный (успех)
- **Изоляция табов**: каждый таб ведёт свой статус, MainWindow не пишет в SharedBottomBar напрямую
- **Свободное переключение вкладок**: генерация не прерывается при уходе с таба

---

## 📈 Архитектурные принципы

| Принцип | Реализация | Выгода |
|---------|------------|--------|
| **UI = View** | Вкладки не делают requests/socket, только отрисовка и маршрутизация сигналов | Устранение UI-фризов, безопасность потоков |
| **Ядро = Бизнес-логика** | Чекпоинты, Ollama API, генерация вынесены в core/ | Переиспользование, изоляция багов |
| **QProcess для тяжёлых задач** | Diffusers запускается в отдельном процессе | Изоляция, возможность остановки, логирование |
| **QThread для сетевых запросов** | OllamaClient работает в отдельном потоке | Не блокирует UI |
| **Сигнальная шина** | pyqtSignal для навигации и передачи данных между вкладками | Слабая связность, безопасное переключение контекста |
| **Единый конфиг** | QSettings-обёртка (utils/config.py) | Централизованное управление настройками |
| **Чекпоинты = атомарность** | JSON + PT, архивация с timestamp | Защита от потери прогресса |
| **Ресурсы = мониторинг** | ResourceMonitor + ResourceManager, лимиты RAM/CPU | Предотвращение OOM, контроль нагрузки |
| **Очистка = корректность** | CleanupDialog с 5 шагами при закрытии | Освобождение памяти, остановка процессов |
| **История = воспроизводимость** | Каждый шаг генерации сохраняется (PNG + PT + JSON) | Возможность экспериментов, сравнения, resume |
| **Свободное переключение** | Табы не блокируются, блокируется только кнопка "Запустить" | UX: можно смотреть историю пока идёт генерация |
| **Изоляция статусов** | Каждый таб ведёт свой _bar_state | Чистая архитектура, нет конфликтов |

---

## 📜 Лицензия

MIT
