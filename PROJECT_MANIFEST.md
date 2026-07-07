# LocalAILite — Project Manifest

## ЦЕЛЬ ПРОЕКТА

Модульное приложение на PyQt6 для работы с локальными AI-моделями на Manjaro Linux. Два режима: чат с Ollama + генерация изображений (SDXL/Diffusers). Единый GUI с вкладками, общая нижняя панель, управление ресурсами, чекпоинты генерации.

---

## АРХИТЕКТУРА

### Оболочка + 2 UI-вкладки + ядро

| Модуль | Версия | Роль |
|--------|--------|------|
| `main.py` | v1.0.0 | **Точка входа**. QApplication, валидация путей через PathValidator, запуск MainWindow, диалог настройки путей при первом запуске. |
| `ui/main_window.py` | v1.0.0 | **Оболочка**. QTabWidget (2 вкладки: Ollama Chat, Diffusers), SharedBottomBar, меню, OllamaManager, корректный closeEvent с CleanupDialog. |
| `ui/tabs/ollama_tab.py` | v1.0.0 | **Чат**. ChatWidget + SettingsPanel + OllamaClient (QThread), управление историей через ChatManager. |
| `ui/tabs/diffusers_tab.py` | v1.0.0 | **Генерация**. QGraphicsView для превью, DiffusersSettingsPanel, DiffusersWorker (QProcess), управление чекпоинтами. |
| `ui/shared_bottom_bar.py` | v1.0.0 | **Общая панель**. Поле ввода промпта, прогрессбар, таймер, индикаторы RAM/CPU, статусная строка. |
| `ui/cleanup_dialog.py` | v1.0.0 | **Очистка**. Диалог освобождения ресурсов при закрытии (5 шагов): остановка Diffusers, выгрузка модели Ollama, стоп сервера, очистка памяти. |
| `ui/chat_widget.py` | v1.0.0 | **Чат-браузер**. QTextBrowser с рендерингом Markdown, стриминг токенов, копирование кода по клику, контекстное меню. |
| `ui/settings_panel.py` | v1.0.0 | **Настройки Ollama**. Правая панель (модель, temperature, top_p, max_tokens, timeout, stream, system_prompt). |
| `ui/tabs/diffusers_settings_panel.py` | v1.0.0 | **Настройки Diffusers**. Модель, scheduler, steps, cfg, size, seed, preview_every, preview_start, negative_prompt, список архивных чекпоинтов. |
| `ui/dialogs/paths_dialog.py` | v1.0.0 | **Стартовый диалог**. Настройка путей (venv, модели, output, Ollama URL) с валидацией. |
| `ui/dialogs/diffusers_models_dialog.py` | v1.0.0 | **Управление моделями**. Список, удаление, открытие папки, ссылки на ресурсы (HuggingFace, CivitAI). |
| `ui/dialogs/settings/settings_dialog.py` | v1.0.0 | **Окно настроек**. Вкладки (Общие, Diffusers, Ресурсы). |
| `ui/dialogs/settings/paths_settings_widget.py` | v1.0.0 | **Вкладка Общие**. Настройки путей с валидацией в реальном времени. |
| `ui/dialogs/settings/diffusers_settings_widget.py` | v1.0.0 | **Вкладка Diffusers**. Device, safety_checker, управление моделями. |
| `ui/dialogs/settings/resources_settings_widget.py` | v1.0.0 | **Вкладка Ресурсы**. max_ram_percent, cpu_cores, cpu_priority. |

### Ядро (core/)

| Модуль | Версия | Роль |
|--------|--------|------|
| `core/chat_manager.py` | v1.0.0 | История чата (messages list), добавление/получение сообщений, экспорт в Markdown. |
| `core/ollama_client.py` | v1.0.0 | QThread-клиент к Ollama API (/api/chat), стриминг токенов, извлечение статистики (tokens/sec, duration). |
| `core/ollama_manager.py` | v1.0.0 | Управление процессом ollama serve (старт/стоп), проверка порта 11434, обработка конфликтов, логирование, PID-файлы. |
| `core/diffusers_worker.py` | v1.0.0 | QProcess-обёртка для scripts/generate_diffusers.py, парсинг JSON-вывода, логирование, сигналы (step_updated, generation_finished, error_occurred). |
| `core/checkpoint_manager.py` | v1.0.0 | Менеджер чекпоинтов генерации. Сохранение latents + scheduler + generator в PT, метаданные в JSON, архивация с timestamp, загрузка из архива. |
| `core/resource_manager.py` | v1.0.0 | Переключение табов + выгрузка неактивных модулей (вызов unload()). |
| `core/resource_monitor.py` | v1.0.0 | Мониторинг RAM/CPU через psutil, оценка потребления для Diffusers/Ollama, применение лимитов (cpu_affinity, priority, env). |
| `core/path_validator.py` | v1.0.0 | Валидация путей (venv, модели, output, Ollama URL), проверка доступности, подсчёт моделей. |
| `core/markdown_parser.py` | v1.0.0 | Парсер Markdown в HTML с адаптацией под системную тему KDE, подсветка кода, кнопки копирования, обработка ссылок, списков, заголовков. |

