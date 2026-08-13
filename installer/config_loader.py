"""
config_loader.py — загрузка и объединение конфигов инсталлера.

Внешний конфиг: installer/config.json (дефолты разработчика, пушится в репозиторий)
Внутренний конфиг: data/local_config.json (пользовательские настройки, НЕ пушится)

Логика:
1. Загружаем config.json (обязательный)
2. Загружаем local_config.json (опциональный, создаётся при установке)
3. Мержим: local_config перекрывает config
4. Возвращаем объединённый конфиг

Использование:
    from installer.config_loader import load_config
    config = load_config()
    sdxl_max = config.get('python.sdxl.max')          # [3, 12]
    venv_path = config.get_path('paths.sdxl_venv')    # абсолютный путь
"""

import json
from pathlib import Path


class ConfigLoader:
    """Загрузчик конфигов инсталлера."""

    def __init__(self, project_root=None):
        if project_root is None:
            # config_loader.py лежит в installer/, корень на уровень выше
            project_root = Path(__file__).resolve().parent.parent
        self.project_root = Path(project_root)
        self.external_config_path = self.project_root / "installer" / "config.json"
        self.local_config_path = self.project_root / "data" / "local_config.json"
        self._config = {}
        self._load()

    def _load(self):
        """Загружает и мержит конфиги."""
        # 1. Внешний конфиг (обязательный)
        if not self.external_config_path.exists():
            raise FileNotFoundError(
                f"Внешний конфиг не найден: {self.external_config_path}")

        with open(self.external_config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)

        # 2. Внутренний конфиг (опциональный)
        if self.local_config_path.exists():
            try:
                with open(self.local_config_path, 'r', encoding='utf-8') as f:
                    local = json.load(f)
                self._merge(self._config, local)
            except (json.JSONDecodeError, OSError):
                # Если local_config битый — игнорируем, используем дефолты
                pass

    def _merge(self, base, override):
        """Рекурсивный мерж: override перекрывает base."""
        for key, value in override.items():
            if (key in base and isinstance(base[key], dict)
                    and isinstance(value, dict)):
                self._merge(base[key], value)
            else:
                base[key] = value

    def get(self, path, default=None):
        """Получить значение по пути через точку.

        Примеры:
            config.get('python.sdxl.max')      → [3, 12]
            config.get('urls.ollama')          → "https://..."
            config.get('nonexistent', 'def')   → 'def'
        """
        keys = path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def get_path(self, path, default=None):
        """Получить абсолютный путь. Относительные резолвятся от корня проекта.

        Пример:
            config.get_path('paths.sdxl_venv')
            → '/home/lin/SOFT/LocalAILite/venv_sdxl'
        """
        value = self.get(path, default)
        if value is None:
            return None
        p = Path(value)
        if not p.is_absolute():
            p = self.project_root / p
        return str(p)

    def save_local(self, paths=None):
        """Сохранить внутренний конфиг (data/local_config.json).

        Args:
            paths: dict с абсолютными путями. Если None — сохраняем текущие.
        """
        self.local_config_path.parent.mkdir(parents=True, exist_ok=True)

        if paths is not None:
            # Обновляем секцию paths перед сохранением
            if "paths" not in self._config:
                self._config["paths"] = {}
            self._config["paths"].update(paths)

        local_data = {"paths": self._config.get("paths", {})}
        with open(self.local_config_path, 'w', encoding='utf-8') as f:
            json.dump(local_data, f, indent=2, ensure_ascii=False)


def load_config(project_root=None):
    """Удобная функция для загрузки конфига."""
    return ConfigLoader(project_root)
