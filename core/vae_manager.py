"""
Менеджер VAE Decoder — отдельный арендатор ресурсов.
Запускает vae_decoder_daemon.py для декодирования latents в PNG.
Работает наравне с Ollama и Diffusers через ResourceManager.
"""
from PyQt6.QtCore import QObject, QProcess, pyqtSignal
import os
from core.resource_monitor import ResourceMonitor

class VAEManager(QObject):
    """Управляет процессом VAE Decoder"""
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log_line = pyqtSignal(str)
    decode_completed = pyqtSignal(str)  # путь к сохранённому PNG

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self._is_running = False

    def decode_step(self, history_dir: str, model_path: str, step_number: int, timeout: int = 300):
        """
        Запускает VAE decoder для конкретного шага.
        Args:
            history_dir: папка с .pt файлами
            model_path: путь к модели SDXL
            step_number: номер шага для декодирования
            timeout: таймаут в секундах (0 = ждать всегда)
        """
        if self._is_running:
            self.error.emit("VAE decoder уже запущен")
            return

        # Проверяем наличие .pt файла
        pt_file = os.path.join(history_dir, f"step_{step_number:04d}.pt")
        if not os.path.exists(pt_file):
            self.error.emit(f"Файл не найден: step_{step_number:04d}.pt")
            return

        venv_path = self.config.get_sdxl_venv_path()
        if not venv_path:
            self.error.emit("Не указан путь к venv для Diffusers")
            return

        python_path = os.path.join(venv_path, "bin", "python")
        daemon_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts", "vae_decoder_daemon.py"
        )
        daemon_script = os.path.abspath(daemon_script)
        if not os.path.exists(daemon_script):
            self.error.emit(f"Скрипт не найден: {daemon_script}")
            return

        # === Применяем лимиты CPU ===
        monitor = ResourceMonitor(self.config)
        limits = monitor.get_limits()
        cpu_env = monitor.get_env_for_cpu_limits(limits["cpu_cores"])

        # Аргументы: декодируем только один файл
        daemon_args = [
            daemon_script,
            "--history_dir", history_dir,
            "--model", model_path,
            "--device", self.config.get("sdxl/device", "cuda"),
            "--cache_dir", self.config.get_sdxl_models_path(),
            "--timeout", str(timeout),
            "--single_file", f"step_{step_number:04d}.pt"  # новый параметр
        ]

        self.process = QProcess()
        self.process.setProgram(python_path)
        self.process.setArguments(daemon_args)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # Передаём env переменные для ограничения CPU
        env = self.process.processEnvironment()
        for key, value in cpu_env.items():
            env.insert(key, value)
        self.process.setProcessEnvironment(env)

        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.start()

        # Применяем CPU affinity и priority
        pid = self.process.processId()
        if pid > 0:
            ResourceMonitor.apply_cpu_affinity(pid, limits["cpu_cores"])
            ResourceMonitor.apply_priority(pid, limits["cpu_priority"])

        self._is_running = True
        self.started.emit()

    def stop(self):
        """Останавливает VAE decoder"""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
        self._is_running = False

    def is_running(self) -> bool:
        """Проверяет, запущен ли VAE decoder"""
        return self._is_running

    def _on_output(self):
        """Обрабатывает вывод процесса"""
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue
            self.log_line.emit(line)
            # Проверяем завершение декодирования
            if line.startswith("[VAE_DAEMON] Saved:"):
                png_file = line.split("Saved:")[1].strip()
                self.decode_completed.emit(png_file)

    def _on_finished(self, exit_code, exit_status):
        """Процесс завершён"""
        self._is_running = False
        if exit_code != 0 and exit_code != 15:
            self.error.emit(f"VAE decoder завершился с кодом {exit_code}")
        self.finished.emit()

    def _on_process_error(self, error):
        """Ошибка запуска процесса"""
        self._is_running = False
        self.error.emit(f"Ошибка запуска VAE decoder: {error}")
