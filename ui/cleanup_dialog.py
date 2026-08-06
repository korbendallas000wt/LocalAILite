from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar,
                             QPushButton, QApplication)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtCore import QProcess
import os


class CleanupThread(QThread):
    """Поток для выполнения очистки ресурсов"""
    step_started = pyqtSignal(str)         # название шага
    step_finished = pyqtSignal(bool, str)  # успех, сообщение
    all_done = pyqtSignal()                # всё завершено

    def __init__(self, ollama_tab, diffusers_tab, config, ollama_manager, manual_mode=False):
        super().__init__()
        self.ollama_tab = ollama_tab
        self.diffusers_tab = diffusers_tab
        self.config = config
        self.ollama_manager = ollama_manager
        self.manual_mode = manual_mode

    def run(self):
        """Выполняет все шаги очистки"""
        # === Шаг 1: Остановка DiffusersWorker ===
        self.step_started.emit("Остановка Diffusers...")
        try:
            # 1.1. Пытаемся остановить через worker (если существует)
            if self.diffusers_tab and self.diffusers_tab.worker:
                if self.diffusers_tab.worker.process:
                    state = self.diffusers_tab.worker.process.state()
                    if state == QProcess.ProcessState.Running:
                        self.diffusers_tab.worker.process.terminate()
                        if not self.diffusers_tab.worker.process.waitForFinished(2000):
                            self.diffusers_tab.worker.process.kill()
                            self.diffusers_tab.worker.process.waitForFinished(1000)
                # Закрываем файл лога
                self.diffusers_tab.worker._close_log_file()
                self.diffusers_tab.worker = None
            
            # 1.2. Проверяем PID-файл (на случай, если worker потерялся)
            from core.resource_monitor import ResourceMonitor
            pid_path = os.path.join(self.config.get_data_dir(), "pids", "diffusers.pid")
            pid = ResourceMonitor.read_pid_file(pid_path)
            if pid > 0 and ResourceMonitor.is_process_alive(pid):
                ResourceMonitor.kill_process_by_pid(pid, force=True)
                self.step_finished.emit(True, f"Diffusers убит по PID ({pid})")
            elif os.path.exists(pid_path):
                os.remove(pid_path)
                self.step_finished.emit(True, "Diffusers остановлен")
            else:
                self.step_finished.emit(True, "Diffusers не запущен")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 2: Выгрузка модели Ollama (через API) ===
        self.step_started.emit("Выгрузка модели Ollama...")
        try:
            # Усечённое приложение: если таба Ollama нет — пропускаем
            if not self.ollama_tab:
                self.step_finished.emit(True, "Ollama: компонент не установлен (пропуск)")
            else:
                # Останавливаем клиент, если работает
                if self.ollama_tab.client and self.ollama_tab.client.isRunning():
                    self.ollama_tab.client.stop()
                    if not self.ollama_tab.client.wait(1000):
                        self.ollama_tab.client.terminate()
                        self.ollama_tab.client.wait(500)

                # Выгружаем модель из Ollama (keep_alive=0)
                import requests
                model = self.ollama_tab.settings_panel.model_combo.currentText()
                if model:
                    requests.post(
                        f"{self.config.get_ollama_url()}/api/generate",
                        json={"model": model, "keep_alive": 0},
                        timeout=2
                    )

                # Проверяем, что модель выгружена
                res = requests.get(f"{self.config.get_ollama_url()}/api/ps", timeout=2)
                if res.status_code == 200:
                    running_models = res.json().get('models', [])
                    if len(running_models) == 0:
                        self.step_finished.emit(True, "Ollama: модель выгружена")
                    else:
                        self.step_finished.emit(
                            True,
                            f"Ollama: моделей в памяти — {len(running_models)}"
                        )
                else:
                    self.step_finished.emit(True, "Ollama: модель выгружена")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 3: Остановка Ollama-сервера (только если наш процесс) ===
        self.step_started.emit("Остановка Ollama-сервера...")
        try:
            if self.ollama_manager and self.ollama_manager.is_our_process():
                self.ollama_manager.stop()
                self.step_finished.emit(True, "Ollama-сервер остановлен")
            else:
                self.step_finished.emit(True, "Ollama-сервер: внешний (не трогаем)")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 4: Очистка памяти ===
        self.step_started.emit("Очистка памяти...")
        try:
            import gc
            gc.collect()

            try:
                import psutil
                mem = psutil.virtual_memory()
                available_gb = mem.available / (1024**3)
                self.step_finished.emit(
                    True,
                    f"Освобождено. Доступно: {available_gb:.1f} GB"
                )
            except ImportError:
                self.step_finished.emit(True, "Память очищена")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 5: Завершение ===
        self.step_started.emit("Завершение...")
        self.step_finished.emit(True, "Готово")
        self.all_done.emit()


class CleanupDialog(QDialog):
    """Диалог очистки ресурсов при закрытии"""
    def __init__(self, ollama_tab, diffusers_tab, config, ollama_manager, parent=None, manual_mode=False):
        super().__init__(parent)
        self.ollama_tab = ollama_tab
        self.diffusers_tab = diffusers_tab
        self.config = config
        self.ollama_manager = ollama_manager
        self.manual_mode = manual_mode

        self.setWindowTitle("Закрытие приложения")
        self.setFixedSize(400, 240)

        layout = QVBoxLayout(self)

        # Заголовок
        self.title_label = QLabel("Освобождение ресурсов...")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Прогресс-бар (5 шагов)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 5)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m")
        layout.addWidget(self.progress_bar)

        # Статус текущего шага
        self.status_label = QLabel("Подготовка...")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Список выполненных шагов
        self.steps_label = QLabel("")
        self.steps_label.setStyleSheet("font-size: 11px;")
        self.steps_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.steps_label)

        layout.addStretch()

        # Создаём поток очистки
        self.cleanup_thread = CleanupThread(
            ollama_tab, diffusers_tab, config, ollama_manager,
            manual_mode=manual_mode
        )
        self.cleanup_thread.step_started.connect(self._on_step_started)
        self.cleanup_thread.step_finished.connect(self._on_step_finished)
        self.cleanup_thread.all_done.connect(self._on_all_done)

        # Запускаем поток
        self.cleanup_thread.start()
        self._completed_steps = []

    def _on_step_started(self, step_name):
        """Начало шага"""
        self.status_label.setText(step_name)
        self.status_label.setStyleSheet("color: blue; font-size: 12px;")

    def _on_step_finished(self, success, message):
        """Шаг завершён"""
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        icon = "✅" if success else "❌"
        self._completed_steps.append(f"{icon} {message}")
        self.steps_label.setText("\n".join(self._completed_steps))

        if success:
            self.status_label.setStyleSheet("color: green; font-size: 12px;")
        else:
            self.status_label.setStyleSheet("color: red; font-size: 12px;")

    def _on_all_done(self):
        """Все шаги завершены"""
        self.title_label.setText("Завершено")
        self.status_label.setText("Все ресурсы освобождены")
        self.status_label.setStyleSheet(
            "color: green; font-size: 12px; font-weight: bold;"
        )
        # Автоматически закрываем через 1 секунду
        QTimer.singleShot(1000, self.accept)

    def closeEvent(self, event):
        """Блокируем закрытие диалога до завершения"""
        if self.cleanup_thread.isRunning():
            event.ignore()
        else:
            event.accept()
