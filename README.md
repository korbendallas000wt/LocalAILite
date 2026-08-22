# LocalAILite — Локальный AI-ассистент

Приложение для работы с локальными AI-моделями: чат с Ollama + генерация изображений (SDXL/Diffusers) + визуальный редактор.

**Платформа:** Linux (Manjaro/Arch, Fedora, Debian, openSUSE, Ubuntu), PyQt6, Python 3.10-3.12

---

## 🪶 Почему LocalAILite

Мы верим: **локальные нейросети — не роскошь для владельцев мощных GPU.** Чат с LLM и генерация изображений доступны даже на слабом железе — если подойти к делу с умом.

- 🏠 **Всё своё, дома** — модели живут на вашей машине. Без подписок, лимитов токенов и чужих серверов.
- ✈ **Работает офлайн** — отключили интернет, а вы продолжаете и чат, и генерацию.
- 🔒 **Приватность по умолчанию** — промпты, диалоги и картинки не покидают ваш компьютер.
- ⏸ **Чекпоинты на каждом шаге** — генерацию можно прервать и продолжить точно с того же места, байт в байт.
- 💾 **Чаты сохраняются** — продолжайте отложенный диалог с точными настройками, редактируйте и экспериментируйте.
- 🐢→🚀 **Масштабируется** — на слабом железе работает, на мощном — ускоряется.

Подробнее о философии проекта — в [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md).

---

## 🧩 Статус модулей

### Оболочка и UI

| Модуль | Версия | Роль |
|--------|--------|------|
| main.py | v1.2.0 | Точка входа: QApplication, валидация путей, запуск MainWindow |
| ui/main_window.py | v1.2.1 | Главное окно: 3 вкладки, меню, OllamaManager, SharedBottomBar |
| ui/shared_bottom_bar.py | v1.4.0 | Общая нижняя панель: промпт, прогресс, таймер, RAM/CPU, единая кнопка |
| ui/chat_widget.py | v1.2.0 | Append-only просмотрщик HTML-блоков + копирование кода + загрузка чатов |
| ui/chat_control_panel.py | v1.0.0 | Панель управления чатом: Новый, Отменить, Файл, Сохранить |
| ui/settings_panel.py | v1.2.0 | Правая панель Ollama: настройки + режимы (Новый/Продолжить/Изменить) |
| ui/cleanup_dialog.py | v1.2.1 | Диалог освобождения ресурсов при закрытии |
| ui/dialogs/settings/chat_settings_widget.py | v1.0.0 | Вкладка "Чат": формат сохранения, папка, автоназвание |
| ui/dialogs/settings/update_settings_widget.py | v1.5.0 | Вкладка "Обновления": версии, CHANGELOG, установка |

### Вкладки

| Модуль | Версия | Роль |
|--------|--------|------|
| ui/tabs/ollama_tab.py | v1.4.0 | Чат: режимы работы, сохранение/загрузка чатов |
| ui/tabs/diffusers_tab.py | v1.2.1 | Генерация: чекпоинты, история, режимы |
| ui/tabs/diffusers_settings_panel.py | v1.4.0 | Настройки Diffusers + реестр моделей + чекпоинты |
| ui/tabs/image_prep_tab.py | v1.1.0 | Visual editor: превью + галерея + обработка |
| ui/tabs/image_prep_panel.py | v1.1.0 | Правая панель Visual editor |

### Ядро (core/)

