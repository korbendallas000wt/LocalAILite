# LocalAILite — Project Manifest

## ЦЕЛЬ ПРОЕКТА

Модульное приложение на PyQt6 для работы с локальными AI-моделями на Manjaro Linux. Три режима: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор. Единый GUI с вкладками, общая нижняя панель, управление ресурсами, чекпоинты генерации, история шагов.

---

## АРХИТЕКТУРА

### Оболочка + 3 UI-вкладки + ядро

| Модуль | Версия | Роль |
|--------|--------|------|
| main.py | v1.2.0 | Точка входа. QApplication, валидация путей через PathValidator, запуск MainWindow, диалог настройки путей при первом запуске. |
| ui/main_window.py | v1.2.1 | Оболочка. QTabWidget (3 вкладки: Ollama Chat, Diffusers, Visual editor), SharedBottomBar, меню, OllamaManager, корректный closeEvent с CleanupDialog. Исправлена коллизия имён табов при сохранении состояния. |
| ui/tabs/ollama_tab.py | v1.2.0 | Чат. ChatWidget + SettingsPanel + OllamaClient (QThread), управление историей через ChatManager, acquire/release ресурса. |
| ui/tabs/diffusers_tab.py | v1.2.1 | Генерация. QGraphicsView для превью, DiffusersSettingsPanel, DiffusersWorker (QProcess), управление чекпоинтами и историей. Исправлена утечка ресурса и гонка при остановке. |
| ui/tabs/image_prep_tab.py | v1.1.0 | Visual editor. QGraphicsView + галерея + обработка изображений (resize/crop). |
| ui/shared_bottom_bar.py | v1.2.0 | Общая панель. Поле ввода промпта, прогрессбар, таймер, индикаторы RAM/CPU, индикатор ресурса, радиокнопки (синхронизированы с табами), единая кнопка действия (3 состояния). |
| ui/cleanup_dialog.py | v1.2.1 | Очистка. Диалог освобождения ресурсов при закрытии (5 шагов): остановка Diffusers (включая kill по PID), выгрузка модели Ollama, стоп сервера, очистка памяти. |
| ui/chat_widget.py | v1.0.0 | Чат-браузер. QTextBrowser с рендерингом Markdown, стриминг токенов, копирование кода по клику, контекстное меню. |
| ui/settings_panel.py | v1.0.0 | Настройки Ollama. Правая панель (модель, temperature, top_p, max_tokens, timeout, stream, system_prompt). |
| ui/tabs/diffusers_settings_panel.py | v1.0.0 | Настройки Diffusers. Модель, scheduler, steps, cfg, size, seed, negative_prompt, список архивных чекпоинтов. |
| ui/tabs/image_prep_panel.py | v1.1.0 | Правая панель Visual editor. Пресет разрешения, режим обрезки (center/letterbox/stretch). |
| ui/dialogs/paths_dialog.py | v1.0.0 | Стартовый диалог. Настройка путей (venv, модели, output, Ollama URL) с валидацией. |
| ui/dialogs/diffusers_models_dialog.py | v1.0.0 | Управление моделями. Список, удаление, открытие папки, ссылки на ресурсы (HuggingFace, CivitAI). |
| ui/dialogs/history_save_dialog.py | v1.2.0 | Диалог сохранения истории генерации (чекбокс создания превью, таймер авто-сохранения). |
| ui/dialogs/settings/settings_dialog.py | v1.0.0 | Окно настроек. Вкладки (Общие, Diffusers, Ресурсы). |
| ui/dialogs/settings/paths_settings_widget.py | v1.0.0 | Вкладка Общие. Настройки путей с валидацией в реальном времени. |
| ui/dialogs/settings/diffusers_settings_widget.py | v1.0.0 | Вкладка Diffusers. Device, safety_checker, управление моделями. |
| ui/dialogs/settings/resources_settings_widget.py | v1.0.0 | Вкладка Ресурсы. max_ram_percent, cpu_cores, cpu_priority. |

### Ядро (core/)

