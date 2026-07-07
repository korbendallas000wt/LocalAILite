from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget, QMenuBar, QMessageBox
from PyQt6.QtGui import QAction
from ui.tabs.ollama_tab import OllamaTab
from ui.tabs.diffusers_tab import DiffusersTab
from ui.shared_bottom_bar import SharedBottomBar
from ui.dialogs.settings.settings_dialog import SettingsDialog
from utils.config import Config
from core.resource_manager import ResourceManager
from core.path_validator import PathValidator
from core.ollama_manager import OllamaManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalAILite")
        self.resize(1100, 700)

        self.config = Config()
        self.resource_manager = ResourceManager()

        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        self.ollama_tab = OllamaTab(self.config)
        self.tabs.addTab(self.ollama_tab, "💬 Ollama Chat")

        self.diffusers_tab = DiffusersTab(self.config)
        self.tabs.addTab(self.diffusers_tab, "🎨 Diffusers")

        self.shared_bar = SharedBottomBar()
        main_layout.addWidget(self.shared_bar)

        self.setCentralWidget(central_widget)

        self.resource_manager.register_module("ollama", self.ollama_tab)
        self.resource_manager.register_module("diffusers", self.diffusers_tab)

        # === Ollama Manager ===
        self.ollama_manager = OllamaManager(self.config)
        self.ollama_manager.started.connect(self._on_ollama_started)
        self.ollama_manager.stopped.connect(self._on_ollama_stopped)
        self.ollama_manager.error.connect(self._on_ollama_error)
        self.ollama_manager.log_line.connect(self._on_ollama_log)
        self.ollama_manager.needs_install.connect(self._on_ollama_needs_install)
        self.ollama_manager.conflict_detected.connect(self._on_ollama_conflict)

        # === Подключение сигналов ===
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._prev_index = 0

        self.shared_bar.prompt_changed.connect(self._on_prompt_changed)
        self.shared_bar.prompt_submitted.connect(self.on_prompt_submitted)
        self.shared_bar.generation_stopped.connect(self.on_generation_stopped)
        self.shared_bar.blocked_action.connect(self._on_blocked_action)

        # Универсальные сигналы состояния от табов
        self.ollama_tab.state_changed.connect(self._on_tab_state_changed)
        self.diffusers_tab.state_changed.connect(self._on_tab_state_changed)

        self._create_menu()
        self._restore_bar_state()

        # Восстанавливаем состояние первого таба
        first_tab = self.tabs.widget(0)
        if hasattr(first_tab, '_bar_state'):
            state = first_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_end_label(state["end_label"])
            self.shared_bar.set_status(state["status"])

        self._update_status()

        # Запускаем Ollama (после показа окна, чтобы диалоги не блокировали)
        # Используем QTimer.singleShot, чтобы окно успело отрисоваться
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.ollama_manager.start)

    def _create_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Файл")
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("Настройки")
        settings_action = QAction("Настройки...", self)
        settings_action.triggered.connect(self._show_settings_dialog)
        settings_menu.addAction(settings_action)

    def _show_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self._update_status()

    def _update_status(self):
        validator = PathValidator()
        result = validator.validate_all(self.config)
        if not result["all_valid"]:
            errors = []
            if not result["venv"]["valid"]:
                errors.append("venv")
            if not result["models"]["valid"]:
                errors.append("модели")
            if not result["output"]["valid"]:
                errors.append("папка сохранения")
            if not result["ollama"]["valid"]:
                errors.append("Ollama")
            self.shared_bar.set_status(f"⚠ Настройте пути: {', '.join(errors)}", "orange")
        else:
            self.shared_bar.set_status("Готово")

    def _on_tab_changed(self, index):
        """Переключение табов"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state') and active_tab._bar_state["is_running"]:
            self.shared_bar.set_status("⚠ Идёт генерация, дождитесь завершения", "red")
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._prev_index)
            self.tabs.blockSignals(False)
            return

        prev_tab = self.tabs.widget(self._prev_index)
        if hasattr(prev_tab, '_bar_state'):
            prev_tab._bar_state["prompt"] = self.shared_bar.get_prompt()

        self.resource_manager.on_tab_changed(index)

        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            state = active_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_end_label(state["end_label"])
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
            self.shared_bar.set_status(state["status"])
            if state["is_running"]:
                self.shared_bar.start_timer()
            else:
                self.shared_bar.stop_timer()

        self._prev_index = index

    def _on_prompt_changed(self, text):
        """Изменение промпта"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            active_tab._bar_state["prompt"] = text

    def _on_tab_state_changed(self, state):
        """Изменение состояния таба"""
        sender = self.sender()
        if sender != self.tabs.currentWidget():
            return

        if "prompt" in state:
            self.shared_bar.set_prompt(state["prompt"])
        if "progress_current" in state and "progress_total" in state:
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
        if "status" in state:
            self.shared_bar.set_status(state["status"])
        if "end_label" in state:
            self.shared_bar.set_end_label(state["end_label"])

        if state.get("is_running"):
            self.shared_bar.start_timer()
            self.shared_bar.set_running_state(True)
        else:
            self.shared_bar.stop_timer()
            self.shared_bar.set_running_state(False)

    def _on_blocked_action(self, text):
        """Действие заблокировано"""
        self.shared_bar.set_status(text, "red")

    def on_prompt_submitted(self, prompt):
        """Отправляет промпт в активный модуль"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state') and active_tab._bar_state["is_running"]:
            self.shared_bar.set_status("⚠ Дождитесь завершения текущей генерации", "red")
            return

        if hasattr(active_tab, 'handle_prompt'):
            active_tab.handle_prompt(prompt)

    def on_generation_stopped(self):
        """Останавливает генерацию в активном модуле"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, 'stop_generation'):
            active_tab.stop_generation()

    def _restore_bar_state(self):
        """Восстановление состояния табов из QSettings"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, '_bar_state'):
                tab_name = "ollama" if i == 0 else "diffusers"
                saved_state = self.config.get_json(f"bar_state/{tab_name}")
                if saved_state:
                    for key in tab._bar_state.keys():
                        if key in saved_state:
                            tab._bar_state[key] = saved_state[key]
                # Сбрасываем is_running при старте — генерация не может продолжаться после перезапуска
                tab._bar_state["is_running"] = False

    def _save_bar_state(self):
        """Сохранение состояния табов в QSettings"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, '_bar_state'):
                tab_name = "ollama" if i == 0 else "diffusers"
                self.config.set_json(f"bar_state/{tab_name}", tab._bar_state)

    # === Ollama Manager handlers ===

    def _on_ollama_started(self):
        """Ollama запущен и готов"""
        if self.ollama_manager.is_our_process():
            self.shared_bar.set_status("✅ Ollama запущен (наш процесс)", "green")
        else:
            self.shared_bar.set_status("✅ Ollama подключён (внешний)", "green")

    def _on_ollama_stopped(self):
        """Ollama остановлен"""
        self.shared_bar.set_status("Ollama остановлен")

    def _on_ollama_error(self, error_msg):
        """Ошибка Ollama"""
        self.shared_bar.set_status(f"⚠ Ollama: {error_msg}", "red")

    def _on_ollama_log(self, line):
        """Строка лога Ollama — добавляем в бегущую строку статуса"""
        # Показываем только важные строки, чтобы не засорять статус
        if any(kw in line.lower() for kw in ["error", "listening", "started", "loaded"]):
            self.shared_bar.set_status(f"Ollama: {line[:80]}", "gray")

    def _on_ollama_needs_install(self):
        """Требуется установка Ollama"""
        reply = QMessageBox.question(
            self,
            "Ollama не найден",
            "Ollama не установлен.\n\n"
            "Скачать и установить? (~1 GB)\n\n"
            "Бинарник будет сохранён в папке приложения (bin/ollama).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_ollama()
        else:
            self.shared_bar.set_status("⚠ Ollama не установлен", "orange")

    def _on_ollama_conflict(self):
        """Обнаружен конфликт — Ollama уже запущен"""
        reply = QMessageBox.question(
            self,
            "Ollama уже запущен",
            "Ollama-сервер уже запущен (возможно, через systemd).\n\n"
            "• Да — использовать существующий сервер\n"
            "• Нет — убить его и запустить свой\n"
            "• Отмена — не использовать Ollama",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.ollama_manager.use_existing()
        elif reply == QMessageBox.StandardButton.No:
            self.shared_bar.set_status("Убиваем существующий Ollama...")
            self.ollama_manager.kill_existing_and_start()
        else:
            self.shared_bar.set_status("⚠ Ollama: конфликт не разрешён", "orange")

    def _download_ollama(self):
        """Скачивает Ollama"""
        # TODO: Реализовать скачивание через QThread + прогрессбар
        self.shared_bar.set_status("⚠ Скачивание Ollama пока не реализовано", "orange")

    def closeEvent(self, event):
        """Показывает диалог очистки при закрытии"""
        # Сохраняем состояние
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            active_tab._bar_state["prompt"] = self.shared_bar.get_prompt()
        self._save_bar_state()

        # Отменяем закрытие и скрываем окно
        event.ignore()
        self.hide()

        # Показываем диалог очистки
        from ui.cleanup_dialog import CleanupDialog
        cleanup_dialog = CleanupDialog(
            self.ollama_tab,
            self.diffusers_tab,
            self.config,
            self.ollama_manager,
            self
        )

        # После закрытия диалога — выходим
        if cleanup_dialog.exec():
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()
