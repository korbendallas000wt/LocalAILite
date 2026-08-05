"""
installer/steps/base.py — базовый класс шага установки.

Принципы:
- Чистый Python, БЕЗ PyQt. Шаг работает и в CLI-бутстрапе (терминал),
  и в UI-визарде (через обёртку QThread).
- Идемпотентность: каждый шаг сам проверяет своё состояние через is_installed().
- Прогресс сообщается через callback (для CLI — print, для UI — сигнал).
- run() — главный метод: если уже установлено — пропустить, иначе установить.

Контракт шага:
    id / name / description  — метаданные для UI
    is_installed() -> StepStatus   — проверить состояние (идемпотентность)
    install(progress) -> StepStatus — установить
    verify() -> StepStatus         — проверить после установки
    run(progress) -> StepStatus    — идемпотентный запуск
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class StepStatus:
    """Результат выполнения шага."""
    ok: bool
    skipped: bool = False
    message: str = ""
    details: str = ""

    @classmethod
    def success(cls, message: str, details: str = "") -> "StepStatus":
        return cls(ok=True, skipped=False, message=message, details=details)

    @classmethod
    def skip(cls, message: str) -> "StepStatus":
        return cls(ok=True, skipped=True, message=message)

    @classmethod
    def failed(cls, message: str, details: str = "") -> "StepStatus":
        return cls(ok=False, skipped=False, message=message, details=details)


# Callback прогресса: (percent: int, message: str)
ProgressCallback = Callable[[int, str], None]


class InstallStep:
    """Базовый класс шага установки."""

    # Метаданные (переопределяются в наследниках)
    id: str = ""
    name: str = ""
    description: str = ""

    def is_installed(self) -> StepStatus:
        """Проверить, установлен ли уже компонент (идемпотентность)."""
        raise NotImplementedError

    def install(self, progress: Optional[ProgressCallback] = None) -> StepStatus:
        """Установить компонент."""
        raise NotImplementedError

    def verify(self) -> StepStatus:
        """Проверить после установки."""
        raise NotImplementedError

    def run(self, progress: Optional[ProgressCallback] = None) -> StepStatus:
        """Идемпотентный запуск шага.
        Если уже установлено — пропустить, иначе установить и проверить.
        """
        # 1. Проверяем, установлено ли уже
        status = self.is_installed()
        if status.ok:
            return StepStatus.skip(f"Уже установлено: {status.message}")
        # 2. Устанавливаем
        status = self.install(progress)
        if not status.ok:
            return status
        # 3. Проверяем после установки
        return self.verify()

    def _report(self, progress: Optional[ProgressCallback], percent: int, message: str):
        """Утилита для сообщения прогресса (безопасно к None)."""
        if progress:
            progress(percent, message)
