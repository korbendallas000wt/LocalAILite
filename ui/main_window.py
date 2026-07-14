from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget, QMenuBar, QMessageBox
from PyQt6.QtGui import QAction
from ui.tabs.ollama_tab import OllamaTab
from ui.tabs.diffusers_tab import DiffusersTab
from ui.tabs.image_prep_tab import ImagePrepTab
from ui.shared_bottom_bar import SharedBottomBar
from ui.dialogs.settings.settings_dialog import SettingsDialog
from utils.config import Config
from core.resource_manager import ResourceManager
from core.path_validator import PathValidator
from core.ollama_manager import OllamaManager
import os

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalAILite")
        self.resize(1100, 700)
        
        self.config = Config()
        self.resource_manager = ResourceManager()
        self.resource_manager.resource_acquired.connect(self._on_resource_acquired)
        self.resource_manager.resource_released.connect(self._on_resource_released)
        
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)
        
        self.ollama_tab = OllamaTab(self.config, self.resource_manager)
        self.tabs.addTab(self.ollama_tab, "💬 Ollama Chat")
        
        self.diffusers_tab = DiffusersTab(self.config, self.resource_manager)
        self.tabs.addTab(self.diffusers_tab, "🎨 Diffusers")
        
        self.image_prep_tab = ImagePrepTab(self.config, self.resource_manager)
        self.tabs.addTab(self.image_prep_tab, "Visual editor")
        
        self.shared_bar = SharedBottomBar()
        main_layout.addWidget(self.shared_bar)
        
        # Синхронизация радиокнопок с табами
        self.shared_bar.ollama_radio.toggled.connect(self._on_radio_toggled)
        self.shared_bar.diffusers_radio.toggled.connect(self._on_radio_toggled)
        
        self.setCentralWidget(central_widget)
        
        self.resource_manager.register_module("ollama", self.ollama_tab)
        self.resource_manager.register_module("diffusers", self.diffusers_tab)
        self.resource_manager.register_module("image_prep", self.image_prep_tab)
        
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
        self.image_prep_tab.state_changed.connect(self._on_tab_state_changed)
        
        self._create_menu()
        self._restore_bar_state()
        
        # Восстанавливаем состояние первого таба
        first_tab = self.tabs.widget(0)
        if hasattr(first_tab, '_bar_state'):
            state = first_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_status(state["status"], state.get("status_color"))
        
        self._update_status()
        
        # Запускаем Ollama
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
            self._set_active_tab_status(f"⚠ Настройте пути: {', '.join(errors)}", "orange")
        else:
            self._set_active_tab_status("Готово", "green")
    
    def _on_tab_changed(self, index):
        """Переключение табов"""
        active_tab = self.tabs.currentWidget()
        
        # Переключение табов свободно, блокировка только на кнопке запуска
        prev_tab = self.tabs.widget(self._prev_index)
        if hasattr(prev_tab, '_bar_state'):
            prev_tab._bar_state["prompt"] = self.shared_bar.get_prompt()
        
        self.resource_manager.on_tab_changed(index)
        
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            state = active_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
            self.shared_bar.set_status(state["status"], state.get("status_color"))
            
            if state["is_running"]:
                self.shared_bar.start_timer()
            else:
                self.shared_bar.stop_timer()
        
        self._prev_index = index
        
        # Синхронизируем радиокнопки с активным табом
        self._sync_radio_with_tab(index)
    
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
            self.shared_bar.set_status(state["status"], state.get("status_color"))
        
        if state.get("is_running"):
            self.shared_bar.start_timer()
            self.shared_bar.set_running_state(True)

        else:
            self.shared_bar.stop_timer()
            self.shared_bar.set_running_state(False)
    def _set_active_tab_status(self, message: str, color: str = "#DAA520"):
        """Устанавливает статус через активный таб (не напрямую в SharedBottomBar)"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_set_status'):
            active_tab._set_status(message, color)
        else:
            self.shared_bar.stop_timer()
            self.shared_bar.set_running_state(False)
    
    def _on_blocked_action(self, text):
        """Действие заблокировано"""
        self._set_active_tab_status(text, "red")
    
    def on_prompt_submitted(self, prompt):
        """Отправляет промпт в активный модуль"""
        active_tab = self.tabs.currentWidget()
        
        if self.resource_manager.is_resource_busy():
            owner = self.resource_manager.get_resource_owner()
            self._set_active_tab_status(f"⚠ Ресурс занят: {owner}", "red")
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
                
                # Сбрасываем is_running при старте
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
            self.ollama_tab._set_status("✅ Ollama запущен (наш процесс)", "green")
        else:
            self.ollama_tab._set_status("✅ Ollama подключён (внешний)", "green")
    
    def _on_ollama_stopped(self):
        """Ollama остановлен"""
        self.ollama_tab._set_status("Ollama остановлен", "gray")
    
    def _on_ollama_error(self, error_msg):
        """Ошибка Ollama"""
        self.ollama_tab._set_status(f"⚠ Ollama: {error_msg}", "red")
    
    def _on_ollama_log(self, line):
        """Строка лога Ollama"""
        if any(kw in line.lower() for kw in ["error", "listening", "started", "loaded"]):
            self.ollama_tab._set_status(f"Ollama: {line[:80]}", "gray")
    
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
            self.ollama_tab._set_status("⚠ Ollama не установлен", "orange")
    
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
            self.ollama_tab._set_status("Убиваем существующий Ollama...", "#DAA520")
            self.ollama_manager.kill_existing_and_start()
        else:
            self.ollama_tab._set_status("⚠ Ollama: конфликт не разрешён", "orange")
    
    def _download_ollama(self):
        """Скачивает Ollama"""
        self.ollama_tab._set_status("⚠ Скачивание Ollama пока не реализовано", "orange")
    
    def _sync_radio_with_tab(self, index):
        """Синхронизирует радиокнопки с активным табом"""
        self.shared_bar.ollama_radio.blockSignals(True)
        self.shared_bar.diffusers_radio.blockSignals(True)
        
        if index == 0:  # Ollama
            self.shared_bar.ollama_radio.setChecked(True)
        elif index == 1:  # Diffusers
            self.shared_bar.diffusers_radio.setChecked(True)
        elif index == 2:  # Visual Editor
            self.shared_bar.diffusers_radio.setChecked(True)
        
        self.shared_bar.ollama_radio.blockSignals(False)
        self.shared_bar.diffusers_radio.blockSignals(False)
    
    def _on_radio_toggled(self, checked):
        """Обработка клика по радиокнопке"""
        if not checked:
            return
        
        sender = self.sender()
        if sender == self.shared_bar.ollama_radio:
            target_index = 0
        elif sender == self.shared_bar.diffusers_radio:
            target_index = 1
        else:
            return
        
        if self.tabs.currentIndex() != target_index:
            self.tabs.setCurrentIndex(target_index)
    
    
    
    
    
    
    
    def closeEvent(self, event):
        """Показывает диалог очистки при закрытии"""
        # Сохраняем состояние
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            active_tab._bar_state["prompt"] = self.shared_bar.get_prompt()
        
        self._save_bar_state()
        
        # Показываем диалог очистки
        from ui.cleanup_dialog import CleanupDialog
        cleanup_dialog = CleanupDialog(
            self.ollama_tab,
            self.diffusers_tab,
            self.config,
            self.ollama_manager,
            self
        )
        
        # Блокируем закрытие до завершения очистки
        event.ignore()
        
        # После закрытия диалога — выходим
        if cleanup_dialog.exec():
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()
    
    def _on_resource_acquired(self, module_name):
        """Ресурс захвачен модулем"""
        self.shared_bar.set_resource_state(True, module_name)
        self._set_active_tab_status(f"⚠ {module_name}: генерация...", "orange")
    
    def _on_resource_released(self):
        """Ресурс освобождён"""
        self.shared_bar.set_resource_state(False)
        self._set_active_tab_status("Готово", "green")
