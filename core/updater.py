"""
core/updater.py — модуль обновлений (v2.1, QNetworkAccessManager).

Проверка версий + скачивание + установка.
Контракт:
    check_for_updates()              — запустить фоновую проверку (асинхронно)
    start_update()                   — запустить полный цикл обновления
    update_available(current, new)   — найдена новая версия
    update_not_found(current)        — версия актуальна
    check_failed(error)              — ошибка проверки (сеть, 404 и т.п.)
    update_progress(stage, percent)  — прогресс обновления
    update_finished(success, msg)    — обновление завершено

Философия: ничего без ведома пользователя. Проверка → пользователь решает → обновление.
Архитектура: QNetworkAccessManager вместо QThread (асинхронно, не требует shutdown).
"""
from PyQt6.QtCore import QObject, QThread, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from pathlib import Path
import urllib.request
import zipfile
import shutil
import tempfile
import logging
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_URL = "https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/VERSION"
ARCHIVE_URL = "https://github.com/korbendallas000wt/LocalAILite/archive/refs/heads/main.zip"
CHANGELOG_URL = "https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/docs/CHANGELOG.md"
LOG_FILE = PROJECT_ROOT / "data" / "shared" / "logs" / "updater.log"

# Настройка логирования
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8"
)
logger = logging.getLogger(__name__)