| Модуль | Версия | Роль |
|--------|--------|------|
| core/chat_manager.py | v1.1.0 | История чата (messages list), загрузка из JSON |
| core/chat_exporter.py | v1.0.0 | Экспорт чатов в JSON (для машины) и TXT (для человека) |
| core/ollama_client.py | v1.0.0 | QThread-клиент к Ollama API (/api/chat), стриминг токенов |
| core/ollama_manager.py | v1.2.0 | Управление ollama serve, конфликты портов, TIME_WAIT |
| core/diffusers_worker.py | v1.2.0 | QProcess-обёртка для generate_diffusers.py, проверка RAM |
| core/checkpoint_manager.py | v1.0.0 | Чекпоинты: JSON + PT, архивация с timestamp |
| core/history_manager.py | v1.1.0 | Менеджер истории: data/diffusers/history/{timestamp}/ |
| core/resource_manager.py | v1.2.0 | Управление ресурсом: acquire/release, 2 арендатора |
| core/resource_monitor.py | v1.2.1 | Мониторинг RAM/CPU, лимиты, CPU affinity, PID |
| core/image_processor.py | v1.1.0 | Обработка изображений: resize, crop |
| core/path_validator.py | v1.1.0 | Валидация: venv, модели, output, Ollama |
| core/paths_manager.py | v1.4.0 | Единый модуль управления путями (дефолты, валидация) |
| core/models_registry.py | v1.4.0 | Реестр моделей: короткое имя ↔ {path, full_name, type} |
| core/markdown_parser.py | v1.2.0 | Markdown в HTML: таблицы, вложенные списки, системная тема |
| core/model_validator.py | v1.0.0 | Проверка целостности моделей (HF cache, single-file, Ollama) |
| core/package_validator.py | v1.0.0 | Проверка пакетов venv (баг #15: numpy) |
| core/updater.py | v2.0 | Модуль обновлений: проверка + скачивание + установка |

### Скрипты (scripts/)

| Модуль | Версия | Роль |
|--------|--------|------|
| scripts/generate_diffusers.py | v1.2.1 | CLI-генерация SDXL: чекпоинты, точный resume |
| scripts/compare_images.py | v1.2.1 | Попиксельное сравнение изображений (для проверки точности) |
| scripts/encode_image.py | v1.1.0 | Кодирование изображения в latents через VAE |
| scripts/test_vae_roundtrip.py | v1.1.0 | Тест VAE encode/decode roundtrip |

### Инсталлятор (installer/)

| Модуль | Версия | Роль |
|--------|--------|------|
| installer/cli.py | v1.4.0 | Точка входа: `python3 installer/cli.py`. Идемпотентен |
| installer/detector.py | v1.3.0 | Диагностика железа: ОС, CPU, RAM, GPU, Python, диск |
| installer/requirements.py | v1.3.0 | Пороги ресурсов для вердиктов советника |
| installer/advisor.py | v1.3.0 | Честные вердикты: что потянет машина, подбор моделей |
| installer/config.json | v1.0.0 | Конфигурация инсталлера (URL, пути, пакеты) |
| installer/config_loader.py | v1.0.0 | Загрузка и валидация config.json |
| installer/final_check.py | v1.0.0 | Глубокие проверки: SDXL env, модели, Ollama |
| installer/steps/ | v1.4.0 | Идемпотентные шаги установки (7 шагов) |
| install.sh | v1.0.0 | Удобная точка входа (проверка Python + запуск cli.py) |

---

## 📁 Структура проекта

    LocalAILite/
    ├── main.py                              # Точка входа
    ├── install.sh                           # Удобная точка входа инсталлера
    ├── LocalAILite                          # Исполняемая обёртка
    ├── LocalAILite.desktop                  # Ярлык для меню
    ├── README.md                            # Этот файл
    │
    ├── docs/                                # Документация
    │   ├── START_HERE.md                    # Точка входа для разработчиков
    │   ├── STRUCTURE.md                     # Структура + raw-ссылки
    │   ├── WORKLOG.md                       # Журнал разработки
    │   ├── CHANGELOG.md                     # История версий
    │   ├── PROJECT_MANIFEST.md              # Контракты и архитектура
    │   └── PHILOSOPHY.md                    # Философия проекта
    │
    ├── core/                                # Ядро (логика без UI)
    │   ├── chat_manager.py                  # История чата
    │   ├── chat_exporter.py                 # Экспорт чатов (JSON + TXT)
    │   ├── ollama_client.py                 # QThread-клиент к Ollama API
    │   ├── ollama_manager.py                # Управление ollama serve
    │   ├── markdown_parser.py               # Markdown в HTML
    │   ├── checkpoint_manager.py            # Чекпоинты генерации
    │   ├── diffusers_worker.py              # QProcess для генерации
    │   ├── history_manager.py               # Менеджер истории
    │   ├── resource_manager.py              # Управление ресурсом
    │   ├── resource_monitor.py              # Мониторинг RAM/CPU
    │   ├── image_processor.py               # Обработка изображений
    │   ├── path_validator.py                # Валидация путей
    │   ├── paths_manager.py                 # Единый модуль путей
    │   ├── models_registry.py               # Реестр моделей
    │   ├── model_validator.py               # Проверка целостности
    │   ├── package_validator.py             # Проверка пакетов venv
    │   └── updater.py                       # Модуль обновлений
    │
    ├── scripts/                             # CLI-скрипты (в venv)
    │   ├── generate_diffusers.py            # Генерация SDXL
    │   ├── compare_images.py                # Сравнение изображений
    │   ├── encode_image.py                  # Кодирование в latents
    │   └── test_vae_roundtrip.py            # Тест VAE
    │
    ├── ui/                                  # PyQt6 интерфейс
    │   ├── main_window.py                   # Главное окно (3 вкладки)
    │   ├── chat_widget.py                   # Append-only чат
    │   ├── chat_control_panel.py            # Панель управления чатом
    │   ├── settings_panel.py                # Панель настроек Ollama
    │   ├── shared_bottom_bar.py             # Общая нижняя панель
    │   ├── cleanup_dialog.py                # Диалог очистки ресурсов
    │   ├── dialogs/
    │   │   ├── paths_dialog.py              # Стартовый диалог путей
    │   │   ├── diffusers_models_dialog.py   # Управление моделями
    │   │   ├── history_save_dialog.py       # Сохранение истории
    │   │   └── settings/
    │   │       ├── settings_dialog.py       # Окно настроек
    │   │       ├── paths_settings_widget.py
    │   │       ├── chat_settings_widget.py  # Вкладка Чат
    │   │       ├── diffusers_settings_widget.py
    │   │       ├── resources_settings_widget.py
    │   │       └── update_settings_widget.py
    │   └── tabs/
    │       ├── ollama_tab.py                # Чат
    │       ├── diffusers_tab.py             # Генерация
    │       ├── diffusers_settings_panel.py  # Настройки Diffusers
    │       ├── image_prep_tab.py            # Visual editor
    │       └── image_prep_panel.py          # Панель Visual editor
    │
    ├── utils/
    │   └── config.py                        # JSON-конфиг + пути
    │
    ├── installer/                           # Инсталлятор
    │   ├── cli.py                           # Точка входа
    │   ├── detector.py                      # Диагностика железа
    │   ├── requirements.py                  # Пороги ресурсов
    │   ├── advisor.py                       # Вердикты
    │   ├── config.json                      # Конфигурация
    │   ├── config_loader.py                 # Загрузка конфигурации
    │   ├── final_check.py                   # Глубокие проверки
    │   └── steps/                           # Идемпотентные шаги
    │
    ├── Repo/                                # Зеркало main (стабильная)
    ├── WORK/                                # Локальные файлы (gitignore)
    │
    └── data/                                # Рабочие данные (gitignore)
        ├── ollama/
        │   ├── models/                      # Модели Ollama
        │   └── chats/                       # Сохранённые чаты
        ├── diffusers/
        │   ├── history/                     # История генерации
        │   ├── init_images/                 # Изображения для img2img
        │   ├── models/                      # Модели SDXL
        │   └── previews/                    # Превью
        ├── image_prep/
        │   └── presets/                     # Пресеты редактора
        └── shared/
            ├── config/                      # local_config.json
            ├── registry/                    # Реестры моделей
            ├── logs/                        # Логи
            └── pids/                        # PID-файлы

---

## 🛠 Запуск

### Установка через инсталлятор

    python3 installer/cli.py

Инсталлятор последовательно выполняет 8 шагов:

**Уровень 1 — бутстрап** (минимум для запуска):
- Детектирует железо и честно скажет, что потянет машина
- Создаст служебную структуру `data/`
- Создаст venv и установит зависимости

**Уровень 2 — полная установка** (компоненты и модели):
- Настроит пути к компонентам
- Скачает бинарник Ollama (~2.1 GB)
- Создаст SDXL venv с torch/diffusers (~6 GB)
- Скачает рекомендованные модели

Идемпотентен: повторный запуск пропустит уже установленное.

### Запуск приложения

    python main.py

Или через ярлык `LocalAILite` в меню приложений.

---

## 🔄 Обновление приложения

Встроенный модуль обновлений:
- Автоматическая проверка версий при запуске
- Уведомление в статусбаре + точка в меню "Настройки"
- Вкладка "Обновления" в настройках с CHANGELOG и кнопкой установки
- Скачивание и замена файлов из ветки `main`

---

## 📊 Ключевые возможности

### 💬 Чат с Ollama
- **Сохранение и загрузка чатов** — экспорт в JSON (для машины) и TXT (для человека)
- **Режимы работы** — Новый, Продолжить (с оригинальными настройками), Изменить (свободные настройки)
- **Панель управления** — Новый чат, Отменить, Файл, Сохранить
- **Автоназвание чатов** — генерация заголовка через LLM
- **Таблицы и вложенные списки** — полная поддержка в markdown
- **Копирование кода и ответов** — контекстное меню + кнопки
- **Модульная архитектура** — OllamaClient в QThread, не блокирует UI

### 🎨 Генерация изображений (SDXL)
- **Чекпоинты на каждом шаге** — сохранение/восстановление прогресса
- **Точный resume** — продолжение с того же места, байт в байт
- **История генерации** — PNG + PT + JSON на каждом шаге
- **Реестр моделей** — короткие имена, типы
- **Режимы** — Создать, Продолжить (из чекпоинта), Изменить (img2img)

### 🖼️ Визуальный редактор
- Подготовка изображений для img2img
- Resize, crop (center/letterbox/stretch)
- Пресеты обработки

### ⚙️ Система
- **Модуль обновлений** — автоматическая проверка, скачивание, установка
- **Управление ресурсами** — один модуль генерирует одновременно
- **Ollama Manager** — автозапуск/остановка, обработка конфликтов
- **Единая нижняя панель** — промпт, прогресс, таймер, статусы
- **Корректное завершение** — диалог очистки ресурсов

---

## 📈 Архитектурные принципы

| Принцип | Реализация | Выгода |
|---------|------------|--------|
| **UI = View** | Вкладки не делают requests, только отрисовка | Устранение фризов |
| **Ядро = Бизнес-логика** | API, генерация вынесены в core/ | Переиспользование |
| **Append-only рендеринг** | Чат добавляет блоки, не перерисовывает | Производительность |
| **Идемпотентность** | Повторный запуск чинит проблемы | Надёжность |
| **Сигнальная шина** | pyqtSignal для навигации | Слабая связность |
| **Единый конфиг** | JSON + QSettings | Централизация |
| **Изоляция табов** | Каждый таб ведёт свой статус | Чистая архитектура |

---

## 📜 Лицензия

MIT
