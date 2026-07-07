
# История изменений — LocalAILite

Формат: [Keep a Changelog](https://keepachangelog.com/) | Версионирование: [SemVer](https://semver.org/)

## [1.0.0] — 2026-07-07

### Добавлено
- **main.py v1.0.0**: Точка входа приложения. QApplication, валидация путей через PathValidator, запуск MainWindow, диалог настройки путей при первом запуске.
- **ui/main_window.py v1.0.0**: Главное окно с QTabWidget (2 вкладки: Ollama Chat, Diffusers), SharedBottomBar, меню, OllamaManager, корректный closeEvent с CleanupDialog.
- **ui/tabs/ollama_tab.py v1.0.0**: Вкладка чата с Ollama. ChatWidget + SettingsPanel + OllamaClient (QThread), управление историей через ChatManager.
- **ui/tabs/diffusers_tab.py v1.0.0**: Вкладка генерации изображений. QGraphicsView для превью, DiffusersSettingsPanel, DiffusersWorker (QProcess), управление чекпоинтами.
- **ui/shared_bottom_bar.py v1.0.0**: Общая нижняя панель для обоих табов. Поле ввода промпта, прогрессбар, таймер, индикаторы RAM/CPU, статусная строка.
- **ui/cleanup_dialog.py v1.0.0**: Диалог освобождения ресурсов при закрытии (5 шагов): остановка Diffusers, выгрузка модели Ollama, стоп сервера, очистка памяти.
- **ui/chat_widget.py v1.0.0**: QTextBrowser с рендерингом Markdown, стриминг токенов, копирование кода по клику, контекстное меню.
- **ui/settings_panel.py v1.0.0**: Правая панель настроек Ollama (модель, temperature, top_p, max_tokens, timeout, stream, system_prompt).
- **ui/tabs/diffusers_settings_panel.py v1.0.0**: Настройки Diffusers (модель, scheduler, steps, cfg, size, seed, preview_every, preview_start, negative_prompt), список архивных чекпоинтов.
- **ui/dialogs/paths_dialog.py v1.0.0**: Стартовый диалог настройки путей (venv, модели, output, Ollama URL) с валидацией.
- **ui/dialogs/diffusers_models_dialog.py v1.0.0**: Диалог управления моделями Diffusers (список, удаление, открытие папки, ссылки на ресурсы).
- **ui/dialogs/settings/settings_dialog.py v1.0.0**: Окно настроек с вкладками (Общие, Diffusers, Ресурсы).
- **ui/dialogs/settings/paths_settings_widget.py v1.0.0**: Вкладка настроек путей с валидацией в реальном времени.
- **ui/dialogs/settings/diffusers_settings_widget.py v1.0.0**: Вкладка настроек Diffusers (device, safety_checker, управление моделями).
- **ui/dialogs/settings/resources_settings_widget.py v1.0.0**: Вкладка настроек ресурсов (max_ram_percent, cpu_cores, cpu_priority).
- **core/chat_manager.py v1.0.0**: История чата (messages list), добавление/получение сообщений, экспорт в Markdown.
- **core/ollama_client.py v1.0.0**: QThread-клиент к Ollama API (/api/chat), стриминг токенов, извлечение статистики (tokens/sec, duration).
- **core/ollama_manager.py v1.0.0**: Управление процессом ollama serve (старт/стоп), проверка порта 11434, обработка конфликтов, логирование, PID-файлы.
- **core/diffusers_worker.py v1.0.0**: QProcess-обёртка для scripts/generate_diffusers.py, парсинг JSON-вывода, логирование, сигналы (step_updated, generation_finished, error_occurred).
- **core/checkpoint_manager.py v1.0.0**: Менеджер чекпоинтов генерации. Сохранение latents + scheduler + generator в PT, метаданные в JSON, архивация с timestamp, загрузка из архива.
- **core/resource_manager.py v1.0.0**: Переключение табов + выгрузка неактивных модулей (вызов unload()).
- **core/resource_monitor.py v1.0.0**: Мониторинг RAM/CPU через psutil, оценка потребления для Diffusers/Ollama, применение лимитов (cpu_affinity, priority, env).
- **core/path_validator.py v1.0.0**: Валидация путей (venv, модели, output, Ollama URL), проверка доступности, подсчёт моделей.
- **core/markdown_parser.py v1.0.0**: Парсер Markdown в HTML с адаптацией под системную тему KDE, подсветка кода, кнопки копирования, обработка ссылок, списков, заголовков.
- **scripts/generate_diffusers.py v1.0.0**: CLI-скрипт генерации SDXL. Поддержка single-file моделей, HF-формата, resume из чекпоинта, callback для прогресса, сохранение превью.
- **utils/config.py v1.0.0**: QSettings-обёртка с методами для Ollama, Diffusers, путей. Миграция из старой версии OllamaChat.
- **Модульная архитектура**: SRP, сигнальная маршрутизация, изолированные потоки (QThread для сети, QProcess для тяжёлых задач).
- **Чекпоинты генерации**: Сохранение/восстановление прогресса (latents + scheduler + generator), архивация с timestamp.
- **Управление ресурсами**: Мониторинг RAM/CPU, лимиты, выгрузка неактивных модулей при переключении табов.
- **Ollama Manager**: Автоматический запуск/остановка сервера, обработка конфликтов портов, логирование.
- **SharedBottomBar**: Единая нижняя панель для обоих табов (промпт, прогресс, таймер, RAM/CPU).
- **CleanupDialog**: Корректное освобождение ресурсов при закрытии (5 шагов).
- **Markdown-парсер**: Подсветка кода, копирование блоков, адаптация под системную тему KDE.
- **Нативная тема KDE**: Без артефактов, адаптивный UI.

### Изменено
- **Архитектура**: Полное разделение UI и бизнес-логики. UI-модули только отрисовка и маршрутизация сигналов, вся логика в core/.
- **Потоки данных**: Чат через OllamaClient (QThread), генерация через DiffusersWorker (QProcess), изоляция от UI-потока.
- **Конфигурация**: Единый QSettings-обёртка (utils/config.py) для всех настроек.
- **Чекпоинты**: Атомарная запись JSON + PT, архивация с timestamp для истории.

### Исправлено
- Устранены UI-фризы за счёт выноса сетевых запросов в QThread.
- Изоляция тяжёлых задач (генерация) в QProcess для возможности остановки и логирования.
- Корректная очистка ресурсов при закрытии через CleanupDialog.
- Адаптация под нативную тему KDE без артефактов.

---

## [0.1.0-dev] — 2026-07-01

### Добавлено
- Начальная структура проекта
- Базовые модули: chat_manager, ollama_client, diffusers_worker
- Прототип UI на PyQt6
- Скрипт generate_diffusers.py для CLI-генерации

### Изменено
- Переход от монолита к модульной архитектуре
- Вынос логики в core/

---

## [0.0.1] — 2026-06-28

### Добавлено
- Инициализация репозитория
- Базовый README.md
- Структура папок
