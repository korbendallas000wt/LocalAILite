"""
utils/config.py — управление настройками приложения.

Хранение: data/local_config.json (в папке проекта, НЕ пушится)
Миграция: при первом запуске копирует значения из QSettings (если есть)

Структура JSON:
{
  "version": 1,
  "settings": { "url": "...", "sdxl/venv_path": "...", ... },
  "features": { "ollama": true, "sdxl": true }
}
"""

import json
import os
from pathlib import Path


class Config:
    def __init__(self):
        self._data_dir = self._get_data_dir()
        self._config_path = self._data_dir / "shared" / "config" / "local_config.json"
        self._data = {"version": 1, "settings": {}, "features": {}}
        self._load()

    def _get_data_dir(self) -> Path:
        """Путь к папке data/ проекта."""
        return Path(__file__).resolve().parent.parent / "data"

    def _load(self):
        """Загружает конфиг из JSON или мигрирует из QSettings."""
        if self._config_path.exists():
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                return
            except (json.JSONDecodeError, OSError):
                # Битый файл — создаём заново
                pass

        # JSON нет — пробуем мигрировать из QSettings
        migrated = self._migrate_from_qsettings()
        if not migrated:
            # QSettings тоже нет — создаём пустой конфиг
            self._save()

    def _migrate_from_qsettings(self) -> bool:
        """Мигрирует настройки из QSettings в JSON.

        Returns:
            True если миграция прошла успешно, False если QSettings пуст
        """
        try:
            from PyQt6.QtCore import QSettings
        except ImportError:
            return False

        settings = QSettings("LocalAILite", "LocalAILite")
        keys = settings.allKeys()

        if not keys:
            return False

        # Миграция из старого OllamaChat
        old_settings = QSettings("OllamaChat", "OllamaChat")
        if not old_settings.contains("migrated"):
            for key in old_settings.allKeys():
                if not settings.contains(key):
                    settings.setValue(key, old_settings.value(key))
            old_settings.setValue("migrated", "true")

        # Копируем значения в JSON
        migrated_count = 0
        for key in settings.allKeys():
            value = settings.value(key)
            if value is not None:
                # Определяем, куда класть: settings или features
                if key.startswith("features/"):
                    feature_name = key.replace("features/", "")
                    # Конвертируем строку в bool
                    if isinstance(value, str):
                        self._data["features"][feature_name] = value.lower() == "true"
                    else:
                        self._data["features"][feature_name] = bool(value)
                else:
                    # Конвертируем типы
                    if isinstance(value, str):
                        # Пробуем распарсить число
                        try:
                            if '.' in value:
                                value = float(value)
                            else:
                                value = int(value)
                        except ValueError:
                            pass  # Оставляем как строку
                    self._data["settings"][key] = value
                migrated_count += 1

        if migrated_count > 0:
            self._save()
            return True

        return False

    def _save(self):
        """Сохраняет конфиг в JSON."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        """Получить значение по ключу.

        Ключи с префиксом "features/" читаются из features, остальные из settings.
        """
        if key.startswith("features/"):
            feature_name = key.replace("features/", "")
            return self._data.get("features", {}).get(feature_name, default)
        else:
            return self._data.get("settings", {}).get(key, default)

    def set(self, key, value):
        """Записать значение по ключу."""
        if key.startswith("features/"):
            feature_name = key.replace("features/", "")
            if "features" not in self._data:
                self._data["features"] = {}
            self._data["features"][feature_name] = value
        else:
            if "settings" not in self._data:
                self._data["settings"] = {}
            self._data["settings"][key] = value
        self._save()

    def get_json(self, key, default=None):
        """Получить значение из конфига и десериализовать из JSON"""
        value = self.get(key)
        if value is None:
            return default
        try:
            if isinstance(value, str):
                return json.loads(value)
            return value
        except (json.JSONDecodeError, TypeError):
            return default

    def set_json(self, key, value):
        """Сериализовать значение в JSON и сохранить в конфиг"""
        self.set(key, json.dumps(value, ensure_ascii=False))

    # === Ollama ===
    def get_ollama_url(self):
        return self.get("url", "http://localhost:11434")

    # === SDXL ===
    def get_sdxl_venv_path(self):
        return self.get("sdxl/venv_path", "")

    def set_sdxl_venv_path(self, path):
        self.set("sdxl/venv_path", path)

    def get_sdxl_models_path(self):
        return self.get("sdxl/models_path", "")

    def set_sdxl_models_path(self, path):
        self.set("sdxl/models_path", path)

    def get_sdxl_scheduler(self):
        return self.get("sdxl/scheduler", "EulerDiscreteScheduler")

    def set_sdxl_scheduler(self, scheduler):
        self.set("sdxl/scheduler", scheduler)

    def get_sdxl_default_steps(self):
        value = self.get("sdxl/steps", 30)
        return int(value) if value else 30

    def get_sdxl_default_cfg(self):
        value = self.get("sdxl/cfg", 7.5)
        return float(value) if value else 7.5

    def get_sdxl_output_dir(self):
        return self.get("sdxl/output_dir", os.path.expanduser("~/Pictures/LocalAILite"))

    def get_sdxl_device(self):
        return self.get("sdxl/device", "cuda")

    def set_sdxl_device(self, device):
        self.set("sdxl/device", device)

    def set_sdxl_output_dir(self, path):
        self.set("sdxl/output_dir", path)

    def get_data_dir(self):
        """Возвращает путь к внутренней папке data/ проекта"""
        return str(self._data_dir)

    def get_previews_dir(self):
        """Папка для промежуточных превью (технические файлы)"""
        return os.path.join(self.get_data_dir(), "diffusers", "previews")

    def get_history_dir(self):
        """Папка для истории генерации (PNG на каждом шаге)"""
        return os.path.join(self.get_data_dir(), "diffusers", "history")

    def get_logs_dir(self):
        """Папка для логов (технические файлы)"""
        return os.path.join(self.get_data_dir(), "shared", "logs")

    # === Ollama (локальный бинарник) ===
    def get_ollama_binary_path(self):
        """Путь к локальному бинарнику Ollama"""
        default = os.path.join(self.get_data_dir(), "..", "bin", "ollama", "bin", "ollama")
        default = os.path.normpath(default)
        return self.get("ollama/binary_path", default)

    def set_ollama_binary_path(self, path):
        self.set("ollama/binary_path", path)

    def get_ollama_lib_dir(self):
        """Папка с библиотеками Ollama (CUDA, ROCm)"""
        default = os.path.join(self.get_data_dir(), "..", "bin", "ollama", "lib", "ollama")
        default = os.path.normpath(default)
        return self.get("ollama/lib_path", default)

    def set_ollama_lib_dir(self, path):
        self.set("ollama/lib_path", path)

    # === Image Prep ===
    def get_init_images_dir(self):
        """Папка для подготовленных изображений"""
        return os.path.join(self.get_data_dir(), "diffusers", "init_images")

    def get_models_registry_path(self):
        """Путь к файлу реестра моделей"""
        return os.path.join(self.get_data_dir(), "shared", "registry", "models_registry.json")

    # === Features (усечённое приложение) ===
    def get_feature(self, feature_name: str, default: bool = True) -> bool:
        """Возвращает флаг компонента (features/*)."""
        value = self.get(f"features/{feature_name}", None)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"

    def set_feature(self, feature_name: str, enabled: bool):
        """Устанавливает флаг компонента (features/*)."""
        self.set(f"features/{feature_name}", enabled)
