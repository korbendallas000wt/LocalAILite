Отличная идея, Корбен! 🎯 Контекст действительно раздулся, пора передавать эстафету новой инкарнации. Подготовлю файл `HANDOFF_NEXT_CHAT.md` с полным контекстом — проблемами, достижениями и планами.

Сначала изучу текущее состояние ключевых файлов, чтобы не опираться только на память:


Корбен, держусь на энтузиазме! 😅 Спасибо за добрые слова — это было продуктивное путешествие!

Попробую создать HANDOFF документ через bash:

```bash
cd /home/lin/Scripts/LocalAILite && cat > HANDOFF_NEXT_CHAT.md << 'EOF'
# HANDOFF_NEXT_CHAT.md - Контекст для следующего чата
Создано: 2026-08-07
Проект: LocalAILite (Manjaro Linux, PyQt6, Python 3.14)

## 📋 ИТОГО ДОСТИГНУТО В ЭТОМ ЧАТЕ

### 1. Интерактивный выбор путей в инсталляторе ✅
**Файл:** `installer/steps/step_paths.py`
- Переписан `choose_paths_interactive()` - интерактивный выбор путей в CLI
- Показывает: дефолт, требуемый объём, свободное место на диске
- Пользователь может оставить дефолт (Enter) или указать свой путь
- Предупреждает о нехватке места
- Записывает выбранные пути в QSettings через `utils/config.py`

### 2. Доработка шагов инсталлятора ✅
Все шаги теперь читают пути из Config, а не используют жёстко заданные пути:

**`installer/steps/step_ollama.py`:**
- Добавлен `_get_paths()` - читает `ollama/binary_path` и `ollama/lib_path` из Config
- Fallback на дефолты из `step_paths` если в Config нет
- Использует `_read_config_value()` для чтения QSettings через venv python

**`installer/steps/step_sdxl_env.py`:**
- Добавлен `_get_paths()` - читает `sdxl/venv_path` из Config
- Валидация: если `python_path` не существует - fallback на дефолт
- Динамический выбор `--index-url` для torch: CUDA (cu121) если NVIDIA+CUDA, иначе CPU

**`installer/steps/step_models.py`:**
- Добавлен `_get_paths()` - читает `sdxl/models_path` и `ollama/models_path` из Config
- Передаёт `OLLAMA_MODELS` env при вызове `ollama list` и `ollama pull`
- Использует рекомендации из `advisor.recommend_models()` для выбора моделей
- Оценивает размер моделей по имени (0.5B→0.5GB, 3B→2GB, 7B→5GB)

### 3. Централизация управления путями ✅
**Новый файл:** `core/paths_manager.py`
- **PathsManager** - единый источник дефолтов, размеров, названий
- `KEYS` - словарь QSettings-ключей (ollama_binary, ollama_lib, ollama_models, sdxl_venv, sdxl_models, sdxl_output, ollama_url)
- `SIZES` - размеры компонентов (GB): ollama_binary=2.1, ollama_models=4.5, sdxl_venv=6.0, sdxl_models=6.5, sdxl_output=0.5
- `LABELS` - человекочитаемые названия для UI
- `get_defaults()` - дефолтные пути (всё в папке проекта для пассивного пользователя)
- `get_paths(config)` - актуальные пути из Config с fallback на дефолты + нормализация
- `get_path(config, name)` - один путь с fallback + нормализация
- `validate_all(config)` - валидация всех путей через PathValidator с учётом features/* и критичности
- `step_paths.py` использует PathsManager для дефолтов (убрано дублирование)

### 4. Расширение валидации путей ✅
**Файл:** `core/path_validator.py`

**Новые методы:**
- `validate_ollama_binary(path)` - проверка бинарника Ollama
  - Учитывает системный бинарник (`shutil.which("ollama")`) если путь не задан
  - Проверяет существование, права на исполнение, запуск с `--version`
  
- `validate_ollama_models_path(path)` - проверка папки моделей Ollama
  - Папка может быть пустой (модели ещё не скачаны) - это не ошибка
  - Считает модели в `manifests/registry.ollama.ai/library/`

**Расширенные методы:**
- `validate_all(config)` - добавлены ollama_binary (критичен) и ollama_models (не критичен)
- `validate_installed(config)` - добавлены ollama_binary (критичен) и ollama_models (не критичен)

### 5. Интеграция новых путей в UI ✅

**`ui/dialogs/settings/paths_settings_widget.py`:**
- Добавлены два новых поля в группе "Ollama":
  - `ollama_bin_edit` - путь к бинарнику (с кнопкой 📁 для выбора файла)
  - `ollama_models_edit` - путь к папке моделей (с кнопкой 📁 для выбора папки)
- Валидация в реальном времени через `PathValidator`
- Индикаторы ✅/❌ для каждого поля
- Автозакрытие диалога если все поля валидны (сигнал `all_valid`)

**`ui/dialogs/paths_dialog.py`:**
- Аналогичные изменения: добавлены `ollama_bin_edit` и `ollama_models_edit`
- Кнопка "Проверить всё" для ручной валидации
- Умное автоподключение к Ollama (5 попыток с интервалом 1 сек)

**`ui/dialogs/settings/settings_dialog.py`:**
- Расширена валидация в `_on_accept()` - проверяет ollama_binary (критичен)
- Показывает предупреждение если есть проблемы

**`ui/main_window.py`:**
- Расширен `_update_status()` - показывает ошибки новых путей в статусной строке
- Добавлены два метода перезагрузки путей:
  - `_reload_paths_light()` - лёгкая: обновить реестр моделей + перезапустить Ollama
  - `_reload_paths_full()` - полная: выгрузить модели + очистить память + перезапустить Ollama
- Добавлен `_restart_ollama_after_cleanup()` - надёжный перезапуск Ollama после очистки
  - Ждёт освобождения порта (до 5 сек)
  - Fallback на `kill_existing_and_start()` если порт не освободился

### 6. Синхронизация дефолтов ✅
**Проблема:** В `ollama_manager.py` был захардкожен личный путь `/run/media/lin/DATA/Program Files/Ollama/`

**Решение:**
- Убран захардкоженный дефолт
- Теперь используется `PathsManager.get_path(config, "ollama_models")`
- Дефолт в PathsManager: `{project}/data/ollama_models` (универсально)
- Пользователь может изменить путь в настройках приложения

### 7. Философия путей ✅
- **Пассивный пользователь** - всё в папке проекта (дефолты из PathsManager)
- **Активный пользователь** - выбирает свои пути через:
  - Интерактивный выбор в CLI-инсталляторе (`step_paths`)
  - Настройки приложения (`paths_settings_widget`)
  - Стартовый диалог при первом запуске (`paths_dialog`)

---

## 🔴 ТЕКУЩИЕ ПРОБЛЕМЫ (НЕ ДОДЕЛАНО)

### Проблема 1: Перезапуск Ollama после диалога очистки не работает ❌
**Симптом:** Пользователь меняет путь к моделям Ollama в настройках, нажимает OK, выбирает "Перезагрузить сейчас" - появляется диалог очистки, но после него Ollama не перезапускается с новыми путями.

**Что сделано:**
- Добавлен `_reload_paths_full()` в MainWindow
- Добавлен `_restart_ollama_after_cleanup()` с ожиданием порта и fallback

**Что не работает:**
- После `cleanup_dialog.exec()` вызывается `QTimer.singleShot(500, self.ollama_manager.start)`
- Но `start()` может эмитить `conflict_detected` если порт не освободился
- Возможно, CleanupDialog не останавливает Ollama корректно (межпоточный вызов из QThread)

**Что нужно исследовать:**
1. Проверить, действительно ли CleanupDialog останавливает Ollama (шаг 3)
2. Проверить, освобождается ли порт 11434 после остановки
3. Возможно, нужен другой механизм:
   - Флаг `restart_ollama=True` в CleanupDialog
   - Сигнал `ollama_restart_needed` из CleanupThread
   - MainWindow подключает сигнал к перезапуску в основном потоке

**Файлы:** `ui/main_window.py`, `ui/cleanup_dialog.py`

### Проблема 2: Выгрузка модели при смене в ComboBox ❌
**Симптом:** Пользователь меняет модель в `SettingsPanel` (правая панель Ollama-чата), но старая модель остаётся в памяти Ollama. RAM занята, ответы идут от старой модели.

**Что сделано:**
- Проанализирован код `ollama_tab.py` и `settings_panel.py`

**Что нужно сделать:**
1. Добавить `_last_loaded_model` в OllamaTab для отслеживания реально загруженной модели
2. В `handle_prompt()` запоминать модель после отправки запроса
3. Добавить `_unload_model(model_name)` - выгрузка через API (`keep_alive=0`)
4. Подключить `model_combo.currentTextChanged` → `_on_model_changed`
5. В `_on_model_changed` выгружать старую модель если она была загружена
6. Обновить `unload()` - выгружать `_last_loaded_model` вместо `model_combo.currentText()`

**Файлы:** `ui/tabs/ollama_tab.py`, `ui/settings_panel.py`

### Проблема 3: Дублирование `_get_paths()` в шагах инсталлятора ⚠️
**Симптом:** `step_ollama.py`, `step_sdxl_env.py`, `step_models.py` имеют свои `_get_paths()` вместо использования `PathsManager`.

**Что нужно сделать:**
1. Убрать `_get_paths()` из каждого шага
2. Использовать `PathsManager.get_paths(config)` напрямую
3. Проверить, что все шаги работают корректно после рефакторинга

**Файлы:** `installer/steps/step_ollama.py`, `installer/steps/step_sdxl_env.py`, `installer/steps/step_models.py`

### Проблема 4: Централизация валидации ⚠️
**Симптом:** `main.py` использует `PathValidator.validate_installed()`, а не `PathsManager.validate_all()`. Есть дублирование логики.

**Что нужно сделать:**
1. Переключить `main.py` на `PathsManager.validate_all(config)`
2. Убрать или упростить `PathValidator.validate_installed()`
3. Убедиться, что логика критичности путей одинаковая

**Файлы:** `main.py`, `core/paths_manager.py`, `core/path_validator.py`

---

## 📋 ПЛАН ДЕЙСТВИЙ ДЛЯ СЛЕДУЮЩЕГО ЧАТА

### Приоритет 1 (критично): Починить перезапуск Ollama
**Цель:** После смены путей в настройках и выбора "Перезагрузить сейчас" - Ollama должен перезапуститься с новыми путями.

**Шаги:**
1. Добавить логирование в `_reload_paths_full()` и `_restart_ollama_after_cleanup()`
2. Проверить, вызывается ли `cleanup_dialog.exec()` корректно
3. Проверить, останавливается ли Ollama в CleanupThread (шаг 3)
4. Проверить, освобождается ли порт 11434
5. Если порт не освобождается - увеличить задержку или использовать `kill_existing_and_start()`
6. Если проблема в межпоточном вызове - использовать сигнал вместо прямого вызова

**Тест:**
1. Запустить приложение
2. Открыть настройки → изменить путь к моделям Ollama
3. Нажать OK → выбрать "Перезагрузить сейчас"
4. Проверить, что Ollama перезапустился (в логах)
5. Проверить, что используется новый путь (`OLLAMA_MODELS` env)

### Приоритет 2 (важно): Выгрузка модели при смене
**Цель:** При смене модели в ComboBox - старая модель выгружается из памяти Ollama.

**Шаги:**
1. Добавить `_last_loaded_model` в OllamaTab
2. В `handle_prompt()` запоминать модель
3. Добавить `_unload_model(model_name)`
4. Подключить `model_combo.currentTextChanged`
5. Обновить `unload()`

**Тест:**
1. Запустить чат с моделью A
2. Отправить запрос (модель A загружается)
3. Сменить модель на B в ComboBox
4. Проверить, что модель A выгрузилась (через `ollama ps`)
5. Отправить запрос (модель B загружается)

### Приоритет 3 (рефакторинг): Убрать дублирование `_get_paths()`
**Цель:** Все шаги инсталлятора используют `PathsManager` напрямую.

**Шаги:**
1. Рефакторинг `step_ollama.py` - убрать `_get_paths()`, использовать `PathsManager`
2. Рефакторинг `step_sdxl_env.py` - убрать `_get_paths()`, использовать `PathsManager`
3. Рефакторинг `step_models.py` - убрать `_get_paths()`, использовать `PathsManager`
4. Тестирование всех шагов

### Приоритет 4 (рефакторинг): Централизация валидации
**Цель:** `main.py` использует `PathsManager.validate_all()`.

**Шаги:**
1. Переключить `main.py` на `PathsManager.validate_all(config)`
2. Убрать или упростить `PathValidator.validate_installed()`
3. Тестирование запуска приложения

---

## 🏗️ АРХИТЕКТУРНЫЕ РЕШЕНИЯ

### Единый источник правды для путей
- **PathsManager** (`core/paths_manager.py`) - дефолты, размеры, названия
- **PathValidator** (`core/path_validator.py`) - валидация
- **Config** (`utils/config.py`) - чтение/запись в QSettings

### Дефолтные пути (для пассивного пользователя)
```python
{
    "ollama_binary": "{project}/bin/ollama/bin/ollama",
    "ollama_lib": "{project}/bin/ollama/lib/ollama",
    "ollama_models": "{project}/data/ollama_models",
    "sdxl_venv": "{project}/venv_sdxl",
    "sdxl_models": "{project}/data/models",
    "sdxl_output": "~/Pictures/LocalAILite",
    "ollama_url": "http://localhost:11434"
}
```

### Критичность путей
- **Критичные** (блокируют запуск): ollama_binary, sdxl_venv, sdxl_models, sdxl_output
- **Не критичные** (предупреждают): ollama_models (модели могут быть ещё не скачаны), ollama_url (сервер запускается автоматически)

### Размеры компонентов (GB)
- ollama_binary: 2.1 GB
- ollama_models: 4.5 GB
- sdxl_venv: 6.0 GB
- sdxl_models: 6.5 GB
- sdxl_output: 0.5 GB
- **Всего:** ~19.6 GB

### Два уровня инсталлятора
1. **CLI-бутстрап** (уровень 1) - `installer/cli.py`
   - Создаёт venv, устанавливает PyQt6
   - Без PyQt (чистый Python)
   - Идемпотентен
   
2. **UI-визард** (уровень 2) - `step_paths.py`, `step_ollama.py`, `step_sdxl_env.py`, `step_models.py`
   - После создания venv
   - С PyQt (может использовать виджеты)
   - Интерактивный выбор путей и моделей

### ResourceManager
- 2 арендатора: Ollama, Diffusers
- Только один может генерировать одновременно
- Кнопка "Запустить" блокируется при занятом ресурсе
- Табы переключаются свободно (генерация продолжается в фоне)

### CleanupDialog
- 5 шагов очистки при закрытии приложения
- Остановка Diffusers (включая kill по PID)
- Выгрузка модели Ollama через API (`keep_alive=0`)
- Остановка Ollama-сервера (только если наш процесс)
- Очистка памяти (`gc.collect()`)

---

## 🔧 ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Стек технологий
- **Платформа:** Manjaro Linux
- **GUI:** PyQt6
- **Python:** 3.14
- **Генерация:** diffusers 0.39+, torch, torchvision, torchaudio
- **Мониторинг:** psutil
- **Конфигурация:** QSettings

### Ключи QSettings
```python
{
    "ollama/binary_path": "Путь к бинарнику Ollama",
    "ollama/lib_path": "Путь к библиотекам Ollama",
    "ollama/models_path": "Путь к папке моделей Ollama",
    "sdxl/venv_path": "Путь к SDXL venv (torch/diffusers)",
    "sdxl/models_path": "Путь к папке моделей SDXL",
    "sdxl/output_dir": "Папка выходных изображений",
    "url": "URL Ollama сервера",
    "features/ollama": "Флаг компонента Ollama",
    "features/sdxl": "Флаг компонента SDXL",
    "features/image_prep": "Флаг компонента Image Prep"
}
```

### Сигналы PyQt
- `PathsSettingsWidget.all_valid` - все пути валидны (автозакрытие диалога)
- `OllamaManager.started` - сервер запущен
- `OllamaManager.stopped` - сервер остановлен
- `OllamaManager.conflict_detected` - порт занят
- `ResourceManager.resource_acquired` - ресурс захвачен
- `ResourceManager.resource_released` - ресурс освобождён

### Методы перезагрузки путей
```python
def _reload_paths_light(self):
    """Лёгкая перезагрузка: обновить реестр, перезапустить Ollama"""
    
