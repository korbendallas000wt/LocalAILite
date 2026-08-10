"""
core/paths_manager.py — единый модуль управления путями (v2.0).
Все компоненты (CLI-инсталлятор, UI-визард, настройки приложения)
читают и пишут пути только через PathsManager. Никаких захардкоженных
дефолтов в других местах.

Принципы:
- Дефолты и метаданные — чистый Python (доступны без PyQt)
- Чтение/запись — через Config (нужен PyQt/QSettings)
- Запись путей ТОЛЬКО через PathsManager (никаких config.set напрямую)
- Валидация с уровнями (0=формат, 1=существование, 2=функциональность)

Ключи QSettings:
ollama/binary_path — путь к файлу бинарника Ollama
ollama/lib_path — путь к папке библиотек Ollama
ollama/models_path — путь к папке моделей Ollama
sdxl/venv_path — путь к SDXL venv (torch/diffusers)
sdxl/models_path — путь к папке моделей SDXL
sdxl/output_dir — папка выходных изображений
url — URL Ollama сервера
"""
import os
import json


class PathsManager:
    """Единая точка доступа к путям компонентов."""

    # Ключи QSettings для всех путей
    KEYS = {
        "ollama_binary": "ollama/binary_path",
        "ollama_lib": "ollama/lib_path",
        "ollama_models": "ollama/models_path",
        "sdxl_venv": "sdxl/venv_path",
        "sdxl_models": "sdxl/models_path",
        "sdxl_output": "sdxl/output_dir",
        "ollama_url": "url",
    }

    # Размеры компонентов для предупреждений (GB)
    SIZES = {
        "ollama_binary": 2.1,
        "ollama_models": 4.5,
        "sdxl_venv": 6.0,
        "sdxl_models": 10.0,
        "sdxl_output": 0.5,
    }

    # Человекочитаемые названия
    LABELS = {
        "ollama_binary": "Ollama бинарник",
        "ollama_lib": "Ollama библиотеки",
        "ollama_models": "Ollama модели",
        "sdxl_venv": "SDXL venv (torch/diffusers)",
        "sdxl_models": "SDXL модели",
        "sdxl_output": "Выходные изображения",
        "ollama_url": "Ollama URL",
    }

    # Критичность путей (блокируют ли сохранение/запуск)
    CRITICAL = {
        "ollama_binary": True,   # без бинарника Ollama не стартует
        "ollama_lib": False,     # библиотеки опциональны
        "ollama_models": False,  # модели могут быть ещё не скачаны
        "sdxl_venv": True,       # без venv SDXL не работает
        "sdxl_models": True,     # без моделей генерация невозможна
        "sdxl_output": True,     # без выходной папки нельзя сохранять
        "ollama_url": False,     # сервер запустится автоматически
    }

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir

    def _find_project_root(self) -> str:
        """Ищем корень проекта (где main.py)."""
        cur = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            if os.path.exists(os.path.join(cur, "main.py")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.getcwd()

    # === Дефолты (чистый Python, без PyQt) ===

    def get_defaults(self) -> dict:
        """Дефолтные пути для пассивного пользователя (всё в папке проекта)."""
        return {
            "ollama_binary": os.path.join(self.base_dir, "bin", "ollama", "bin", "ollama"),
            "ollama_lib": os.path.join(self.base_dir, "bin", "ollama", "lib", "ollama"),
            "ollama_models": os.path.join(self.base_dir, "data", "ollama_models"),
            "sdxl_venv": os.path.join(self.base_dir, "venv_sdxl"),
            "sdxl_models": os.path.join(self.base_dir, "data", "models"),
            "sdxl_output": os.path.expanduser("~/Pictures/LocalAILite"),
            "ollama_url": "http://localhost:11434",
        }

    def get_sizes(self) -> dict:
        """Размеры компонентов для предупреждений (GB)."""
        return self.SIZES.copy()

    def get_labels(self) -> dict:
        """Человекочитаемые названия."""
        return self.LABELS.copy()

    def get_total_size_gb(self) -> float:
        """Общий объём для всех компонентов."""
        return round(sum(self.SIZES.values()), 1)

    # === Чтение путей ===

    def get_raw_paths(self, config) -> dict:
        """Сырые значения путей из Config (БЕЗ fallback на дефолты).
        Пустая строка = пользователь не указал путь.
        Используется для детектирования изменений.
        """
        raw = {}
        for name, key in self.KEYS.items():
            value = config.get(key, "")
            raw[name] = value if value else ""
        return raw

    def get_effective_paths(self, config) -> dict:
        """Эффективные пути: сырые значения с fallback на дефолты.
        Используется для запуска приложения и передачи в компоненты.
        """
        defaults = self.get_defaults()
        raw = self.get_raw_paths(config)
        paths = {}
        for name, value in raw.items():
            path = value if value else defaults.get(name, "")
            # Нормализуем путь (убираем data/../data и т.п.)
            if path and not path.startswith("http"):
                path = os.path.normpath(path)
            paths[name] = path
        return paths

    def get_paths(self, config) -> dict:
        """Совместимость со старым API. То же, что get_effective_paths."""
        return self.get_effective_paths(config)

    def get_path(self, config, name: str) -> str:
        """Один эффективный путь из Config с fallback на дефолт."""
        defaults = self.get_defaults()
        key = self.KEYS.get(name)
        if not key:
            return defaults.get(name, "")
        value = config.get(key, "")
        path = value if value else defaults.get(name, "")
        # Нормализуем путь
        if path and not path.startswith("http"):
            path = os.path.normpath(path)
        return path

    # === Запись путей (ТОЛЬКО через PathsManager) ===

    def set_path(self, config, name: str, value: str):
        """Записывает путь в Config.
        Это ЕДИНСТВЕННЫЙ способ записи путей.
        """
        key = self.KEYS.get(name)
        if key:
            config.set(key, value)

    def set_paths(self, config, values: dict):
        """Массовая запись путей. values: {name: path}."""
        for name, value in values.items():
            self.set_path(config, name, value)

    # === Валидация ===

    def validate(self, config, level: int = 1) -> dict:
        """Валидация всех путей с указанием уровня.

        Уровни:
        0 — формат (синтаксис, тип)
        1 — существование (файл/папка на месте)
        2 — функциональность (реально работает: запуск бинарника, HTTP)

        Args:
            config: экземпляр Config
            level: максимальный уровень проверки

        Returns:
            dict: {name: {"valid", "level", "error", "critical", "details"}, ...}
                  + ключ "all_valid"
        """
        from core.path_validator import PathValidator
        validator = PathValidator()
        paths = self.get_effective_paths(config)
        result = {}
        all_valid = True

        # Маппинг имени пути → метод валидатора (уровень 1+)
        validators = {
            "ollama_binary": validator.validate_ollama_binary,
            "ollama_models": validator.validate_ollama_models_path,
            "ollama_url": validator.validate_ollama_url,
            "sdxl_venv": validator.validate_venv,
            "sdxl_models": validator.validate_models_path,
            "sdxl_output": validator.validate_output_dir,
        }

        for name, path in paths.items():
            validate_fn = validators.get(name)
            if not validate_fn:
                continue

            # Проверяем только включённые компоненты
            if name.startswith("ollama") and not config.get_feature("ollama", True):
                continue
            if name.startswith("sdxl") and not config.get_feature("sdxl", True):
                continue

            critical = self.CRITICAL.get(name, False)

            # Уровень 0 — только формат (без subprocess/HTTP)
            if level == 0:
                if name == "ollama_url":
                    valid = bool(path and path.startswith("http"))
                    error = "" if valid else "Неверный формат URL"
                else:
                    valid = bool(path)
                    error = "" if valid else "Путь не указан"
                result[name] = {
                    "valid": valid, "level": 0, "error": error,
                    "critical": critical, "details": {}
                }
                if not valid and critical:
                    all_valid = False
                continue

            # Уровень 1+ — вызываем валидатор
            vr = validate_fn(path)
            result[name] = {
                "valid": vr.get("valid", False),
                "level": level,
                "error": vr.get("error", ""),
                "critical": critical,
                "details": {k: v for k, v in vr.items() if k not in ("valid", "error")}
            }
            if not result[name]["valid"] and critical:
                all_valid = False

        result["all_valid"] = all_valid
        return result

    def validate_all(self, config) -> dict:
        """Совместимость со старым API. Валидация уровня 1."""
        return self.validate(config, level=1)

    # === Источники моделей ===

    def get_model_sources(self) -> dict:
        """Читает ссылки на источники моделей из data/model_sources.json.
        Если файл не существует — возвращает дефолтные ссылки.
        """
        sources_path = os.path.join(self.base_dir, "data", "model_sources.json")
        if os.path.exists(sources_path):
            try:
                with open(sources_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Дефолтные ссылки (если файла нет)
        return {
            "sdxl": [
                {"label": "🌐 HuggingFace Diffusers",
                 "url": "https://huggingface.co/models?pipeline_tag=text-to-image&sort=downloads"},
                {"label": "🎨 CivitAI (SDXL)",
                 "url": "https://civitai.com/model-versions?baseModel=SDXL%201.0"},
                {"label": "📦 SDXL Base",
                 "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0"},
                {"label": "📦 SDXL Refiner",
                 "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0"}
            ],
            "ollama": [
                {"label": "📦 Ollama Library",
                 "url": "https://ollama.com/library"}
            ]
        }

    # === Утилиты ===

    def get_disk_free_gb(self, path: str) -> float:
        """Возвращает свободное место на диске для пути (GB)."""
        import shutil
        try:
            check_path = path
            while check_path and not os.path.exists(check_path):
                check_path = os.path.dirname(check_path)
            if not check_path:
                check_path = "/"
            usage = shutil.disk_usage(check_path)
            return round(usage.free / (1024 ** 3), 1)
        except Exception:
            return 0.0
