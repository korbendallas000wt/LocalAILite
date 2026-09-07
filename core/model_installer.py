"""
core/model_installer.py — установка моделей (Этап 3).

Два воркера (QThread):
- DiffusersInstallWorker — перемещение Diffusers-модели в папку моделей
- OllamaInstallWorker — создание Ollama-модели из GGUF через 'ollama create'

Единый контракт сигналов:
    progress_updated(int, str)         # процент, сообщение
    install_finished(bool, str, bool)  # успех, сообщение, нужна ли глубокая проверка
"""

import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal


def derive_ollama_name_from_gguf(gguf_path: str) -> str:
    """Выводит имя модели из имени GGUF-файла.

    'My-Model.Q4_K_M.gguf' → 'my-model.q4_k_m' (Ollama нормализует сам).
    """
    base = os.path.basename(gguf_path)
    name = os.path.splitext(base)[0]  # убираем .gguf
    sanitized = "".join(c if (c.isalnum() or c in "._-") else "-" for c in name)
    return sanitized.lower() or "model"


class DiffusersInstallWorker(QThread):
    """Перемещение модели в папку моделей (установка)."""

    progress_updated = pyqtSignal(int, str)
    install_finished = pyqtSignal(bool, str, bool)  # успех, сообщение, нужна глубокая проверка

    def __init__(self, config, model_id: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.model_id = model_id

    def run(self):
        try:
            from core.models_registry import _load_registry_v3
            from core.paths_manager import PathsManager

            registry_data = _load_registry_v3(self.config)
            model_info = registry_data["models"].get(self.model_id)
            if not model_info:
                self.install_finished.emit(False, "Модель не найдена в реестре", False)
                return

            src = model_info.get("paths", {}).get("installed", "")
            if not src or not os.path.exists(src):
                self.install_finished.emit(False, "Исходный путь модели не найден", False)
                return

            pm = PathsManager()
            models_dir = pm.get_path(self.config, "sdxl_models")
            os.makedirs(models_dir, exist_ok=True)

            src_norm = os.path.normpath(src)
            dir_norm = os.path.normpath(models_dir)
            if src_norm.startswith(dir_norm + os.sep) or src_norm == dir_norm:
                self.install_finished.emit(False, "Модель уже находится в папке моделей", False)
                return

            dst = os.path.join(models_dir, os.path.basename(src_norm))
            if os.path.exists(dst):
                self.install_finished.emit(
                    False,
                    f"В папке моделей уже есть «{os.path.basename(dst)}». Сначала удалите её.",
                    False)
                return

            self.progress_updated.emit(5, "Подготовка перемещения...")

            # 1) пробуем rename (та же ФС — мгновенно и атомарно, данные не двигаются)
            try:
                os.rename(src, dst)
                self._set_registry_path(registry_data, dst)
                self.progress_updated.emit(100, "Перемещено")
                # Модель с диска не была проверена по хэшам — проверяем после
                # установки независимо от способа переноса (rename не гарантирует
                # валидность, только отсутствие повреждений при переносе)
                self.install_finished.emit(
                    True, f"Модель установлена: {os.path.basename(dst)}", True)
                return
            except OSError:
                pass  # разные ФС — копируем

            # 2) разные диски: копирование + удаление оригинала
            self.progress_updated.emit(8, "Копирование (разные диски)...")
            self._copy_tree_with_progress(src, dst)
            self.progress_updated.emit(95, "Удаление оригинала...")
            if os.path.isdir(src):
                shutil.rmtree(src)
            else:
                os.remove(src)
            self._set_registry_path(registry_data, dst)
            self.progress_updated.emit(100, "Готово")
            self.install_finished.emit(
                True, f"Модель установлена: {os.path.basename(dst)}", True)  # копия → глубокая проверка
        except Exception as e:
            self.install_finished.emit(False, f"Ошибка установки: {e}", False)

    def _set_registry_path(self, registry_data, new_path: str):
        from core.models_registry import _save_registry_v3
        info = registry_data["models"].get(self.model_id)
        if info:
            info["paths"]["installed"] = new_path
            info["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _save_registry_v3(self.config, registry_data)

    def _copy_tree_with_progress(self, src: str, dst: str):
        if os.path.isfile(src):
            files = [src]
            single_file = True
        else:
            files = []
            for dirpath, _, filenames in os.walk(src):
                for f in filenames:
                    files.append(os.path.join(dirpath, f))
            single_file = False

        total = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        copied = 0
        last_pct = 8
        for fp in files:
            target = dst if single_file else os.path.join(
                dst, os.path.relpath(fp, src))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(fp, "rb") as fin, open(target, "wb") as fout:
                while True:
                    chunk = fin.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
                    copied += len(chunk)
                    if total > 0:
                        pct = 8 + int(copied * 85 / total)
                        if pct > last_pct:
                            last_pct = pct
                            self.progress_updated.emit(
                                pct,
                                f"Копирование: {copied/(1024**3):.1f} / {total/(1024**3):.1f} GB")


class OllamaInstallWorker(QThread):
    """Создание Ollama-модели из GGUF через 'ollama create'."""

    progress_updated = pyqtSignal(int, str)
    install_finished = pyqtSignal(bool, str, bool)  # успех, сообщение, нужна глубокая проверка

    def __init__(self, config, model_id: str, model_name: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.model_id = model_id
        self.model_name = model_name  # имя:тег для создания

    def run(self):
        modelfile_path = None
        try:
            from core.models_registry import _load_registry_v3
            from core.paths_manager import PathsManager

            registry_data = _load_registry_v3(self.config)
            model_info = registry_data["models"].get(self.model_id)
            if not model_info:
                self.install_finished.emit(False, "Модель не найдена в реестре", False)
                return
            gguf_path = model_info.get("paths", {}).get("installed", "")
            if not gguf_path or not os.path.isfile(gguf_path):
                self.install_finished.emit(False, "GGUF-файл не найден", False)
                return

            pm = PathsManager()
            ollama_bin = pm.get_path(self.config, "ollama_binary")
            models_path = pm.get_path(self.config, "ollama_models")
            if not ollama_bin or not os.path.exists(ollama_bin):
                self.install_finished.emit(False, "Бинарник Ollama не найден", False)
                return

            self.progress_updated.emit(5, "Проверка сервера Ollama...")
            if not self._is_server_running():
                server_proc = self._start_server(ollama_bin, models_path)
                if not self._wait_server_ready(30):
                    self._stop_server(server_proc)
                    self.install_finished.emit(
                        False, "Сервер Ollama не запустился за 30 секунд", False)
                    return

            fd, modelfile_path = tempfile.mkstemp(suffix=".Modelfile")
            with os.fdopen(fd, "w") as f:
                f.write(f"FROM {gguf_path}\n")

            self.progress_updated.emit(10, f"Создание модели {self.model_name}...")
            env = os.environ.copy()
            if models_path:
                env["OLLAMA_MODELS"] = models_path

            proc = subprocess.Popen(
                [ollama_bin, "create", self.model_name, "-f", modelfile_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env)
            for line in proc.stdout:
                line = line.strip()
                if line:
                    self.progress_updated.emit(50, f"Ollama: {line[:60]}")
            proc.wait()

            if modelfile_path and os.path.exists(modelfile_path):
                os.unlink(modelfile_path)
                modelfile_path = None

            if proc.returncode == 0:
                # Модель установлена в Ollama — убираем запись исходного GGUF
                self._remove_gguf_entry()
                self.progress_updated.emit(100, "Модель создана")
                self.install_finished.emit(
                    True, f"Модель {self.model_name} установлена", False)
            else:
                self.install_finished.emit(
                    False, f"Ошибка создания (код {proc.returncode})", False)
        except Exception as e:
            self.install_finished.emit(False, f"Ошибка установки: {e}", False)
        finally:
            if modelfile_path and os.path.exists(modelfile_path):
                try:
                    os.unlink(modelfile_path)
                except Exception:
                    pass

    def _remove_gguf_entry(self):
        from core.models_registry import _load_registry_v3, _save_registry_v3
        registry_data = _load_registry_v3(self.config)
        if self.model_id in registry_data["models"]:
            del registry_data["models"][self.model_id]
            _save_registry_v3(self.config, registry_data)

    def _is_server_running(self) -> bool:
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 11434))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _start_server(self, ollama_bin: str, models_path: str = ""):
        env = os.environ.copy()
        if models_path:
            env["OLLAMA_MODELS"] = models_path
        return subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    def _wait_server_ready(self, timeout: int = 30) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self._is_server_running():
                return True
            time.sleep(0.5)
        return False

    def _stop_server(self, proc):
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
