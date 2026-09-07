"""
installer/steps/step_config.py — шаг создания структуры данных (data/).

Самый простой шаг: только файловая система, без venv/сети/PyQt.
Создаёт папки data/ для моделей, выходов, чекпоинтов, логов, кэша.

Идемпотентен: если структура уже существует — пропускает.
Запись путей в Config/PathValidator — на уровне UI-визарда, не здесь.
"""

import os

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus


class StepConfig(InstallStep):
    """Создание структуры data/ в корне проекта."""

    id = "config"
    name = "Структура данных"
    description = "Создание папок data/ для моделей, выходов, чекпоинтов, логов"

    # Относительные подпапки внутри data/
    SUBDIRS = [
        "ollama/models",
        "ollama/chats",            # Сохранённые чаты (JSON/TXT)
        "diffusers/history",       # История генерации: {timestamp}/step_NNNN.{pt,json}
        "diffusers/init_images",   # Подготовленные изображения для img2img
        "diffusers/models",        # Модели SDXL (чекпоинты)
        "diffusers/previews",      # Промежуточные PNG превью шагов (технические)
        "image_prep/presets",      # Пресеты визуального редактора (на будущее)
        "shared/config",           # local_config.json
        "shared/registry",         # model_sources.json, models_registry.json
        "shared/logs",             # Логи diffusers_*.log и ollama.log
        "shared/pids",             # PID-файлы (ollama.pid, diffusers.pid)
    ]

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        self.data_dir = os.path.join(self.base_dir, "data")

    def _find_project_root(self) -> str:
        """Ищем корень проекта (где main.py), поднимаясь от этого файла."""
        cur = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            if os.path.exists(os.path.join(cur, "main.py")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.getcwd()

    def is_installed(self) -> StepStatus:
        """Проверяем, что все подпапки существуют."""
        missing = [
            d for d in self.SUBDIRS
            if not os.path.isdir(os.path.join(self.data_dir, d))
        ]
        if missing:
            return StepStatus.failed(
                f"Отсутствуют подпапки data/: {', '.join(missing)}",
                details=f"data_dir={self.data_dir}",
            )
        return StepStatus.success(f"Структура data/ полная ({self.data_dir})")

    def install(self, progress=None) -> StepStatus:
        """Создаём все подпапки и копируем базовые файлы реестра."""
        try:
            for i, subdir in enumerate(self.SUBDIRS):
                path = os.path.join(self.data_dir, subdir)
                os.makedirs(path, exist_ok=True)
                percent = int((i + 1) / len(self.SUBDIRS) * 100)
                self._report(progress, percent, f"data/{subdir}")
            
            # Копируем базовый справочник описаний (идемпотентно: не перезаписываем существующий)
            src_lib = os.path.join(self.base_dir, "scripts", "ollama_library.json")
            dst_lib = os.path.join(self.data_dir, "shared", "registry", "ollama_library.json")
            if os.path.exists(src_lib) and not os.path.exists(dst_lib):
                import shutil
                shutil.copy(src_lib, dst_lib)
            
            return StepStatus.success(
                f"Создана структура data/ ({len(self.SUBDIRS)} подпапок)",
                details=f"data_dir={self.data_dir}",
            )
        except Exception as e:
            return StepStatus.failed(f"Ошибка создания data/: {e}")

    def verify(self) -> StepStatus:
        return self.is_installed()