### Скрипты (scripts/)

| Модуль | Версия | Роль |
|--------|--------|------|
| `scripts/generate_diffusers.py` | v1.0.0 | CLI-скрипт генерации SDXL. Поддержка single-file моделей, HF-формата, resume из чекпоинта, callback для прогресса, сохранение превью. |

### Утилиты (utils/)

| Модуль | Версия | Роль |
|--------|--------|------|
| `utils/config.py` | v1.0.0 | QSettings-обёртка с методами для Ollama, Diffusers, путей. Миграция из старой версии OllamaChat. |

---

## ПРИНЦИПЫ АРХИТЕКТУРЫ

| Принцип | Реализация | Выгода |
|---------|------------|--------|
| **UI = View** | Вкладки не делают requests/socket, только отрисовка и маршрутизация сигналов | Устранение UI-фризов, безопасность потоков |
| **Ядро = Бизнес-логика** | Чекпоинты, Ollama API, генерация вынесены в core/ | Переиспользование, изоляция багов |
| **QProcess для тяжёлых задач** | Diffusers запускается в отдельном процессе через QProcess | Изоляция, возможность остановки, логирование |
| **QThread для сетевых запросов** | OllamaClient работает в отдельном потоке | Не блокирует UI |
| **Сигнальная шина** | pyqtSignal для навигации и передачи данных между вкладками | Слабая связность, безопасное переключение контекста |
| **Единый конфиг** | QSettings-обёртка (utils/config.py) | Централизованное управление настройками |
| **Чекпоинты = атомарность** | JSON + PT, архивация с timestamp | Защита от потери прогресса |
| **Ресурсы = мониторинг** | ResourceMonitor + ResourceManager, лимиты RAM/CPU | Предотвращение OOM, контроль нагрузки |
| **Очистка = корректность** | CleanupDialog с 5 шагами при закрытии | Освобождение памяти, остановка процессов |

---

## КОНТРАКТЫ

### Данные
- Все настройки хранятся в QSettings через `utils/config.py`
- Чекпоинты: `data/checkpoints/checkpoint.json` (метаданные) + `checkpoint.pt` (latents, scheduler, generator)
- Архивные чекпоинты: `data/checkpoints/YYYY-MM-DD_HH-MM-SS.json/.pt`
- Логи: `data/logs/diffusers_*.log`, `data/logs/ollama.log`
- PID-файлы: `data/pids/ollama.pid`
- Превью: `data/previews/sdxl_{seed}_step{step:04d}.png`

### Сеть
- Все запросы к Ollama API идут через `core/ollama_client.py` (QThread)
- Endpoint: `http://127.0.0.1:11434/api/chat` (стриминг токенов)
- Endpoint: `http://127.0.0.1:11434/api/tags` (список моделей)
- Endpoint: `http://127.0.0.1:11434/api/generate` (keep_alive=0 для выгрузки модели)
- Endpoint: `http://127.0.0.1:11434/api/ps` (проверка запущенных моделей)
- Timeout: настраивается через UI (по умолчанию 600с)
- Retry: нет (ошибки пробрасываются в UI)

### Конфигурация
- Все изменения в настройках проходят через `utils/config.py` (QSettings)
- Миграция из старой версии: `QSettings("OllamaChat", "OllamaChat")` → `QSettings("LocalAILite", "LocalAILite")`
- Пути: venv, модели, output, Ollama URL — валидируются через `core/path_validator.py`
- Ресурсы: max_ram_percent, cpu_cores, cpu_priority — применяются через `core/resource_monitor.py`

### Сигналы
- **prompt_submitted(str)** → `MainWindow.on_prompt_submitted` → активный таб.handle_prompt()
- **generation_stopped()** → активный таб.stop_generation()
- **state_changed(dict)** → `MainWindow._on_tab_state_changed` → обновление SharedBottomBar
- **step_updated(int, int, str)** → DiffusersTab._on_step_updated → обновление прогресса и превью
- **generation_finished(str, int)** → DiffusersTab._on_generation_finished → финальное изображение
- **error_occurred(str)** → DiffusersTab._on_error → статусная строка
- **token_received(str)** → OllamaTab.on_token → стриминг в ChatWidget
- **stats_received(dict)** → OllamaTab.on_stats → статистика (tokens/sec, duration)