| Модуль | Версия | Роль |
|--------|--------|------|
| core/chat_manager.py | v1.0.0 | История чата (messages list), добавление/получение сообщений, экспорт в Markdown. |
| core/ollama_client.py | v1.0.0 | QThread-клиент к Ollama API (/api/chat), стриминг токенов, извлечение статистики (tokens/sec, duration). |
| core/ollama_manager.py | v1.2.0 | Управление процессом ollama serve (старт/стоп), проверка порта 11434, обработка конфликтов, логирование, PID-файлы, проверка RAM, CPU affinity, nice-приоритет. |
| core/diffusers_worker.py | v1.2.0 | QProcess-обёртка для scripts/generate_diffusers.py, парсинг JSON-вывода, логирование, сигналы (step_updated, generation_finished, error_occurred). Проверка RAM, CPU limits, history_dir. Адаптация под diffusers 0.39+ (callback_on_step_end). |
| core/checkpoint_manager.py | v1.0.0 | Менеджер чекпоинтов генерации. Сохранение latents + scheduler + generator в PT, метаданные в JSON, архивация с timestamp, загрузка из архива. |
| core/history_manager.py | v1.1.0 | Менеджер истории генерации. Создаёт папки data/history/{timestamp}/, сохраняет metadata.json, копирует PNG на каждом шаге, список историй, удаление. |
| core/resource_manager.py | v1.2.0 | Управление ресурсом (GPU/RAM): acquire/release, 2 арендатора (Ollama, Diffusers). Переключение табов + выгрузка неактивных модулей. |
| core/resource_monitor.py | v1.2.1 | Мониторинг RAM/CPU через psutil, реальная проверка RAM (psutil.virtual_memory), оценка потребления SDXL 9-11 GB, применение лимитов (cpu_affinity, priority, env-переменные), управление процессами по PID (read_pid_file, is_process_alive, kill_process_by_pid). |
| core/models_registry.py | v1.2.0 | Реестр моделей Diffusers: красивое имя ↔ путь. Сканирование папки моделей, разрешение конфликтов имён. |
| core/image_processor.py | v1.1.0 | Обработка изображений: resize, crop (center/letterbox/stretch), нормализация до кратности 8. |
| core/path_validator.py | v1.0.0 | Валидация путей (venv, модели, output, Ollama URL), проверка доступности, подсчёт моделей. |
| core/markdown_parser.py | v1.0.0 | Парсер Markdown в HTML с адаптацией под системную тему KDE, подсветка кода, кнопки копирования, обработка ссылок, списков, заголовков. |

### Скрипты (scripts/)

| Модуль | Версия | Роль |
|--------|--------|------|
| scripts/generate_diffusers.py | v1.2.1 | CLI-скрипт генерации SDXL. Поддержка single-file моделей, HF-формата, точный resume из чекпоинта (срез timesteps + компенсация init_noise_sigma), callback_on_step_end (diffusers 0.39+), сохранение истории (PT + JSON на каждом шаге), защита от перезаписи PNG, оптимизация CPU (torch.set_num_threads). |
| scripts/compare_images.py | v1.2.1 | Попиксельное сравнение изображений через numpy (для проверки точности resume). |
| scripts/encode_image.py | v1.1.0 | Кодирование изображения в latents через VAE (для img2img подготовки). |
| scripts/test_vae_roundtrip.py | v1.1.0 | Тест VAE encode/decode roundtrip. |

### Утилиты (utils/)

| Модуль | Версия | Роль |
|--------|--------|------|
| utils/config.py | v1.1.0 | QSettings-обёртка с методами для Ollama, Diffusers, путей, истории, init_images. Миграция из старой версии OllamaChat. |
| get_context.sh | v1.2.1 | Точечная выгрузка файлов проекта для LLM (вместо полного full_context.py). |

---

## ПРИНЦИПЫ АРХИТЕКТУРЫ

