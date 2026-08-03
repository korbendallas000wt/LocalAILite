from PyQt6.QtCore import QObject, QProcess, pyqtSignal
import json
import os
from datetime import datetime
from core import history_manager
from core.resource_monitor import ResourceMonitor

class DiffusersWorker(QObject):
    step_updated = pyqtSignal(int, int, str)      # step, total, image_path
    generation_finished = pyqtSignal(str, int)    # final_path, seed
    error_occurred = pyqtSignal(str)
    status_message = pyqtSignal(str)              # статусное сообщение для UI
    log_line = pyqtSignal(str)                    # каждая строка вывода

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self._stopped_by_user = False
        self._log_file = None
        self._log_path = None

    def start(self, prompt, negative_prompt, params, resume=False,
              history_dir=None, step_file=None, start_step=0):
        """Запускает процесс генерации"""
        self._stopped_by_user = False

        # === Открываем файл лога ===
        from utils.config import Config
        config = Config()
        log_dir = config.get_logs_dir()
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        self._log_path = os.path.join(log_dir, f"diffusers_{date_str}.log")
        try:
            self._log_file = open(self._log_path, "a", encoding="utf-8")
            self._log_file.write(f"=== Diffusers Generation Log ===\n")
            self._log_file.write(f"Prompt: {prompt}\n")
            self._log_file.write(f"Negative: {negative_prompt}\n")
            self._log_file.write(f"Model: {params.get('model', '')}\n")
            self._log_file.write(f"Scheduler: {params.get('scheduler', '')}\n")
            self._log_file.write(f"Steps: {params.get('steps', 0)}\n")
            self._log_file.write(f"CFG: {params.get('cfg', 0)}\n")
            self._log_file.write(f"Size: {params.get('width', 0)}x{params.get('height', 0)}\n")
            self._log_file.write(f"Seed: {params.get('seed', -1)}\n")
            self._log_file.write(f"Device: {self.config.get('sdxl/device', 'cuda')}\n")
            self._log_file.write(f"Resume: {resume}\n")
            self._log_file.write(f"Resume history_dir: {history_dir}\n")
            self._log_file.write(f"Resume step_file: {step_file}\n")
            self._log_file.write(f"Resume start_step: {start_step}\n")
            self._log_file.write(f"Preview every: {params.get('preview_every', 0)}\n")
            self._log_file.write(f"Preview start: {params.get('preview_start', 1)}\n")
            self._log_file.write(f"Output dir: {self.config.get_sdxl_output_dir()}\n")
            self._log_file.write("=" * 40 + "\n\n")
            self._log_file.flush()
        except Exception as e:
            print(f"[DiffusersWorker] Не удалось открыть файл лога: {e}")
            self._log_file = None

        # === Создаём или используем существующую папку истории ===
        if resume and history_dir:
            # При resume — используем существующую папку
            self._history_dir = history_dir
            print(f"[DiffusersWorker] Resuming to existing history folder: {self._history_dir}")
        else:
            # При обычной генерации — создаём новую папку
            self._history_dir = history_manager.create_history_folder()
            print(f"[DiffusersWorker] New history folder: {self._history_dir}")

        venv_path = self.config.get_sdxl_venv_path()
        if not venv_path:
            self.error_occurred.emit("Не указан путь к venv для Diffusers")
            self._close_log_file()
            return

        python_path = os.path.join(venv_path, "bin", "python")
        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_diffusers.py")
        script_path = os.path.abspath(script_path)
        if not os.path.exists(script_path):
            self.error_occurred.emit(f"Скрипт не найден: {script_path}")
            self._close_log_file()
            return

        # Получаем путь к папке моделей (для cache_dir)
        models_path = self.config.get_sdxl_models_path()
        
        # Определяем полный путь к модели через реестр
        model_name = params["model"]
        from core.models_registry import get_model_path_by_name
        model_path = get_model_path_by_name(self.config, model_name)
        
        if not model_path:
            # Fallback: используем имя как есть
            model_path = model_name

        args = [
            script_path,
            "--prompt", prompt,
            "--negative", negative_prompt,
            "--model", model_path,
            "--scheduler", params["scheduler"],
            "--steps", str(params["steps"]),
            "--cfg", str(params["cfg"]),
            "--width", str(params["width"]),
            "--height", str(params["height"]),
            "--seed", str(params["seed"]),
            "--device", self.config.get("sdxl/device", "cuda"),
            "--preview-every", str(params.get("preview_every", 0)),
            "--preview-start", str(params.get("preview_start", 1)),
            "--output_dir", self.config.get_sdxl_output_dir(),
            "--preview-dir", self.config.get_previews_dir(),
            "--history-dir", self._history_dir,
            "--cache_dir", models_path
        ]
        if self.config.get("sdxl/no_safety_checker", "false") == "true":
            args.append("--no-safety-checker")
        if resume:
            args.append("--resume")
            if history_dir:
                args.extend(["--resume-history-dir", history_dir])
            if step_file:
                args.extend(["--resume-step-file", step_file])
            args.extend(["--resume-start-step", str(start_step)])

        # === Проверка RAM ===
        monitor = ResourceMonitor(self.config)
        required_ram = monitor.estimate_diffusers_ram(
            params.get("width", 1024),
            params.get("height", 1024),
            params.get("model", "")
        )
        ram_check = monitor.check_ram_available(required_ram)
        if not ram_check["ok"]:
            self.error_occurred.emit(f"Недостаточно RAM: {ram_check['message']}")
            self._close_log_file()
            return
        print(f"[DiffusersWorker] RAM check: OK, available: {ram_check['available_gb']:.1f} GB", flush=True)

        # === Применяем лимиты CPU ===
        limits = monitor.get_limits()
        cpu_env = monitor.get_env_for_cpu_limits(limits["cpu_cores"])

        self.process = QProcess()
        self.process.setProgram(python_path)
        self.process.setArguments(args)
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

        # Применяем CPU affinity и priority к запущенному процессу
        pid = self.process.processId()
        if pid > 0:
            ResourceMonitor.apply_cpu_affinity(pid, limits["cpu_cores"])
            ResourceMonitor.apply_priority(pid, limits["cpu_priority"])
            print(f"[DiffusersWorker] CPU limits applied: cores={limits['cpu_cores']}, priority={limits['cpu_priority']}", flush=True)
            
            # Сохраняем PID в файл
            from utils.config import Config
            config = Config()
            pid_dir = os.path.join(config.get_data_dir(), "pids")
            os.makedirs(pid_dir, exist_ok=True)
            pid_path = os.path.join(pid_dir, "diffusers.pid")
            try:
                with open(pid_path, "w") as f:
                    f.write(str(pid))
            except Exception as e:
                print(f"[DiffusersWorker] Не удалось сохранить PID: {e}")

    def get_history_dir(self):
        """Возвращает путь к папке истории текущей генерации"""
        return getattr(self, '_history_dir', None)

    def stop(self):
        """Останавливает процесс (ручная остановка пользователем)"""
        self._stopped_by_user = True
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
        # Удаляем PID-файл
        from utils.config import Config
        config = Config()
        pid_path = os.path.join(config.get_data_dir(), "pids", "diffusers.pid")
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
            except Exception:
                pass
        
        self._close_log_file()
        self.generation_finished.emit("", -1)

    def _close_log_file(self):
        """Закрывает файл лога"""
        if self._log_file:
            try:
                self._log_file.write("\n=== Generation finished ===\n")
                self._log_file.write(f"Log saved to: {self._log_path}\n")
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _on_output(self):
        """Обрабатывает ВСЕ строки вывода процесса"""
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 1. Пишем в файл лога
            if self._log_file:
                try:
                    self._log_file.write(line + '\n')
                    self._log_file.flush()
                except Exception:
                    pass
            # 2. Эмитим сигнал для бегущей строки в UI
            self.log_line.emit(line)
            # 3. Пытаемся распарсить JSON (для UI)
            try:
                msg = json.loads(line)
                msg_type = msg.get("type")
                if msg_type == "step":
                    step = msg.get("step", 0)
                    total = msg.get("total", 0)
                    image_path = msg.get("image_path", "")
                    self.step_updated.emit(step, total, image_path)
                elif msg_type == "done":
                    final_path = msg.get("final_path", "")
                    seed = msg.get("seed", -1)
                    self.generation_finished.emit(final_path, seed)
                elif msg_type == "error":
                    error_msg = msg.get("message", "Неизвестная ошибка")
                    self.error_occurred.emit(error_msg)
                elif msg_type == "status":
                    status_msg = msg.get("message", "")
                    self.status_message.emit(status_msg)
                elif msg_type == "warning":
                    warning_msg = msg.get("message", "")
                    self.status_message.emit(f"⚠ {warning_msg}")
            except json.JSONDecodeError:
                pass

    def _on_finished(self, exit_code, exit_status):
        """Процесс завершён"""
        self._close_log_file()
        if self._stopped_by_user:
            return
        # Дочитываем оставшийся вывод
        remaining = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        if remaining.strip():
            for line in remaining.split('\n'):
                if line.strip():
                    self.log_line.emit(line.strip())
                    try:
                        msg = json.loads(line.strip())
                        msg_type = msg.get("type")
                        if msg_type == "done":
                            self.generation_finished.emit(
                                msg.get("final_path", ""),
                                msg.get("seed", -1)
                            )
                        elif msg_type == "error":
                            self.error_occurred.emit(msg.get("message", "Неизвестная ошибка"))
                        elif msg_type == "status":
                            self.status_message.emit(msg.get("message", ""))
                    except json.JSONDecodeError:
                        pass
        # Игнорируем код 15 (SIGTERM — нормальная остановка)
        if exit_code != 0 and exit_code != 15:
            self.error_occurred.emit(f"Процесс завершился с кодом {exit_code}")

    def _on_process_error(self, error):
        """Ошибка запуска процесса"""
        if self._stopped_by_user:
            return
        if error == QProcess.ProcessError.Crashed:
            return
        self.error_occurred.emit(f"Ошибка запуска: {error}")