### Потоки
- OllamaClient работает в QThread (сетевые запросы)
- DiffusersWorker запускает QProcess (генерация изображений)
- CleanupThread работает в QThread (очистка ресурсов при закрытии)
- ResourceMonitor использует psutil (мониторинг RAM/CPU каждые 2 сек)
- Межпоточные вызовы UI → только через pyqtSignal

### Чекпоинты
- Сохранение: `checkpoint_manager.save_checkpoint(latents, scheduler, generator, params, current_step, remaining_timesteps, actual_seed, last_preview_path)`
- Загрузка активного: `checkpoint_manager.load_checkpoint()` → (json_data, torch_data)
- Загрузка архивного: `checkpoint_manager.load_archived_checkpoint(filename)` → (json_data, torch_data)
- Архивация: `checkpoint_manager.archive_checkpoint()` → переименование с timestamp
- Удаление: `checkpoint_manager.delete_checkpoint()` (после успешного завершения)
- Resume: `scripts/generate_diffusers.py --resume --checkpoint-file {filename}`

---

## ПУТИ И КОНФИГУРАЦИЯ

### Проект
- Точка входа: `main.py`
- Ядро: `core/` (9 модулей)
- UI: `ui/` (2 вкладки + SharedBottomBar + CleanupDialog + 3 диалога настроек)
- Скрипты: `scripts/generate_diffusers.py`
- Утилиты: `utils/config.py`

### Данные (в gitignore)
- `data/cache/` — кэш моделей HuggingFace
- `data/checkpoints/` — чекпоинты (checkpoint.json/.pt + архив)
- `data/logs/` — логи diffusers_*.log и ollama.log
- `data/ollama/` — данные Ollama (ключи, история)
- `data/pids/` — PID-файлы (ollama.pid)
- `data/previews/` — промежуточные PNG превью шагов

### Бинарники (в gitignore)
- `bin/ollama/` — локальные бинарники Ollama + CUDA/Vulkan libs