| Принцип | Реализация | Выгода |
|---------|------------|--------|
| UI = View | Вкладки не делают requests/socket, только отрисовка и маршрутизация сигналов | Устранение UI-фризов, безопасность потоков |
| Ядро = Бизнес-логика | Чекпоинты, Ollama API, генерация вынесены в core/ | Переиспользование, изоляция багов |
| QProcess для тяжёлых задач | Diffusers запускается в отдельном процессе | Изоляция, возможность остановки, логирование |
| QThread для сетевых запросов | OllamaClient работает в отдельном потоке | Не блокирует UI |
| Сигнальная шина | pyqtSignal для навигации и передачи данных между вкладками | Слабая связность, безопасное переключение контекста |
| Единый конфиг | QSettings-обёртка (utils/config.py) | Централизованное управление настройками |
| Чекпоинты = атомарность | JSON + PT, архивация с timestamp | Защита от потери прогресса |
| История = воспроизводимость | Каждый шаг генерации сохраняется (PT + JSON) | Возможность экспериментов, сравнения, resume |
| Ресурсы = мониторинг | ResourceMonitor + ResourceManager, лимиты RAM/CPU | Предотвращение OOM, контроль нагрузки |
| Очистка = корректность | CleanupDialog с 5 шагами при закрытии | Освобождение памяти, остановка процессов |
| Свободное переключение табов | Табы не блокируются, блокируется только кнопка "Запустить" | UX: можно смотреть историю пока идёт генерация |
| Изоляция статусов | Каждый таб ведёт свой _bar_state, MainWindow не пишет в SharedBottomBar напрямую | Чистая архитектура, нет конфликтов |
| VAE в монолите | VAE работает внутри процесса генерации (не отдельный процесс) | Быстрее, нет конфликта за CPU affinity |
| Точный resume | Срез timesteps + компенсация init_noise_sigma | Картинка после resume идентична непрерывной генерации |

---

## КОНТРАКТЫ

### Данные
- Все настройки хранятся в QSettings через utils/config.py
- Чекпоинты: data/checkpoints/checkpoint.json (метаданные) + checkpoint.pt (latents, scheduler, generator)
- Архивные чекпоинты: data/checkpoints/YYYY-MM-DD_HH-MM-SS.json/.pt
- История генерации: data/history/{timestamp}/step_NNNN.pt + step_NNNN.json + metadata.json
- Логи: data/logs/diffusers_*.log, data/logs/ollama.log
- PID-файлы: data/pids/ollama.pid, data/pids/diffusers.pid
- Превью: data/previews/sdxl_{seed}_step{step:04d}.png (технические)
- Init images: data/init_images/ (подготовленные для img2img)
- Реестр моделей: data/models_registry.json

### Сеть
- Все запросы к Ollama API идут через core/ollama_client.py (QThread)
- Endpoint: http://127.0.0.1:11434/api/chat (стриминг токенов)
- Endpoint: http://127.0.0.1:11434/api/tags (список моделей)
- Endpoint: http://127.0.0.1:11434/api/generate (keep_alive=0 для выгрузки модели)
- Endpoint: http://127.0.0.1:11434/api/ps (проверка запущенных моделей)
- Timeout: настраивается через UI (по умолчанию 600с)
- Retry: нет (ошибки пробрасываются в UI)

### Конфигурация
- Все изменения в настройках проходят через utils/config.py (QSettings)
- Миграция из старой версии: QSettings("OllamaChat", "OllamaChat") → QSettings("LocalAILite", "LocalAILite")
- Пути: venv, модели, output, Ollama URL — валидируются через core/path_validator.py
- Ресурсы: max_ram_percent, cpu_cores, cpu_priority — применяются через core/resource_monitor.py

### Сигналы
- prompt_submitted(str) → MainWindow.on_prompt_submitted → активный таб.handle_prompt()
- generation_stopped() → активный таб.stop_generation()
- state_changed(dict) → MainWindow._on_tab_state_changed → обновление SharedBottomBar
- step_updated(int, int, str) → DiffusersTab._on_step_updated → обновление прогресса и превью
- generation_finished(str, int) → DiffusersTab._on_generation_finished → финальное изображение
- error_occurred(str) → DiffusersTab._on_error → статусная строка
- token_received(str) → OllamaTab.on_token → стриминг в ChatWidget
- stats_received(dict) → OllamaTab.on_stats → статистика (tokens/sec, duration)
- resource_acquired(str) → MainWindow._on_resource_acquired → блокировка кнопки "Запустить"
- resource_released() → MainWindow._on_resource_released → разблокировка кнопки

