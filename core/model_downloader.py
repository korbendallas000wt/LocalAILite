"""
Модуль загрузки моделей (core/model_downloader.py).

Асинхронное скачивание моделей с сигналами для UI.
Два загрузчика: OllamaDownloader и DiffusersDownloader.

Использование:
    downloader = OllamaDownloader(config, "qwen2.5:3b")
    downloader.progress_updated.connect(lambda pct, msg: print(f"{pct}%: {msg}"))
    downloader.download_finished.connect(lambda ok, msg: print(f"Готово: {ok}, {msg}"))
    downloader.start()
"""

from PyQt6.QtCore import QObject, pyqtSignal, QProcess, QProcessEnvironment, QTimer
import os
import psutil
import re

class ModelDownloader(QObject):
    """Базовый класс для загрузчиков моделей."""
    
    # Сигналы
    progress_updated = pyqtSignal(int, str)  # (процент 0-100, сообщение)
    download_finished = pyqtSignal(bool, str)  # (успех, сообщение)
    error_occurred = pyqtSignal(str)  # сообщение об ошибке
    download_cancelled = pyqtSignal()
    
    def __init__(self, config, model_name: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.model_name = model_name
        self._process = None
        self._is_running = False
        self._is_cancelled = False
        self._last_percent = -1
    

    def _get_folder_size(self, folder_path: str) -> int:
        """Рекурсивно вычисляет размер папки в байтах."""
        total = 0
        if not folder_path or not os.path.exists(folder_path):
            return total
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except (OSError, IOError):
                        pass
        except (OSError, IOError):
            pass
        return total
    
    def _start_size_monitoring(self):
        """Запускает периодическую проверку размера папки модели."""
        if not self._repo_id or not self._models_path:
            return
        
        # Формируем имя папки HF cache: models--org--name
        self._model_folder_name = "models--" + self._repo_id.replace("/", "--")
        
        # Создаём таймер проверки размера (каждые 2 секунды)
        self._size_check_timer = QTimer(self)
        self._size_check_timer.timeout.connect(self._check_download_progress)
        self._size_check_timer.start(2000)
    
    def _check_download_progress(self):
        """Проверяет размер папки модели и обновляет прогресс."""
        if not self._models_path or not self._model_folder_name:
            return
        
        model_folder = os.path.join(self._models_path, self._model_folder_name)
        current_size = self._get_folder_size(model_folder)
        
        # Вычисляем процент от ожидаемого размера
        expected_bytes = self._model_size_gb * (1024 ** 3)
        if expected_bytes > 0:
            pct = min(90, int((current_size / expected_bytes) * 85))  # Максимум 90% (остальное — верификация)
            current_gb = current_size / (1024 ** 3)
            self._report_progress(10 + pct, f"SDXL: {current_gb:.1f} / {self._model_size_gb:.1f} GB")
    
    def _stop_size_monitoring(self):
        """Останавливает мониторинг размера папки."""
        if self._size_check_timer:
            self._size_check_timer.stop()
            self._size_check_timer = None

    def start(self):
        """Запускает скачивание (переопределяется в наследниках)."""
        raise NotImplementedError
    
    def cancel(self):
        """Отменяет скачивание."""
        self._is_cancelled = True
        if self._process:
            self._process.terminate()
            self._process.waitForFinished(3000)
            if self._process.state() != QProcess.ProcessState.NotRunning:
                self._process.kill()
        self.download_cancelled.emit()
    
    def is_running(self) -> bool:
        """Возвращает True, если скачивание активно."""
        return self._is_running
    
    def _check_disk_space(self, required_gb: float, path: str) -> bool:
        """Проверяет свободное место на диске."""
        try:
            usage = psutil.disk_usage(path)
            free_gb = usage.free / (1024**3)
            return free_gb >= required_gb
        except Exception:
            return True  # Если не удалось проверить — разрешаем
    
    def _report_progress(self, percent: int, message: str):
        """Эмитит сигнал прогресса. Прогресс только вперёд (защита от скачков)."""
        percent = min(100, max(0, percent))
        if percent <= self._last_percent:
            return
        self._last_percent = percent
        self.progress_updated.emit(percent, message)


class OllamaDownloader(ModelDownloader):
    """Загрузчик моделей Ollama через 'ollama pull'."""
    
    def __init__(self, config, model_name: str, parent=None):
        super().__init__(config, model_name, parent)
        self._ollama_bin = None
        self._models_path = None
        self._model_size_gb = 2.0  # Дефолт, переопределяется из реестра
    
    def _is_server_running(self) -> bool:
        """Проверяет, запущен ли Ollama сервер на порту 11434."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 11434))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def _start_server(self, ollama_bin: str, models_path: str = ""):
        """Запускает Ollama сервер в фоне. Возвращает Popen-объект."""
        import subprocess
        env = os.environ.copy()
        if models_path:
            env["OLLAMA_MODELS"] = models_path
        
        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env
        )
        return proc
    
    def _wait_server_ready(self, timeout: int = 30) -> bool:
        """Ждёт, пока Ollama сервер станет доступен на порту 11434."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self._is_server_running():
                return True
            time.sleep(0.5)
        return False
    
    def _stop_server(self, proc):
        """Останавливает Ollama сервер."""
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def set_model_size(self, size_gb: float):
        """Устанавливает размер модели для проверки диска."""
        self._model_size_gb = size_gb
    
    def start(self):
        """Запускает скачивание Ollama модели."""
        if self._is_running:
            return
        
        self._is_running = True
        self._is_cancelled = False
        self._last_percent = -1
        
        # Получаем пути из конфигурации
        from core.paths_manager import PathsManager
        pm = PathsManager()
        self._ollama_bin = pm.get_path(self.config, "ollama_binary")
        self._models_path = pm.get_path(self.config, "ollama_models")
        
        # Проверяем наличие бинарника
        if not self._ollama_bin or not os.path.exists(self._ollama_bin):
            self._is_running = False
            self.error_occurred.emit(f"Бинарник Ollama не найден: {self._ollama_bin}")
            self.download_finished.emit(False, "Бинарник Ollama не найден")
            return
        
        # Проверяем свободное место
        if not self._check_disk_space(self._model_size_gb, os.path.expanduser("~")):
            self._is_running = False
            msg = f"Недостаточно места для модели ({self._model_size_gb:.1f} GB)"
            self.error_occurred.emit(msg)
            self.download_finished.emit(False, msg)
            return
        
        # Проверяем, запущен ли Ollama сервер
        self._server_proc = server_proc = None
        server_started_by_us = False
        if not self._is_server_running():
            self._report_progress(8, "Ollama сервер не запущен — запускаем...")
            self._server_proc = server_proc = self._start_server(self._ollama_bin, self._models_path)
            server_started_by_us = True
            if not self._wait_server_ready(timeout=30):
                self._stop_server(server_proc)
                self._is_running = False
                msg = "Ollama сервер не запустился за 30 секунд"
                self.error_occurred.emit(msg)
                self.download_finished.emit(False, msg)
                return
            self._report_progress(10, "Ollama сервер готов")
        
        self._report_progress(5, f"Запуск скачивания {self.model_name}...")
        
        # Создаём QProcess для ollama pull
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        
        # Подключаем сигналы QProcess
        self._process.readyReadStandardOutput.connect(self._on_output_ready)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        
        # Устанавливаем переменные окружения
        env = QProcessEnvironment.systemEnvironment()
        if self._models_path:
            env.insert("OLLAMA_MODELS", self._models_path)
        self._process.setProcessEnvironment(env)
        
        # Запускаем ollama pull
        self._process.start(self._ollama_bin, ["pull", self.model_name])
        
        if not self._process.waitForStarted(5000):
            self._is_running = False
            error = self._process.errorString()
            self.error_occurred.emit(f"Не удалось запустить ollama pull: {error}")
            self.download_finished.emit(False, f"Ошибка запуска: {error}")
    
    def _on_output_ready(self):
        """Обрабатывает вывод ollama pull, парсит прогресс."""
        if not self._process:
            return
        
        output = self._process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        
        for line in re.split(r'[\r\n]+', output):
            line = line.strip()
            if not line:
                continue
            
            # Парсим процент из строки прогресса: "pulling manifest ... 45%"
            match = re.search(r'(\d+)%', line)
            if match:
                pct = int(match.group(1))
                self._report_progress(10 + int(pct * 0.85), f"Ollama: {pct}%")
            elif "verifying" in line.lower():
                self._report_progress(92, "Ollama: проверка контрольной суммы")
            elif "writing" in line.lower():
                self._report_progress(96, "Ollama: запись манифеста")
            elif "success" in line.lower():
                self._report_progress(100, f"Ollama: модель {self.model_name} скачана")
    
    def _on_process_finished(self, exit_code, exit_status):
        """Обрабатывает завершение процесса ollama pull."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._is_cancelled:
            self.download_finished.emit(False, "Скачивание отменено пользователем")
            return
        
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            # Верифицируем модель после скачивания
            self._report_progress(98, "Проверка целостности модели...")
            try:
                from core.model_validator import validate_ollama_model
                result = validate_ollama_model(self.model_name, self._models_path)
                if result.valid:
                    self._report_progress(100, f"Модель {self.model_name} успешно скачана")
                    self.download_finished.emit(True, f"Модель {self.model_name} скачана")
                else:
                    error_msg = f"Модель скачалась, но не прошла проверку: {result.errors[0] if result.errors else 'неизвестная ошибка'}"
                    self.error_occurred.emit(error_msg)
                    self.download_finished.emit(False, error_msg)
            except Exception as e:
                error_msg = f"Ошибка верификации модели: {e}"
                self.error_occurred.emit(error_msg)
                self.download_finished.emit(False, error_msg)
        else:
            error = self._process.errorString() if self._process else "Неизвестная ошибка"
            self.error_occurred.emit(f"Ошибка скачивания: {error}")
            self.download_finished.emit(False, f"Ошибка: {error}")
    
    def _on_process_error(self, error):
        """Обрабатывает ошибки QProcess."""
        if not self._is_running:
            return
        
        self._is_running = False
        error_msg = self._process.errorString() if self._process else "Ошибка процесса"
        self.error_occurred.emit(f"Ошибка процесса: {error_msg}")
        self.download_finished.emit(False, f"Ошибка процесса: {error_msg}")


class DiffusersDownloader(ModelDownloader):
    """Загрузчик моделей Diffusers через huggingface_hub в SDXL venv."""
    
    def __init__(self, config, model_name: str, parent=None):
        super().__init__(config, model_name, parent)
        self._sdxl_python = None
        self._models_path = None
        self._repo_id = None
        self._model_size_gb = 7.0  # Дефолт для SDXL
        self._size_check_timer = None
        self._model_folder_name = None  # Для HF cache: models--org--name
    
    def cancel(self):
        """Отменяет скачивание и останавливает мониторинг."""
        self._is_cancelled = True
        self._stop_size_monitoring()
        if self._process:
            self._process.terminate()
            self._process.waitForFinished(3000)
            if self._process.state() != QProcess.ProcessState.NotRunning:
                self._process.kill()
        self.download_cancelled.emit()
    
    def set_repo_id(self, repo_id: str):
        """Устанавливает HuggingFace repo_id (например, 'stabilityai/stable-diffusion-xl-base-1.0')."""
        self._repo_id = repo_id
    
    def set_model_size(self, size_gb: float):
        """Устанавливает размер модели для проверки диска."""
        self._model_size_gb = size_gb
    
    def start(self):
        """Запускает скачивание Diffusers модели."""
        if self._is_running:
            return
        
        if not self._repo_id:
            self.error_occurred.emit("Repo ID не установлен")
            self.download_finished.emit(False, "Repo ID не установлен")
            return
        
        self._is_running = True
        self._is_cancelled = False
        self._last_percent = -1
        
        # Получаем пути из конфигурации
        from core.paths_manager import PathsManager
        pm = PathsManager()
        sdxl_venv = pm.get_path(self.config, "sdxl_venv")
        self._models_path = pm.get_path(self.config, "sdxl_models")
        self._sdxl_python = os.path.join(sdxl_venv, "bin", "python") if sdxl_venv else None
        
        # Проверяем наличие SDXL venv
        if not self._sdxl_python or not os.path.exists(self._sdxl_python):
            self._is_running = False
            error_msg = f"SDXL venv не найден: {self._sdxl_python}"
            self.error_occurred.emit(error_msg)
            self.download_finished.emit(False, error_msg)
            return
        
        # Проверяем свободное место
        if not self._check_disk_space(self._model_size_gb, os.path.expanduser("~")):
            self._is_running = False
            msg = f"Недостаточно места для модели ({self._model_size_gb:.1f} GB)"
            self.error_occurred.emit(msg)
            self.download_finished.emit(False, msg)
            return
        
        self._report_progress(5, f"Запуск скачивания {self._repo_id}...")
        
        # Запускаем мониторинг размера папки
        self._start_size_monitoring()
        
        # Создаём скрипт для скачивания через huggingface_hub
        script = f"""
import sys
import json

try:
    from huggingface_hub import snapshot_download
    
    from huggingface_hub import list_repo_files

    # Определяем реальный состав репозитория: веса бывают обычные и fp16
    files = set(list_repo_files('{self._repo_id}'))
    weights = []
    for plain, fp16 in [
        ("text_encoder/model.safetensors", "text_encoder/model.fp16.safetensors"),
        ("text_encoder_2/model.safetensors", "text_encoder_2/model.fp16.safetensors"),
        ("unet/diffusion_pytorch_model.safetensors", "unet/diffusion_pytorch_model.fp16.safetensors"),
        ("vae/diffusion_pytorch_model.safetensors", "vae/diffusion_pytorch_model.fp16.safetensors"),
    ]:
        if fp16 in files:
            weights.append(fp16)
        elif plain in files:
            weights.append(plain)
    if not weights:
        raise RuntimeError('В репозитории не найдено файлов весов (.safetensors)')

    # Скачиваем модель в HF cache формате
    snapshot_download(
        repo_id='{self._repo_id}',
        cache_dir='{self._models_path}',
        allow_patterns=[
            "model_index.json",
            "scheduler/*",
            "text_encoder/config.json",
            "text_encoder_2/config.json",
            "tokenizer/*",
            "tokenizer_2/*",
            "unet/config.json",
            "vae/config.json",
        ] + weights
    )
    
    # Успех
    print('SUCCESS')
    sys.exit(0)
    
except Exception as e:
    # Ошибка
    print(f'ERROR: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
        
        # Создаём QProcess для запуска скрипта в SDXL venv
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        
        # Подключаем сигналы QProcess
        self._process.readyReadStandardOutput.connect(self._on_output_ready)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        
        # Запускаем скрипт
        self._process.start(self._sdxl_python, ["-c", script])
        
        if not self._process.waitForStarted(5000):
            self._is_running = False
            error = self._process.errorString()
            self.error_occurred.emit(f"Не удалось запустить скрипт скачивания: {error}")
            self.download_finished.emit(False, f"Ошибка запуска: {error}")
    
    def _on_output_ready(self):
        """Обрабатывает вывод скрипта скачивания."""
        if not self._process:
            return
        
        output = self._process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        
        for line in re.split(r'[\r\n]+', output):
            line = line.strip()
            if not line:
                continue
            
            # Парсим прогресс из tqdm (если есть): "Downloading: 45%|...| 3.1G/6.9G"
            if "Downloading" in line and "%" in line:
                match = re.search(r'(\d+)%', line)
                if match:
                    pct = int(match.group(1))
                    self._report_progress(10 + int(pct * 0.85), f"SDXL: {pct}%")
            elif "SUCCESS" in line:
                self._report_progress(100, f"Модель {self._repo_id} скачана")
    
    def _on_process_finished(self, exit_code, exit_status):
        """Обрабатывает завершение процесса скачивания."""
        if not self._is_running:
            return
        
        self._is_running = False
        self._stop_size_monitoring()
        
        if self._is_cancelled:
            self.download_finished.emit(False, "Скачивание отменено пользователем")
            return
        
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            # Верифицируем модель после скачивания
            self._report_progress(98, "Проверка целостности модели...")
            try:
                from core.model_validator import validate_model
                
                # Ищем скачанную модель в папке
                repo_folder_name = "models--" + self._repo_id.replace("/", "--")
                model_path = os.path.join(self._models_path, repo_folder_name)
                
                if os.path.exists(model_path):
                    result = validate_model(model_path)
                    if result.valid:
                        self._report_progress(100, f"Модель {self._repo_id} успешно скачана")
                        self.download_finished.emit(True, f"Модель {self._repo_id} скачана")
                    else:
                        error_msg = f"Модель скачалась, но не прошла проверку: {result.errors[0] if result.errors else 'неизвестная ошибка'}"
                        self.error_occurred.emit(error_msg)
                        self.download_finished.emit(False, error_msg)
                else:
                    error_msg = f"Папка модели не найдена после скачивания: {model_path}"
                    self.error_occurred.emit(error_msg)
                    self.download_finished.emit(False, error_msg)
            except Exception as e:
                error_msg = f"Ошибка верификации модели: {e}"
                self.error_occurred.emit(error_msg)
                self.download_finished.emit(False, error_msg)
        else:
            error = self._process.errorString() if self._process else "Неизвестная ошибка"
            self.error_occurred.emit(f"Ошибка скачивания: {error}")
            self.download_finished.emit(False, f"Ошибка: {error}")
    
    def _on_process_error(self, error):
        """Обрабатывает ошибки QProcess."""
        if not self._is_running:
            return
        
        self._is_running = False
        error_msg = self._process.errorString() if self._process else "Ошибка процесса"
        self.error_occurred.emit(f"Ошибка процесса: {error_msg}")
        self.download_finished.emit(False, f"Ошибка процесса: {error_msg}")
