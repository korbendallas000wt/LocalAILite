"""
installer/steps/step_paths.py — шаг настройки путей (уровень 2).

Настраивает пути ко всем тяжёлым компонентам:
- Ollama бинарник и модели
- SDXL venv (torch/diffusers)
- SDXL модели
- Выходные изображения

Философия: UI живёт в папке проекта, всё тяжёлое — через выбор пути.
Для пассивного пользователя — дефолты в папке проекта.
Обязательно предупреждаем об объёме и проверяем свободное место.

Идемпотентен: если пути уже записаны — пропускает.
Чистый Python, БЕЗ PyQt — работает в CLI-бутстрапе и в UI-визарде.
"""

import os
import subprocess
import shutil

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus


class StepPaths(InstallStep):
    """Настройка путей ко всем тяжёлым компонентам."""

    id = "paths"
    name = "Настройка путей"
    description = "Выбор путей для Ollama, SDXL venv, моделей и выходных файлов"

    # Константы делегированы в PathsManager
    # PathsManager.KEYS — ключи QSettings
    # PathsManager.SIZES — размеры компонентов
    # PathsManager.LABELS — человекочитаемые названия

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        self.venv_python = os.path.join(base_dir, "venv", "bin", "python")
        # Единый источник дефолтов, размеров и названий
        from core.paths_manager import PathsManager
        self.pm = PathsManager(base_dir)

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

    def _get_default_paths(self) -> dict:
        """Дефолтные пути для пассивного пользователя (всё в папке проекта).
        Делегирует в PathsManager — единый источник дефолтов.
        Возвращает словарь с ключами QSettings (как раньше).
        """
        defaults = self.pm.get_defaults()
        # Конвертируем из коротких ключей PathsManager в QSettings-ключи
        return {
            self.pm.KEYS["ollama_binary"]: defaults["ollama_binary"],
            self.pm.KEYS["ollama_models"]: defaults["ollama_models"],
            self.pm.KEYS["sdxl_venv"]: defaults["sdxl_venv"],
            self.pm.KEYS["sdxl_models"]: defaults["sdxl_models"],
            self.pm.KEYS["sdxl_output"]: defaults["sdxl_output"],
            self.pm.KEYS["ollama_url"]: defaults["ollama_url"],
        }

    def _get_disk_free_gb(self, path: str) -> float:
        """Возвращает свободное место на диске для пути (GB)."""
        try:
            # Ищем ближайший существующий родительский каталог
            check_path = path
            while check_path and not os.path.exists(check_path):
                check_path = os.path.dirname(check_path)
            if not check_path:
                check_path = "/"
            usage = shutil.disk_usage(check_path)
            return round(usage.free / (1024 ** 3), 1)
        except Exception:
            return 0.0

    def choose_paths_interactive(self) -> dict:
        """Интерактивный выбор путей в CLI.
        
        Для каждого пути показывает:
        - Дефолт (в папке проекта)
        - Требуемый объём
        - Свободное место на диске
        Пользователь может оставить дефолт (Enter) или указать другой путь.
        """
        defaults = self._get_default_paths()
        chosen = {}

        # Общий объём (через PathsManager)
        total_size = self.pm.get_total_size_gb()
        print(f"\n  ⚠ Общий объём для всех компонентов: ~{total_size:.1f} GB")
        print("  Вы можете оставить пути по умолчанию или указать другие.\n")

        # Маппинг QSettings-ключа → имя в PathsManager (для LABELS и SIZES)
        qkey_to_name = {v: k for k, v in self.pm.KEYS.items()}

        for key, default in defaults.items():
            # URL не требует выбора пути
            if key == self.pm.KEYS["ollama_url"]:
                chosen[key] = default
                continue

            name = qkey_to_name.get(key, key)
            label = self.pm.LABELS.get(name, key)
            size = self.pm.SIZES.get(name, 0)
            free_gb = self._get_disk_free_gb(default)

            print(f"  --- {label} (~{size:.1f} GB) ---")
            print(f"  По умолчанию: {default}")
            print(f"  Свободно на диске: {free_gb:.1f} GB")

            if free_gb < size:
                print(f"  ⚠ Недостаточно места! Нужно {size:.1f} GB, свободно {free_gb:.1f} GB")

            user_input = input(f"  [Enter] — оставить | [путь] — изменить: ").strip()

            if user_input:
                chosen_path = os.path.expanduser(user_input)
                # Проверяем свободное место на новом диске
                new_free_gb = self._get_disk_free_gb(chosen_path)
                if new_free_gb < size:
                    print(f"  ⚠ На новом пути тоже мало места: {new_free_gb:.1f} GB < {size:.1f} GB")
                    confirm = input(f"  Всё равно использовать? [y/N]: ").strip().lower()
                    if confirm != 'y':
                        chosen[key] = default
                        continue
                chosen[key] = chosen_path
                print(f"  ✅ Выбрано: {chosen_path}")
            else:
                chosen[key] = default
                print(f"  ✅ Оставлено: {default}")

        return chosen

    def _read_config_value(self, key: str, default: str = "") -> str:
        """Читает значение из Config (JSON, без PyQt)."""
        try:
            from utils.config import Config
            config = Config()
            value = config.get(key, default)
            return value if value else default
        except Exception:
            return default

    def _write_config_values(self, values: dict) -> bool:
        """Записывает значения в QSettings через venv python."""
        if not os.path.exists(self.venv_python):
            print("  ⚠ venv не создан — пути нельзя записать.")
            print("     Сначала выполните шаг 3 (создание окружения приложения).")
            return False
        lines = ["from utils.config import Config; c = Config()"]
        for key, value in values.items():
            escaped = value.replace("'", "\\'")
            lines.append(f"c.set('{key}', '{escaped}')")
        script = "; ".join(lines)
        try:
            result = subprocess.run(
                [self.venv_python, "-c", script],
                capture_output=True, text=True, timeout=10, cwd=self.base_dir
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_installed(self) -> StepStatus:
        """Проверяет, записаны ли все пути в Config."""
        defaults = self._get_default_paths()
        missing = []

        # Маппинг QSettings-ключа → имя для LABELS
        qkey_to_name = {v: k for k, v in self.pm.KEYS.items()}

        for key in defaults:
            value = self._read_config_value(key)
            if not value:
                name = qkey_to_name.get(key, key)
                missing.append(self.pm.LABELS.get(name, key))

        if missing:
            return StepStatus.failed(
                f"Пути не настроены: {', '.join(missing)}",
                details="Требуется настройка через step_paths"
            )

        return StepStatus.success("Все пути настроены")

    def install(self, progress=None, paths=None) -> StepStatus:
        """Записывает пути в QSettings.
        
        Args:
            progress: callback прогресса
            paths: словарь путей для записи. Если None — дефолты.
                   В CLI-режиме использовать choose_paths_interactive().
                   В UI-визарде — пути из диалога.
        """
        if paths is None:
            paths = self._get_default_paths()

        self._report(progress, 20, "Создание папок...")

        # Создаём папки, которые должны существовать (через ключи PathsManager)
        dirs_to_create = [
            self.pm.KEYS["ollama_binary"],
            self.pm.KEYS["ollama_models"],
            self.pm.KEYS["sdxl_models"],
            self.pm.KEYS["sdxl_output"],
        ]
        for key in dirs_to_create:
            if key in paths:
                path = paths[key]
                # Для ollama_binary создаём родительскую папку (это файл)
                if key == self.pm.KEYS["ollama_binary"]:
                    path = os.path.dirname(path)
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception:
                    pass

        self._report(progress, 60, "Сохранение путей в Config...")
        if not self._write_config_values(paths):
            return StepStatus.failed(
                "Не удалось записать пути в Config",
                details="Ошибка записи в data/local_config.json"
            )

        self._report(progress, 100, "Пути настроены")
        return StepStatus.success(
            "Пути настроены",
            details=f"ollama={paths.get(self.pm.KEYS['ollama_binary'], '')}, "
                    f"sdxl_models={paths.get(self.pm.KEYS['sdxl_models'], '')}"
        )

    def verify(self) -> StepStatus:
        """Проверяет после установки."""
        return self.is_installed()