### Потоки
- OllamaClient работает в QThread (сетевые запросы)
- DiffusersWorker запускает QProcess (генерация изображений)
- CleanupThread работает в QThread (очистка ресурсов при закрытии)
- ResourceMonitor использует psutil (мониторинг RAM/CPU каждые 2 сек)
- Межпоточные вызовы UI → только через pyqtSignal

### Чекпоинты
- Сохранение: checkpoint_manager.save_checkpoint(latents, scheduler, generator, params, current_step, remaining_timesteps, actual_seed, last_preview_path)
- Загрузка активного: checkpoint_manager.load_checkpoint() → (json_data, torch_data)
- Загрузка архивного: checkpoint_manager.load_archived_checkpoint(filename) → (json_data, torch_data)
- Архивация: checkpoint_manager.archive_checkpoint() → переименование с timestamp
- Удаление: checkpoint_manager.delete_checkpoint() (после успешного завершения)
- Resume: scripts/generate_diffusers.py --resume --resume-history-dir {dir} --resume-step-file {file} --resume-start-step {N}

### История генерации
- Создание папки: history_manager.create_history_folder() → data/history/{timestamp}/
- Сохранение метаданных: history_manager.save_metadata(history_dir, params) → metadata.json
- Сохранение шага: history_manager.save_step_image(history_dir, step, image_path) → step_NNNN.png
- Список историй: history_manager.list_history() → [{"timestamp", "path", "display_name"}, ...]
- Удаление: history_manager.delete_history(history_dir)
- Размер: history_manager.get_history_size_mb(history_dir) → float

---

## ПУТИ И КОНФИГУРАЦИЯ

### Проект
- Точка входа: main.py
- Ядро: core/ (12 модулей)
- UI: ui/ (3 вкладки + SharedBottomBar + CleanupDialog + 3 диалога настроек)
- Скрипты: scripts/ (4 скрипта)
- Утилиты: utils/config.py, get_context.sh

### Данные (в gitignore)
- data/cache/ — кэш моделей HuggingFace
- data/checkpoints/ — чекпоинты (checkpoint.json/.pt + архив)
- data/history/ — история генерации: {timestamp}/step_NNNN.{pt,json} + metadata.json
- data/init_images/ — подготовленные изображения для img2img
- data/logs/ — логи diffusers_*.log и ollama.log
- data/ollama/ — данные Ollama (ключи, история)
- data/pids/ — PID-файлы (ollama.pid, diffusers.pid)
- data/previews/ — промежуточные PNG превью шагов (технические)

### Бинарники (в gitignore)
- bin/ollama/ — локальные бинарники Ollama + CUDA/Vulkan libs

