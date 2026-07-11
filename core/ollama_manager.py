from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal
import os
import socket
import time
from core.resource_monitor import ResourceMonitor


class OllamaManager(QObject):
    """Управляет процессом Ollama-сервера"""

    # Сигналы
    started = pyqtSignal()           # Сервер запущен и готов
    stopped = pyqtSignal()           # Сервер остановлен
    error = pyqtSignal(str)          # Ошибка
    log_line = pyqtSignal(str)       # Строка лога
    needs_install = pyqtSignal()     # Требуется установка Ollama
    conflict_detected = pyqtSignal() # Обнаружен конфликт (Ollama уже запущен)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self._is_our_process = False  # Наш ли это процесс
        self._log_file = None
        self._log_path = None
        self._pid_path = None

    def start(self):
        """Запускает Ollama-сервер"""
        # 1. Проверяем, не запущен ли уже
        if self._is_port_busy():
            # Порт занят — спрашиваем пользователя
            self.conflict_detected.emit()
            return

        # 2. Проверяем наличие бинарника
        ollama_bin = self._get_ollama_binary()
        if not ollama_bin:
            self.needs_install.emit()
            return

        # 3. Запускаем свой процесс
        self._start_process(ollama_bin)

    def use_existing(self):
        """Использует существующий Ollama-сервер (не наш процесс)"""
        self._is_our_process = False
        self.started.emit()

    def kill_existing_and_start(self):
        """Убивает существующий Ollama и запускает свой"""
        import subprocess
        try:
            subprocess.run(["pkill", "-9", "ollama"], timeout=5)
            time.sleep(1)  # Ждём освобождения порта
        except Exception as e:
            self.error.emit(f"Не удалось убить Ollama: {e}")
            return

        # Проверяем, что порт освободился
        if self._is_port_busy():
            self.error.emit("Порт 11434 всё ещё занят")
            return

        # Запускаем свой процесс
        ollama_bin = self._get_ollama_binary()
        if ollama_bin:
            self._start_process(ollama_bin)
        else:
            self.needs_install.emit()

    def stop(self):
        """Останавливает Ollama-сервер (только если это наш процесс)"""
        if not self._is_our_process:
            return  # Не наш процесс — не трогаем

        if self.process:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(1000)

        # Удаляем PID-файл
        if self._pid_path and os.path.exists(self._pid_path):
            try:
                os.remove(self._pid_path)
            except Exception:
                pass

        # Закрываем лог
        self._close_log_file()

        self._is_our_process = False
        self.stopped.emit()

    def is_running(self) -> bool:
        """Проверяет, запущен ли Ollama (по порту)"""
        return self._is_port_busy()

    def is_our_process(self) -> bool:
        """Возвращает True, если это наш процесс"""
        return self._is_our_process

    def _get_ollama_binary(self) -> str:
        """Возвращает путь к бинарнику Ollama"""
        # 1. Локальный бинарник (из конфига)
        local_bin = self.config.get_ollama_binary_path()
        if os.path.exists(local_bin):
            return local_bin
        # 2. Системный путь
        import shutil
        system_bin = shutil.which("ollama")
        if system_bin:
            return system_bin
        return None

    def _start_process(self, ollama_bin: str):
        """Запускает QProcess с ollama serve"""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Открываем файл лога
        log_dir = os.path.join(app_dir, "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._log_path = os.path.join(log_dir, "ollama.log")

        try:
            self._log_file = open(self._log_path, "a", encoding="utf-8")
            self._log_file.write(
                f"\n=== Ollama started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )
            self._log_file.flush()
        except Exception as e:
            print(f"[OllamaManager] Не удалось открыть файл лога: {e}")
            self._log_file = None

        # Создаём PID-файл
        pid_dir = os.path.join(app_dir, "data", "pids")
        os.makedirs(pid_dir, exist_ok=True)
        self._pid_path = os.path.join(pid_dir, "ollama.pid")

        # Запускаем процесс
        self.process = QProcess()
        self.process.setProgram(ollama_bin)
        self.process.setArguments(["serve"])

        # Передаём переменные окружения
        env = QProcessEnvironment.systemEnvironment()
        models_path = self.config.get(
            "ollama/models_path",
            "/run/media/lin/DATA/Program Files/Ollama/"
        )
        env.insert("OLLAMA_MODELS", models_path)
        env.insert("OLLAMA_HOST", "127.0.0.1:11434")
        
        # Данные Ollama (ключи, история) — в data/ollama/
        ollama_data_dir = self.config.get_ollama_data_dir()
        os.makedirs(ollama_data_dir, exist_ok=True)
        env.insert("OLLAMA_DATA_DIR", ollama_data_dir)
        
        # Библиотеки (CUDA, ROCm) — в bin/ollama/lib/ollama/
        lib_dir = self.config.get_ollama_lib_dir()
        if os.path.exists(lib_dir):
            current_ld_path = env.value("LD_LIBRARY_PATH", "")
            if current_ld_path:
                env.insert("LD_LIBRARY_PATH", f"{lib_dir}:{current_ld_path}")
            else:
                env.insert("LD_LIBRARY_PATH", lib_dir)
        self.process.setProcessEnvironment(env)

        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.start()

        # Записываем PID
        pid = self.process.processId()
        try:
            with open(self._pid_path, "w") as f:
                f.write(str(pid))
        except Exception:
            pass

        self._is_our_process = True

        # Ждём готовности
        self._wait_ready()

    def _on_output(self):
        """Обрабатывает вывод процесса"""
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Пишем в лог
            if self._log_file:
                try:
                    self._log_file.write(line + '\n')
                    self._log_file.flush()
                except Exception:
                    pass

            # Эмитим сигнал
            self.log_line.emit(line)

    def _on_finished(self, exit_code, exit_status):
        """Процесс завершён"""
        self._close_log_file()

        if exit_code != 0 and exit_code != 15:  # 15 = SIGTERM
            self.error.emit(f"Ollama завершился с кодом {exit_code}")

        self._is_our_process = False
        self.stopped.emit()

    def _on_process_error(self, error):
        """Ошибка запуска процесса"""
        self.error.emit(f"Ошибка запуска Ollama: {error}")

    def _close_log_file(self):
        """Закрывает файл лога"""
        if self._log_file:
            try:
                self._log_file.write(
                    f"\n=== Ollama stopped at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _is_port_busy(self) -> bool:
        """Проверяет, занят ли порт 11434"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 11434))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _wait_ready(self, timeout=30):
        """Ждёт, пока Ollama станет доступен"""
        start = time.time()
        while time.time() - start < timeout:
            if self._is_port_busy():
                # Записываем PID (на случай, если процесс ещё не записал)
                if self.process:
                    pid = self.process.processId()
                    try:
                        with open(self._pid_path, "w") as f:
                            f.write(str(pid))
                    except Exception:
                        pass
                self.started.emit()
                return
            time.sleep(0.5)
        self.error.emit("Ollama не запустился за 30 секунд")
