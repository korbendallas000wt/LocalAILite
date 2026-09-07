"""
core/model_verifier.py — асинхронная глубокая проверка моделей.

DeepValidationWorker (QThread): хэш-проверка модели в фоне,
с прогрессом и отменой. Используется Менеджером моделей:
- явная кнопка «Полная проверка»
- автоматическая проверка после завершения скачивания
"""

from PyQt6.QtCore import QThread, pyqtSignal
from core.model_validator import (validate_model_deep, validate_ollama_model_deep,
                                   ValidationCancelled)


class DeepValidationWorker(QThread):
    """Глубокая (хэш) проверка модели в фоновом потоке.

    Args:
        model_type: "diffusers" или "ollama"
        target: для diffusers — путь к модели (корень models--*),
                для ollama — имя модели "имя:тег"
        config: конфигурация приложения

    Signals:
        progress_updated(current, total, message)
        verification_finished(valid, errors, warnings, cancelled)
    """

    progress_updated = pyqtSignal(int, int, str)
    verification_finished = pyqtSignal(bool, list, list, bool)

    def __init__(self, model_type: str, target: str, config, parent=None):
        super().__init__(parent)
        self.model_type = model_type
        self.target = target
        self.config = config
        self._cancel_requested = False

    def cancel(self):
        """Запросить отмену (сработает на следующем чанке/файле)."""
        self._cancel_requested = True

    def _cancel_check(self) -> bool:
        return self._cancel_requested

    def _progress(self, current: int, total: int, message: str):
        self.progress_updated.emit(current, total, message)

    def run(self):
        try:
            if self.model_type == "ollama":
                from core.paths_manager import PathsManager
                pm = PathsManager()
                models_path = pm.get_path(self.config, "ollama_models")
                result = validate_ollama_model_deep(
                    self.target, models_path,
                    progress=self._progress,
                    cancel_check=self._cancel_check)
            else:
                result = validate_model_deep(
                    self.target,
                    progress=self._progress,
                    cancel_check=self._cancel_check)
            self.verification_finished.emit(
                result.valid, result.errors, result.warnings, False)
        except ValidationCancelled:
            self.verification_finished.emit(
                False, ["Проверка отменена"], [], True)
        except Exception as e:
            self.verification_finished.emit(
                False, [f"Ошибка проверки: {e}"], [], False)