def _reload_paths_full(self):
    """Полная перезагрузка: выгрузить модели, очистить память, перезапустить"""
    
def _restart_ollama_after_cleanup(self):
    """Надёжный перезапуск Ollama после очистки"""
```

---

## 📝 ЗАМЕТКИ ДЛЯ СЛЕДУЮЩЕГО ЧАТА

### Важные моменты
1. **CleanupDialog может не освобождать порт достаточно быстро** - нужно исследовать механизм остановки Ollama
2. **Межпоточные вызовы** - `stop()` из QThread может не работать корректно с QProcess в основном потоке
3. **Сигналы вместо прямых вызовов** - возможно, нужен сигнал `ollama_restart_needed` из CleanupThread
4. **Выгрузка модели** - `keep_alive=0` через API `/api/generate` выгружает модель из памяти
5. **Нормализация путей** - `PathsManager.get_path()` нормализует пути (убирает `data/../data`)

### Что тестировать
1. Перезапуск Ollama после смены путей
2. Выгрузка модели при смене в ComboBox
3. Интерактивный выбор путей в CLI-инсталляторе
4. Валидация новых путей в настройках
5. Запуск приложения с разными конфигурациями путей

### Известные баги
1. После диалога очистки Ollama не перезапускается (Приоритет 1)
2. Старая модель остаётся в памяти при смене в ComboBox (Приоритет 2)

### Успешные тесты
1. ✅ Интерактивный выбор путей в CLI
2. ✅ Валидация новых путей в настройках
3. ✅ Индикаторы ✅/❌ для новых путей
4. ✅ Нормализация путей в PathsManager
5. ✅ Динамический выбор `--index-url` для torch

---

## 🎯 ФИНАЛЬНАЯ ЦЕЛЬ

Создать надёжную систему управления путями, где:
1. Пользователь может легко изменить пути через UI
2. При изменении путей - приложение корректно перезапускает компоненты
3. Все компоненты используют единый источник дефолтов (PathsManager)
4. Валидация путей централизована и консистентна
5. Модели выгружаются из памяти при смене (экономия RAM)

---

**Конец HANDOFF_NEXT_CHAT.md**

**Для следующего чата:**
Прочитай `HANDOFF_NEXT_CHAT.md` и продолжи с Приоритета 1 (починить перезапуск Ollama после смены путей).