class UpdateWorker(QThread):
    """Полный цикл обновления: скачивание → проверка → замена файлов."""
    progress = pyqtSignal(str, int)  # (этап, процент)
    finished = pyqtSignal(bool, str)  # (успех, сообщение)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag = False
    
    def stop(self):
        """Прервать обновление (только во время скачивания)."""
        self._stop_flag = True
    
    def run(self):
        try:
            # 1. Скачиваем архив
            self.progress.emit("Скачивание...", 0)
            archive_path = self._download_archive()
            if not archive_path:
                self.finished.emit(False, "Ошибка скачивания архива")
                return
            
            # 2. Проверяем ZIP
            self.progress.emit("Проверка архива...", 50)
            if not self._validate_archive(archive_path):
                self.finished.emit(False, "Архив повреждён")
                return
            
            # 3. Распаковываем и заменяем файлы
            self.progress.emit("Замена файлов...", 75)
            if not self._apply_update(archive_path):
                self.finished.emit(False, "Ошибка замены файлов")
                return
            
            # 4. Готово
            self.progress.emit("Обновление завершено", 100)
            logger.info("Обновление успешно завершено")
            self.finished.emit(True, "Обновление успешно установлено. Перезапустите приложение.")
            
        except Exception as e:
            logger.error(f"Критическая ошибка обновления: {e}")
            self.finished.emit(False, f"Критическая ошибка: {e}")
    
    def _download_archive(self):
        """Скачивает main.zip во временную папку."""
        try:
            temp_dir = Path(tempfile.mkdtemp())
            archive_path = temp_dir / "main.zip"
            
            req = urllib.request.Request(
                ARCHIVE_URL,
                headers={"User-Agent": "LocalAILite-Updater/2.1"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(archive_path, "wb") as f:
                    while True:
                        if self._stop_flag:
                            logger.info("Скачивание прервано пользователем")
                            return None
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            logger.info(f"Архив скачан: {archive_path} ({archive_path.stat().st_size} bytes)")
            return archive_path
        except Exception as e:
            logger.error(f"Ошибка скачивания архива: {e}")
            return None
    
    def _validate_archive(self, archive_path):
        """Проверяет валидность ZIP-архива."""
        try:
            if not zipfile.is_zipfile(archive_path):
                logger.error("Файл не является валидным ZIP-архивом")
                return False
            
            with zipfile.ZipFile(archive_path, 'r') as zf:
                # Проверяем наличие основных файлов
                names = zf.namelist()
                if not any('main.py' in name for name in names):
                    logger.error("Архив не содержит main.py")
                    return False
                if not any('VERSION' in name for name in names):
                    logger.error("Архив не содержит VERSION")
                    return False
            
            logger.info("Архив валиден")
            return True
        except Exception as e:
            logger.error(f"Ошибка валидации архива: {e}")
            return False
    
    def _apply_update(self, archive_path):
        """Заменяет файлы из архива поверх проекта."""
        try:
            temp_dir = archive_path.parent
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)
            
            # Распаковываем
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(extract_dir)
            
            # GitHub добавляет префикс LocalAILite-main/
            source_root = extract_dir / "LocalAILite-main"
            if not source_root.exists():
                logger.error("Ожидаемая структура архива не найдена")
                return False
            
            # Копируем файлы (кроме исключённых папок)
            exclude_dirs = {'data', 'venv', 'bin', 'Repo', 'WORK', 'Backup', '__pycache__', '.git'}
            
            copied_count = 0
            for item in source_root.rglob('*'):
                if item.is_file():
                    rel_path = item.relative_to(source_root)
                    
                    # Проверяем, что не в исключённой папке
                    if rel_path.parts and rel_path.parts[0] in exclude_dirs:
                        continue
                    
                    dest = PROJECT_ROOT / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
                    copied_count += 1
            
            logger.info(f"Скопировано {copied_count} файлов")
            
            # Удаляем временные файлы
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка применения обновления: {e}")
            return False


class Updater(QObject):
    """Модуль обновлений (v2.1, асинхронный через QNetworkAccessManager)."""
    update_available = pyqtSignal(str, str)
    update_not_found = pyqtSignal(str)
    check_failed = pyqtSignal(str)
    changelog_loaded = pyqtSignal(str)  # CHANGELOG для UI
    update_progress = pyqtSignal(str, int)
    update_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_network_reply)
        self._update_worker = None
        self._remote_version = None
        self._pending_requests = {}  # request_id -> request_type

    def get_local_version(self):
        """Читает локальную версию из файла VERSION."""
        version_path = PROJECT_ROOT / "VERSION"
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except (OSError, IOError):
            return "0.0.0"

    def check_for_updates(self):
        """Запускает асинхронную проверку версий через QNetworkAccessManager."""
        logger.info("Проверка обновлений (асинхронно)")
        local_version = self.get_local_version()
        
        # Создаём запрос к VERSION
        url = QUrl(VERSION_URL)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"LocalAILite-Updater/2.1")
        
        reply = self._network_manager.get(request)
        # Сохраняем тип запроса для обработки в _on_network_reply
        self._pending_requests[id(reply)] = ("version_check", local_version)

    def _on_network_reply(self, reply):
        """Обработка ответа от QNetworkAccessManager."""
        reply_id = id(reply)
        request_info = self._pending_requests.pop(reply_id, None)
        
        if not request_info:
            reply.deleteLater()
            return
        
        request_type, local_version = request_info
        
        # Проверяем ошибки сети
        if reply.error() != QNetworkReply.NetworkError.NoError:
            error_msg = reply.errorString()
            logger.error(f"Ошибка сети при проверке обновлений: {error_msg}")
            self.check_failed.emit(error_msg)
            reply.deleteLater()
            return
        
        # Читаем ответ
        data = reply.readAll().data().decode("utf-8").strip()
        reply.deleteLater()
        
        if request_type == "version_check":
            self._handle_version_check(data, local_version)
        elif request_type == "changelog":
            self._handle_changelog(data)

    def _handle_version_check(self, remote_version, local_version):
        """Обработка результата проверки версий."""
        if not remote_version:
            logger.error("Пустой ответ VERSION")
            self.check_failed.emit("Пустой ответ VERSION")
            return
        
        logger.info(f"Remote версия: {remote_version}, локальная: {local_version}")
        
        if self._is_newer(remote_version, local_version):
            logger.info(f"Доступна новая версия: {remote_version} (текущая: {local_version})")
            self._remote_version = remote_version
            self.update_available.emit(local_version, remote_version)
            # Загружаем CHANGELOG асинхронно
            self._load_changelog()
        else:
            logger.info(f"Версия актуальна: {local_version}")
            self.update_not_found.emit(local_version)

    def _load_changelog(self):
        """Асинхронно скачивает CHANGELOG.md для отображения в UI."""
        logger.info("Загрузка CHANGELOG")
        url = QUrl(CHANGELOG_URL)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"LocalAILite-Updater/2.1")
        
        reply = self._network_manager.get(request)
        self._pending_requests[id(reply)] = ("changelog", None)

    def _handle_changelog(self, changelog_text):
        """Обработка загруженного CHANGELOG."""
        try:
            # Парсим последний блок
            last_block = self._parse_changelog(changelog_text)
            self.changelog_loaded.emit(last_block)
        except Exception as e:
            logger.warning(f"Не удалось обработать CHANGELOG: {e}")

    def _parse_changelog(self, changelog_text: str) -> str:
        """Извлекает последний блок из CHANGELOG.md."""
        pattern = r'## \[[\d.]+\] — \d{4}-\d{2}-\d{2}.*?(?=## \[|\Z)'
        matches = re.findall(pattern, changelog_text, re.DOTALL)
        if matches:
            return matches[0].strip()
        return "Информация о версии недоступна"

    def start_update(self):
        """Запускает полный цикл обновления."""
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        
        logger.info("Запуск обновления")
        self._update_worker = UpdateWorker(self)
        self._update_worker.progress.connect(self.update_progress.emit)
        self._update_worker.finished.connect(self.update_finished.emit)
        self._update_worker.start()

    def cancel_update(self):
        """Прерывает обновление (только во время скачивания)."""
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.stop()
            logger.info("Обновление отменено пользователем")

    @staticmethod
    def _is_newer(remote, current):
        """Сравнивает версии (простой парсер SemVer)."""
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