### Конфигурация (QSettings)
- Организация: "LocalAILite"
- Приложение: "LocalAILite"
- Ключи:
  - url — Ollama URL (по умолчанию http://localhost:11434)
  - sdxl/venv_path — путь к venv для Diffusers
  - sdxl/models_path — путь к папке моделей
  - sdxl/output_dir — папка сохранения изображений
  - sdxl/scheduler — scheduler (по умолчанию EulerDiscreteScheduler)
  - sdxl/steps — количество шагов (по умолчанию 30)
  - sdxl/cfg — CFG scale (по умолчанию 7.5)
  - sdxl/device — устройство (cuda/cpu)
  - sdxl/no_safety_checker — отключение NSFW filter (true/false)
  - resources/max_ram_percent — максимум RAM (по умолчанию 80%)
  - resources/cpu_cores — количество ядер CPU (по умолчанию 3)
  - resources/cpu_priority — приоритет процесса (nice, по умолчанию 0)
  - image_prep/preset — индекс пресета разрешения
  - image_prep/crop_mode — режим обрезки (center/letterbox/stretch)
  - image_prep/last_path — последний путь к изображению
  - temperature, top_p, max_tokens, timeout, stream, system_prompt, model — настройки Ollama

---

## ТЕХНИЧЕСКИЙ СТЕК

- Python: 3.14
- GUI: PyQt6
- Сеть: requests (для Ollama API)
- Генерация: diffusers 0.39+, torch, torchvision, torchaudio
- Обработка изображений: Pillow
- Мониторинг: psutil
- Потоки: QThread (сеть), QProcess (генерация)
- Конфигурация: QSettings
- Git: ветка main (релизы). Коммиты: feat/fix/refactor/docs/chore

---

## МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ

| Показатель | Значение | Примечание |
|------------|----------|------------|
| Загрузка модели SDXL | ~10-15 сек | Single-file .safetensors, CUDA |
| Генерация 1024×1024 (30 шагов) | ~30-60 сек | Зависит от GPU |
| Чекпоинт (сохранение) | < 1 сек | JSON + PT, синхронная запись |
| Чекпоинт (загрузка) | ~2-3 сек | PT с latents + scheduler state |
| Ollama API (стриминг) | ~0.5-2 сек/токен | Зависит от модели и CPU/GPU |
| Мониторинг RAM/CPU | 2 сек | psutil.virtual_memory() + cpu_percent() |
| Очистка ресурсов (CleanupDialog) | ~3-5 сек | 5 шагов: Diffusers → Ollama модель → сервер → gc |

---

## ПЛАН РАЗВИТИЯ (ROADMAP)

### Высокий приоритет
- Экспорт чата в Markdown/PDF (история диалога с Ollama)
- Batch-генерация (несколько промптов подряд с разными параметрами)
- Слайдер просмотра истории (UI для листания шагов из data/history/{timestamp}/)
- Функция чистки истории (удаление старых генераций)

### Средний приоритет
- Блок 3: Чекпоинты img2img (поля init_image_path, strength, crop_mode в JSON, поддержка --init-image в скрипте)
- LoRA/Textual Inversion (поддержка дополнительных моделей для Diffusers)
- ControlNet (интеграция для управления позой/структурой)
- Upscaling (увеличение разрешения через ESRGAN/Real-ESRGAN)
- Темы оформления (светлая/тёмная, автоопределение через QPalette)

### Низкий приоритет
- Системный трей (сворачивание в трей при закрытии)
- Горячие клавиши (Ctrl+Enter для отправки, Esc для остановки)
- Плагины (расширяемость через внешние модули)
- Интеграция с HuggingFace Hub (поиск и скачивание моделей через UI)
- Автоматическое скачивание Ollama (через QThread + прогрессбар)

---

## БЫСТРЫЙ СТАРТ ДЛЯ НОВОГО ЧАТА

🔹 Проект: LocalAILite (Manjaro Linux, PyQt6, Python 3.14)
🔹 Ветка: main (GitHub: korbendallas000wt/LocalAILite)
🔹 Архитектура: Модульная, сигнальная маршрутизация, SRP, QProcess для генерации, QThread для сети
🔹 Ключевые файлы:
- main.py v1.2.0 (точка входа, валидация путей)
- ui/main_window.py v1.2.1 (оболочка, 3 вкладки, SharedBottomBar, OllamaManager)
- ui/tabs/ollama_tab.py v1.2.0 (чат, ChatWidget + SettingsPanel + OllamaClient)
- ui/tabs/diffusers_tab.py v1.2.1 (генерация, QGraphicsView + DiffusersWorker)
- ui/tabs/image_prep_tab.py v1.1.0 (Visual editor, превью + галерея + обработка)
- ui/shared_bottom_bar.py v1.2.0 (общая панель, промпт, прогресс, таймер, RAM/CPU, индикатор ресурса, единая кнопка)
- ui/cleanup_dialog.py v1.2.1 (очистка ресурсов, 5 шагов, kill по PID)
- core/ollama_client.py v1.0.0 (QThread-клиент к Ollama API)
- core/ollama_manager.py v1.2.0 (управление ollama serve, RAM/CPU limits)
- core/diffusers_worker.py v1.2.0 (QProcess-обёртка для generate_diffusers.py, RAM/CPU limits)
- core/checkpoint_manager.py v1.0.0 (чекпоинты: JSON + PT, архивация)
- core/history_manager.py v1.1.0 (история генерации: data/history/{timestamp}/)
- core/resource_manager.py v1.2.0 (управление ресурсом: 2 арендатора)
- core/resource_monitor.py v1.2.1 (мониторинг RAM/CPU, реальная проверка RAM, PID-методы)
- core/models_registry.py v1.2.0 (реестр моделей: красивое имя ↔ путь)
- core/image_processor.py v1.1.0 (обработка изображений)
- scripts/generate_diffusers.py v1.2.1 (CLI-генерация SDXL, точный resume, защита от перезаписи)
- scripts/compare_images.py v1.2.1 (попиксельное сравнение изображений)
- utils/config.py v1.1.0 (QSettings-обёртка)
- get_context.sh v1.2.1 (точечная выгрузка контекста для LLM)

🔹 Контракты:
- Данные: QSettings через utils/config.py, чекпоинты через core/checkpoint_manager.py, история через core/history_manager.py
- Сеть: Ollama API через core/ollama_client.py (QThread, timeout=600s)
- Генерация: scripts/generate_diffusers.py через core/diffusers_worker.py (QProcess)
- Ресурсы: core/resource_monitor.py (psutil, лимиты RAM/CPU)
- Сигналы: prompt_submitted(str) ↔ handle_prompt() | state_changed(dict) → SharedBottomBar | resource_acquired/released → блокировка кнопки
- Потоки: OllamaClient (QThread), DiffusersWorker (QProcess), CleanupThread (QThread)

🔹 Стиль работы:
- Отчёт → блоки документации → команды → «готово»
- Комментарии вне bash-блоков, команды копируются целиком
- Общение на «ты», режим «Тишина» по сигналу +тихо

---

## ЗАКЛЮЧЕНИЕ

Проект LocalAILite v1.2.1 — это стабильная производственная база с модульной архитектурой. Ключевые достижения:

- Полное разделение UI и бизнес-логики (SRP)
- Изоляция тяжёлых задач в QProcess (генерация) и QThread (сеть)
- Чекпоинты генерации с атомарной записью и архивацией
- История генерации: PT + JSON на каждом шаге
- Управление ресурсами: 2 арендатора (Ollama, Diffusers), только один генерирует одновременно
- Проверка RAM перед запуском (реальная, через psutil.virtual_memory), CPU affinity, nice-приоритет, env-переменные
- Общая нижняя панель (SharedBottomBar) для всех табов
- Корректная очистка ресурсов при закрытии (CleanupDialog, 5 шагов, kill по PID)
- Адаптация под нативную тему KDE без артефактов
- Адаптация под diffusers 0.39+ (callback_on_step_end)
- Синхронные чекпоинты (упрощение, надёжность)
- Свободное переключение табов (блокировка только на кнопке "Запустить")
- Цветовая подсветка статусов (серый, золотой, оранжевый, красный, зелёный)
- Изоляция статусов (каждый таб ведёт свой _bar_state)
- Единая кнопка действия (3 состояния: Генерация / Остановить / Завершение...)
- VAE в монолите (быстрее, нет конфликта за CPU affinity)
- Точный resume (срез timesteps + компенсация init_noise_sigma, картинка идентична непрерывной генерации)
- Защита от перезаписи PNG (счётчик sdxl_{seed}_N.png)
- Реестр моделей (красивое имя ↔ путь)
- Реалистичная оценка RAM для SDXL (9-11 GB)

Все модули изолированы, контракты зафиксированы, сигнальная шина отлажена. Код готов к ревью, слиянию в main и последующему развитию.
