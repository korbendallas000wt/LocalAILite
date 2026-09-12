"""
core/updater.py — модуль обновлений (v2.3, QNetworkAccessManager + GitHub API).

Проверка версий + скачивание + установка.
Контракт:
    check_for_updates()              — запустить фоновую проверку (асинхронно)
    start_update()                   — запустить полный цикл обновления
    update_available(current, new)   — найдена новая версия
    update_not_found(current)        — версия актуальна
    check_failed(error, current)      — ошибка проверки (сеть, 404 и т.п.); current — локальная версия
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
import json
import base64

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# GitHub API (IPv4). Прямые URL raw.githubusercontent.com блокируются некоторыми
# провайдерами (резолвится только в IPv6 и таймаутится). API возвращает base64-контент,
# который декодируется локально. codeload.github.com (куда редиректит zipball) — IPv4.
REPO_OWNER = "korbendallas000wt"
REPO_NAME = "LocalAILite"
BRANCH = "main"
VERSION_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/VERSION?ref={BRANCH}"
ARCHIVE_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/zipball/{BRANCH}"
CHANGELOG_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/docs/CHANGELOG.md?ref={BRANCH}"
# Явный таймаут для сетевых запросов (мс). Без него QNetworkAccessManager может
# висеть минуты, пока ОС сама не разорвёт соединение.
NETWORK_TIMEOUT_MS = 10000
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
    """Полный цикл обновления: скачивание → проверка → замена файлов.

    Архив скачивается через GitHub API (zipball), который редиректит на
    codeload.github.com (IPv4, работает). Структура архива: LocalAILite-<hash>/,
    не LocalAILite-main/, поэтому _apply_update ищет любой подкаталог.
    """
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
                headers={"User-Agent": "LocalAILite-Updater/2.3"},
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
                # GitHub API zipball возвращает архив со структурой LocalAILite-<hash>/,
                # поэтому ищем main.py и VERSION в любом подкаталоге.
                names = zf.namelist()
                if not any(name.endswith('main.py') or name == 'main.py' for name in names):
                    logger.error("Архив не содержит main.py")
                    return False
                if not any(name.endswith('VERSION') or name == 'VERSION' for name in names):
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
            
            # GitHub API zipball возвращает структуру LocalAILite-<hash>/
            # (в отличие от /archive/refs/heads/main.zip, который даёт LocalAILite-main/).
            # Ищем единственный корневой каталог в extracted.
            source_root = None
            for item in extract_dir.iterdir():
                if item.is_dir():
                    source_root = item
                    break
            if source_root is None or not source_root.exists():
                logger.error("Ожидаемая структура архива не найдена")
                return False
            logger.info(f"Корень архива: {source_root.name}")
            
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
    """Модуль обновлений (v2.3, асинхронный через QNetworkAccessManager + GitHub API)."""
    update_available = pyqtSignal(str, str)
    update_not_found = pyqtSignal(str)
    check_failed = pyqtSignal(str, str)  # (error, current_version)
    changelog_loaded = pyqtSignal(str)  # CHANGELOG для UI
    update_progress = pyqtSignal(str, int)
    update_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_network_reply)
        self._update_worker = None
        self._remote_version = None
        # v2.2/v2.3: ключ — сам объект reply (сильная ссылка). Раньше был id(reply):
        # GC мог собрать Python-обёртку до сигнала finished, ответ терялся
        # (баг на PyQt 6.6 / Ubuntu — вкладка «Обновления» висела на «Проверка...»).
        self._pending_requests = {}  # reply -> (request_type, local_version)

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
        
        # Создаём запрос к VERSION через GitHub API
        url = QUrl(VERSION_URL)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"LocalAILite-Updater/2.3")
        request.setTransferTimeout(NETWORK_TIMEOUT_MS)  # Явный таймаут (мс)
        
        reply = self._network_manager.get(request)
        # Сохраняем тип запроса для обработки в _on_network_reply
        self._pending_requests[reply] = ("version_check", local_version)

    def _on_network_reply(self, reply):
        """Обработка ответа от QNetworkAccessManager."""
        request_info = self._pending_requests.pop(reply, None)

        if not request_info:
            print("[updater] Ответ сети без зарегистрированного запроса (проигнорирован)")
            reply.deleteLater()
            return
        
        request_type, local_version = request_info
        
        # Проверяем ошибки сети
        if reply.error() != QNetworkReply.NetworkError.NoError:
            error_msg = reply.errorString()
            logger.error(f"Ошибка сети при проверке обновлений: {error_msg}")
            self.check_failed.emit(error_msg, local_version)
            reply.deleteLater()
            return
        
        # Читаем ответ
        data = reply.readAll().data().decode("utf-8").strip()
        reply.deleteLater()
        
        if request_type == "version_check":
            self._handle_version_check(data, local_version)
        elif request_type == "changelog":
            self._handle_changelog(data)

    def _handle_version_check(self, raw_response, local_version):
        """Обработка результата проверки версий.

        GitHub API возвращает JSON: {"content": "<base64>", "encoding": "base64", ...}
        Нужно распарсить и декодировать base64 в строку версии.
        """
        # Парсим JSON-ответ и декодируем base64
        remote_version = self._decode_api_response(raw_response)
        if not remote_version:
            logger.error("Не удалось декодировать версию из ответа API")
            self.check_failed.emit("Не удалось получить версию (ошибка API)", local_version)
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
        request.setRawHeader(b"User-Agent", b"LocalAILite-Updater/2.3")
        request.setTransferTimeout(NETWORK_TIMEOUT_MS)  # Явный таймаут (мс)
        
        reply = self._network_manager.get(request)
        self._pending_requests[reply] = ("changelog", None)

    def _handle_changelog(self, raw_response):
        """Обработка загруженного CHANGELOG (base64 из GitHub API)."""
        try:
            changelog_text = self._decode_api_response(raw_response)
            if not changelog_text:
                logger.warning("Не удалось декодировать CHANGELOG")
                return
            # Парсим последний блок
            last_block = self._parse_changelog(changelog_text)
            print("[updater] CHANGELOG загружен")
            self.changelog_loaded.emit(last_block)
        except Exception as e:
            logger.warning(f"Не удалось обработать CHANGELOG: {e}")

    def _decode_api_response(self, raw_response: str) -> str:
        """Декодирует JSON-ответ GitHub API с base64-контентом.

        Формат ответа: {"content": "MS45LjAK\n", "encoding": "base64", ...}
        Возвращает декодированную строку или None при ошибке.
        """
        try:
            data = json.loads(raw_response)
            if "content" not in data or "encoding" not in data:
                logger.error(f"Неожиданный формат ответа API: {list(data.keys())}")
                return None
            if data["encoding"] != "base64":
                logger.error(f"Неожиданное кодирование: {data['encoding']}")
                return None
            # GitHub добавляет переводы строк в base64 (по 76 символов) — убираем
            content_b64 = data["content"].replace("\n", "").strip()
            return base64.b64decode(content_b64).decode("utf-8").strip()
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Ошибка декодирования ответа API: {e}")
            return None

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