### Конфигурация (QSettings)
- Организация: "LocalAILite"
- Приложение: "LocalAILite"
- Ключи:
  - `url` — Ollama URL (по умолчанию http://localhost:11434)
  - `sdxl/venv_path` — путь к venv для Diffusers
  - `sdxl/models_path` — путь к папке моделей
  - `sdxl/output_dir` — папка сохранения изображений
  - `sdxl/scheduler` — scheduler (по умолчанию EulerDiscreteScheduler)
  - `sdxl/steps` — количество шагов (по умолчанию 30)
  - `sdxl/cfg` — CFG scale (по умолчанию 7.5)
  - `sdxl/device` — устройство (cuda/cpu)
  - `sdxl/no_safety_checker` — отключение NSFW filter (true/false)
  - `sdxl/preview_every` — сохранение превью каждые N шагов
  - `sdxl/preview_start` — начальный шаг превью
  - `resources/max_ram_percent` — максимум RAM (по умолчанию 80%)
  - `resources/cpu_cores` — количество ядер CPU (по умолчанию 3)
  - `resources/cpu_priority` — приоритет процесса (nice, по умолчанию 0)
  - `temperature`, `top_p`, `max_tokens`, `timeout`, `stream`, `system_prompt`, `model` — настройки Ollama

---

## ТЕХНИЧЕСКИЙ СТЕК

- **Python**: 3.14
- **GUI**: PyQt6
- **Сеть**: requests (для Ollama API)
- **Генерация**: diffusers, torch, torchvision, torchaudio
- **Мониторинг**: psutil
- **Потоки**: QThread (сеть), QProcess (генерация)
- **Конфигурация**: QSettings
- **Git**: ветка main (релизы). Коммиты: feat/fix/refactor/docs/chore

---

## МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ

| Показатель | Значение | Примечание |
|------------|----------|------------|
| Загрузка модели SDXL | ~10-15 сек | Single-file .safetensors, CUDA |
| Генерация 1024×1024 (30 шагов) | ~30-60 сек | Зависит от GPU |
| Чекпоинт (сохранение) | < 1 сек | JSON + PT, атомарная запись |
| Чекпоинт (загрузка) | ~2-3 сек | PT с latents + scheduler state |
| Ollama API (стриминг) | ~0.5-2 сек/токен | Зависит от модели и CPU/GPU |
| Мониторинг RAM/CPU | 2 сек | psutil.virtual_memory() + cpu_percent() |
| Очистка ресурсов (CleanupDialog) | ~3-5 сек | 5 шагов: Diffusers → Ollama модель → сервер → gc |

---

## ПЛАН РАЗВИТИЯ (ROADMAP)

### Высокий приоритет
- **Экспорт чата** в Markdown/PDF (история диалога с Ollama)
- **Batch-генерация** (несколько промптов подряд с разными параметрами)
- **Сравнение чекпоинтов** (визуальное сравнение превью из разных шагов)
- **История генераций** (лог промптов + параметров + результатов)

### Средний приоритет
- **LoRA/Textual Inversion** (поддержка дополнительных моделей для Diffusers)
- **ControlNet** (интеграция для управления позой/структурой)
- **Img2Img** (генерация на основе входного изображения)
- **Upscaling** (увеличение разрешения через ESRGAN/Real-ESRGAN)
- **Темы оформления** (светлая/тёмная, автоопределение через QPalette)

### Низкий приоритет
- **Системный трей** (сворачивание в трей при закрытии)
- **Горячие клавиши** (Ctrl+Enter для отправки, Esc для остановки)
- **Плагины** (расширяемость через внешние модули)
- **Интеграция с HuggingFace Hub** (поиск и скачивание моделей через UI)
- **Автоматическое скачивание Ollama** (через QThread + прогрессбар)

---

## БЫСТРЫЙ СТАРТ ДЛЯ НОВОГО ЧАТА

🔹 Проект: LocalAILite (Manjaro Linux, PyQt6, Python 3.14)
🔹 Ветка: main (GitHub: korbendallas000wt/LocalAILite)
🔹 Архитектура: Модульная, сигнальная маршрутизация, SRP, QProcess для генерации, QThread для сети
🔹 Ключевые файлы:
- main.py v1.0.0 (точка входа, валидация путей)
- ui/main_window.py v1.0.0 (оболочка, 2 вкладки, SharedBottomBar, OllamaManager)
- ui/tabs/ollama_tab.py v1.0.0 (чат, ChatWidget + SettingsPanel + OllamaClient)
- ui/tabs/diffusers_tab.py v1.0.0 (генерация, QGraphicsView + DiffusersWorker)
- ui/shared_bottom_bar.py v1.0.0 (общая панель, промпт, прогресс, таймер, RAM/CPU)
- ui/cleanup_dialog.py v1.0.0 (очистка ресурсов, 5 шагов)
- core/ollama_client.py v1.0.0 (QThread-клиент к Ollama API)
- core/ollama_manager.py v1.0.0 (управление ollama serve)
- core/diffusers_worker.py v1.0.0 (QProcess-обёртка для generate_diffusers.py)
- core/checkpoint_manager.py v1.0.0 (чекпоинты: JSON + PT, архивация)
- core/resource_monitor.py v1.0.0 (мониторинг RAM/CPU, лимиты)
- scripts/generate_diffusers.py v1.0.0 (CLI-генерация SDXL)
- utils/config.py v1.0.0 (QSettings-обёртка)

🔹 Контракты:
- Данные: QSettings через utils/config.py, чекпоинты через core/checkpoint_manager.py
- Сеть: Ollama API через core/ollama_client.py (QThread, timeout=600s)
- Генерация: scripts/generate_diffusers.py через core/diffusers_worker.py (QProcess)
- Ресурсы: core/resource_monitor.py (psutil, лимиты RAM/CPU)
- Сигналы: prompt_submitted(str) ↔ handle_prompt() | state_changed(dict) → SharedBottomBar
- Потоки: OllamaClient (QThread), DiffusersWorker (QProcess), CleanupThread (QThread)

🔹 Стиль работы:
- Отчёт → блоки документации → команды → «готово»
- Комментарии вне bash-блоков, команды копируются целиком
- Общение на «ты», режим «Тишина» по сигналу +тихо

---

## ЗАКЛЮЧЕНИЕ

Проект LocalAILite v1.0.0 — это стабильная производственная база с модульной архитектурой. Ключевые достижения:

- Полное разделение UI и бизнес-логики (SRP)
- Изоляция тяжёлых задач в QProcess (генерация) и QThread (сеть)
- Чекпоинты генерации с атомарной записью и архивацией
- Управление ресурсами (мониторинг RAM/CPU, лимиты)
- Общая нижняя панель (SharedBottomBar) для обоих табов
- Корректная очистка ресурсов при закрытии (CleanupDialog, 5 шагов)
- Адаптация под нативную тему KDE без артефактов

Все модули изолированы, контракты зафиксированы, сигнальная шина отлажена. Код готов к ревью, слиянию в main и последующему развитию.
