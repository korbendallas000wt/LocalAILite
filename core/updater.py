"""
core/updater.py — модуль проверки обновлений (v1.0).

Сравнивает локальную версию (файл VERSION в корне проекта) с remote-версией
(файл VERSION в ветке main на GitHub). Работает в фоне, не блокирует UI.

Контракт:
    check_for_updates()              — запустить фоновую проверку
    update_available(current, new)   — найдена новая версия
    update_not_found(current)        — версия актуальна
    check_failed(error)              — ошибка проверки (сеть, 404 и т.п.)

Философия: ничего без ведома пользователя. Только проверка версии,
никакого скачивания или изменения файлов.
"""
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from pathlib import Path
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_URL = "https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/VERSION"
TIMEOUT_SEC = 10


class _VersionCheckWorker(QThread):
    """Фоновая проверка: читает remote VERSION, не блокирует UI."""
    finished_check = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(self, local_version, parent=None):
        super().__init__(parent)
        self.local_version = local_version

    def run(self):
        try:
            req = urllib.request.Request(
                VERSION_URL,
                headers={"User-Agent": "LocalAILite-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                remote_version = resp.read().decode("utf-8").strip()
            if not remote_version:
                self.failed.emit("Пустой ответ VERSION")
                return
            self.finished_check.emit(self.local_version, remote_version)
        except Exception as e:
            self.failed.emit(str(e))


class Updater(QObject):
    """Модуль проверки обновлений."""
    update_available = pyqtSignal(str, str)
    update_not_found = pyqtSignal(str)
    check_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

    def get_local_version(self):
        version_path = PROJECT_ROOT / "VERSION"
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except (OSError, IOError):
            return "0.0.0"

    def check_for_updates(self):
        if self._worker is not None and self._worker.isRunning():
            return
        local_version = self.get_local_version()
        self._worker = _VersionCheckWorker(local_version, self)
        self._worker.finished_check.connect(self._on_check_finished)
        self._worker.failed.connect(self._on_check_failed)
        self._worker.start()

    def _on_check_finished(self, current, remote):
        if self._is_newer(remote, current):
            self.update_available.emit(current, remote)
        else:
            self.update_not_found.emit(current)

    def _on_check_failed(self, error):
        self.check_failed.emit(error)

    @staticmethod
    def _is_newer(remote, current):
        def parse(v):
            parts = []
            for chunk in v.split("."):
                num = ""
                for ch in chunk:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                parts.append(int(num) if num else 0)
            while len(parts) < 3:
                parts.append(0)
            return tuple(parts[:3])
        try:
            return parse(remote) > parse(current)
        except Exception:
            return False
