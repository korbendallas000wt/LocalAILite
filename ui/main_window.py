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
        
        # === Условное создание табов по флагам features/* ===
        self.ollama_tab = None
        self.diffusers_tab = None
        self.image_prep_tab = None

        if self.config.get_feature("ollama", True):
            self.ollama_tab = OllamaTab(self.config, self.resource_manager)
            self.tabs.addTab(self.ollama_tab, "💬 Ollama Chat")
        
        if self.config.get_feature("sdxl", True):
            self.diffusers_tab = DiffusersTab(self.config, self.resource_manager)
            self.tabs.addTab(self.diffusers_tab, "🎨 Diffusers")
        
        if self.config.get_feature("image_prep", True):
            self.image_prep_tab = ImagePrepTab(self.config, self.resource_manager)
            self.tabs.addTab(self.image_prep_tab, "Visual editor")
        
        # Маппинг таб → имя модуля (для bar_state и on_tab_changed)
        self._tab_names = {}
        if self.ollama_tab:
            self._tab_names[id(self.ollama_tab)] = "ollama"
        if self.diffusers_tab:
            self._tab_names[id(self.diffusers_tab)] = "diffusers"
        if self.image_prep_tab:
            self._tab_names[id(self.image_prep_tab)] = "image_prep"

        self.shared_bar = SharedBottomBar()
        main_layout.addWidget(self.shared_bar)
        
        # Синхронизация радиокнопок с табами
        
        self.setCentralWidget(central_widget)
        
        if self.ollama_tab:
            self.resource_manager.register_module("ollama", self.ollama_tab)
        if self.diffusers_tab:
            self.resource_manager.register_module("diffusers", self.diffusers_tab)
        if self.image_prep_tab:
            self.resource_manager.register_module("image_prep", self.image_prep_tab)
        
        # === Ollama Manager (только если features/ollama) ===
        self.ollama_manager = None
        if self.ollama_tab:
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
        if self.ollama_tab:
            self.ollama_tab.state_changed.connect(self._on_tab_state_changed)
        if self.diffusers_tab:
            self.diffusers_tab.state_changed.connect(self._on_tab_state_changed)
        if self.image_prep_tab:
            self.image_prep_tab.state_changed.connect(self._on_tab_state_changed)
        
        self._create_menu()
        self._restore_bar_state()
        
        # Восстанавливаем состояние первого таба
        first_tab = self.tabs.widget(0)
        if first_tab and hasattr(first_tab, '_bar_state'):
            state = first_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
            self.shared_bar.set_status(state["status"], state.get("status_color"))
            if "elapsed_seconds" in state:
                self.shared_bar.set_timer_display(state["elapsed_seconds"])
        
        self._update_status()
        
        # Запускаем Ollama (только если компонент установлен)
        from PyQt6.QtCore import QTimer
        if self.ollama_manager:
            QTimer.singleShot(100, self.ollama_manager.start)

        # Проверка обновлений (через 3 сек после старта)
        from core.updater import Updater
        self.updater = Updater()
        self.updater.update_available.connect(self._on_update_available)
        self.updater.check_failed.connect(
            lambda err: print(f"Updater: проверка не удалась: {err}")
        )
        QTimer.singleShot(3000, self.updater.check_for_updates)
    
    def _create_menu(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("Файл")
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        self.settings_action = QAction("Настройки", self)
        self.settings_action.triggered.connect(self._show_settings_dialog)
        menubar.addAction(self.settings_action)
        
        # Освобождение ресурсов
        tools_menu = menubar.addMenu("Инструменты")
        cleanup_action = QAction("🧹 Освободить ресурсы", self)
        cleanup_action.triggered.connect(self._manual_cleanup)
        tools_menu.addAction(cleanup_action)
    
    def _show_settings_dialog(self):
        from core.paths_manager import PathsManager
        pm = PathsManager()
        # Сырые значения (без fallback на дефолты) для корректного детектирования
        old_raw = pm.get_raw_paths(self.config)

        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self._update_status()
            new_raw = pm.get_raw_paths(self.config)

            # Проверяем, изменились ли пути (сравниваем сырые значения)
            paths_changed = any(old_raw[k] != new_raw[k] for k in old_raw)
            if not paths_changed:
                return

            # Проверяем, занят ли ресурс генерацией
            if self.resource_manager.is_resource_busy():
                self._set_active_tab_status(
                    "⚠ Пути изменятся после завершения генерации", "orange"
                )
                return

            # Спрашиваем пользователя о перезагрузке
            reply = QMessageBox.question(
                self,
                "Пути изменены",
                "Пути к компонентам изменены.\n\n"
                "Перезагрузить сейчас?\n\n"
                "• Да — выгрузить модели и перезапустить\n"
                "• Нет — изменения применятся при следующем запуске",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._reload_paths_full()
    
    def _manual_cleanup(self):
        """Ручной вызов очистки ресурсов (без закрытия приложения)"""
        from ui.cleanup_dialog import CleanupDialog
        cleanup_dialog = CleanupDialog(
            self.ollama_tab,
            self.diffusers_tab,
            self.config,
            self.ollama_manager,
            self,
            manual_mode=True
        )
        cleanup_dialog.exec()
    
    def _reload_paths_light(self):
        """Лёгкая перезагрузка путей: обновить реестр моделей, перезапустить Ollama."""
        # 1. Обновить реестры моделей в обоих табах
        if self.diffusers_tab:
            self.diffusers_tab.settings_panel._load_models()
        if self.ollama_tab:
            self.ollama_tab.settings_panel.load_models()
        # 2. Перезапустить OllamaManager если это наш процесс
        if self.ollama_manager and self.ollama_manager.is_our_process():
            self.ollama_tab._set_status("Перезапуск Ollama...", "#DAA520")
            self.ollama_manager.stop()
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self.ollama_manager.start)
        self._update_status()

    def _reload_paths_full(self):
        """Полная перезагрузка: выгрузить модели, очистить память, перезапустить."""
        from ui.cleanup_dialog import CleanupDialog
        cleanup_dialog = CleanupDialog(
            self.ollama_tab,
            self.diffusers_tab,
            self.config,
            self.ollama_manager,
            self,
            manual_mode=True
        )
        cleanup_dialog.exec()
        # После очистки обновляем реестры моделей в обоих табах
        if self.diffusers_tab:
            self.diffusers_tab.settings_panel._load_models()
        if self.ollama_tab:
            self.ollama_tab.settings_panel.load_models()
        # Перезапускаем Ollama с новыми путями (надёжно: ждём освобождения порта)
        if self.ollama_manager:
            self._restart_ollama_after_cleanup()
        self._update_status()

    def _restart_ollama_after_cleanup(self):
        """Надёжный перезапуск Ollama после очистки (неблокирующий).
        Использует QTimer вместо time.sleep, чтобы не фризить UI.
        """
        from PyQt6.QtCore import QTimer
        self._restart_attempts = 0
        self._max_restart_attempts = 10
        self._check_port_timer = QTimer()
        self._check_port_timer.setSingleShot(True)
        self._check_port_timer.timeout.connect(self._check_port_and_start)
        self._check_port_and_start()

    def _check_port_and_start(self):
        """Одна попытка проверки порта и запуска Ollama."""
        if not self.ollama_manager.is_running():
            # Проверяем бинарник перед запуском (не показываем диалог установки при смене путей)
            bin_path = self.ollama_manager._get_ollama_binary()
            if not bin_path:
                if self.ollama_tab:
                    self.ollama_tab._set_status("⚠ Бинарник Ollama не найден", "orange")
                return
            # Порт свободен — запускаем
            if self.ollama_tab:
                self.ollama_tab._set_status("Перезапуск Ollama...", "#DAA520")
            self.ollama_manager.start()
            return
        self._restart_attempts += 1
        if self._restart_attempts < self._max_restart_attempts:
            # Порт ещё занят — пробуем через 500 мс
            self._check_port_timer.start(500)
        else:
            # Порт не освободился — принудительный перезапуск
            if self.ollama_tab:
                self.ollama_tab._set_status("⚠ Порт занят, принудительный перезапуск...", "orange")
            self.ollama_manager.kill_existing_and_start()

    def _update_status(self):
        validator = PathValidator()
        result = validator.validate_installed(self.config)
        
        if not result["all_valid"]:
            errors = []
            if "venv" in result and not result["venv"]["valid"]:
                errors.append("venv")
            if "models" in result and not result["models"]["valid"]:
                errors.append("модели")
            if "output" in result and not result["output"]["valid"]:
                errors.append("папка сохранения")
            if "ollama" in result and not result["ollama"]["valid"]:
                errors.append("Ollama")
            # Новые пути Ollama (бинарник критичен, модели не критичны)
            if "ollama_binary" in result and not result["ollama_binary"]["valid"]:
                errors.append("бинарник Ollama")
            if "ollama_models" in result and not result["ollama_models"]["valid"]:
                errors.append("модели Ollama")
            self._set_active_tab_status(f"⚠ Настройте пути: {', '.join(errors)}", "orange")
        else:
            self._set_active_tab_status("Готово", "green")
    
    def _on_tab_changed(self, index):
        """Переключение табов"""
        active_tab = self.tabs.currentWidget()
        
        # Переключение табов свободно, блокировка только на кнопке запуска
        prev_tab = self.tabs.widget(self._prev_index)
        if prev_tab and hasattr(prev_tab, '_bar_state'):
            prev_tab._bar_state["prompt"] = self.shared_bar.get_prompt()
        
        tab_name = self._tab_names.get(id(active_tab), "")
        self.resource_manager.on_tab_changed(tab_name)
        
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            state = active_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
        if "elapsed_seconds" in state:
            self.shared_bar.set_timer_display(state["elapsed_seconds"])
            self.shared_bar.set_status(state["status"], state.get("status_color"))
            
        
        self._prev_index = index
        
        # Синхронизируем радиокнопки с активным табом
    
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
        if "elapsed_seconds" in state:
            self.shared_bar.set_timer_display(state["elapsed_seconds"])
        
        if state.get("is_running"):
            self.shared_bar.set_running_state(True)

        else:
            self.shared_bar.set_running_state(False)
    def _set_active_tab_status(self, message: str, color: str = "#DAA520"):
        """Устанавливает статус через активный таб (не напрямую в SharedBottomBar)"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_set_status'):
            active_tab._set_status(message, color)
    
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
        """Останавливает генерацию только из целевой вкладки"""
        if not self.resource_manager.is_resource_busy():
            return
        
        owner = self.resource_manager.get_resource_owner()
        active_tab = self.tabs.currentWidget()
        
        # Динамический поиск индекса вкладки-владельца по имени модуля
        owner_index = -1
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if self._tab_names.get(id(tab)) == owner:
                owner_index = i
                break
        
        if owner_index >= 0 and self.tabs.currentIndex() != owner_index:
            # Переключаем на целевую вкладку
            self.tabs.setCurrentIndex(owner_index)
            self._set_active_tab_status(f"⚠ Перейдите на вкладку {owner} для остановки", "orange")
            return
        
        # Мы на целевой вкладке — останавливаем
        if hasattr(active_tab, 'stop_generation'):
            active_tab.stop_generation()
    
    def _restore_bar_state(self):
        """Восстановление состояния табов из QSettings"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, '_bar_state'):
                tab_name = self._tab_names.get(id(tab), f"tab_{i}")
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
                tab_name = self._tab_names.get(id(tab), f"tab_{i}")
                self.config.set_json(f"bar_state/{tab_name}", tab._bar_state)
    
    # === Ollama Manager handlers ===
    
    def _on_ollama_started(self):
        """Ollama запущен и готов"""
        if self.ollama_manager.is_our_process():
            self.ollama_tab._set_status("✅ Ollama запущен (наш процесс)", "green")
        else:
            self.ollama_tab._set_status("✅ Ollama подключён (внешний)", "green")
        # Обновляем список моделей (сервер готов, API доступен)
        if self.ollama_tab:
            self.ollama_tab.settings_panel.load_models()
    
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
    

    # === Обновления ===

    def _on_update_available(self, current, new):
        """Найдена новая версия — мигаем в статусе и ставим точку в меню"""
        self._update_menu_badge(True)
        self._show_update_notification(
            f"⚠ Доступно обновление {new} (текущая {current})"
        )

    def _update_menu_badge(self, has_update):
        """Добавляет/убирает точку к пункту Настройки"""
        if has_update:
            self.settings_action.setText("Настройки ●")
        else:
            self.settings_action.setText("Настройки")

    def _show_update_notification(self, message):
        """Мигает сообщением об обновлении в статусе активной вкладки"""
        from PyQt6.QtCore import QTimer
        # Останавливаем предыдущий таймер, если есть
        if hasattr(self, '_blink_timer') and self._blink_timer.isActive():
            self._blink_timer.stop()
        # Сохраняем текущий статус активной вкладки
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            self._blink_saved_status = active_tab._bar_state.get("status", "Готово")
            self._blink_saved_color = active_tab._bar_state.get("status_color", "#DAA520")
        else:
            self._blink_saved_status = "Готово"
            self._blink_saved_color = "green"
        self._blink_message = message
        self._blink_count = 0
        self._blink_max = 6  # 3 цикла on/off (~3 секунды при 500 мс)
        self._blink_timer = QTimer()
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._blink_step)
        self._blink_timer.start()
        # Сразу показываем сообщение
        self._set_active_tab_status(self._blink_message, "orange")

    def _blink_step(self):
        """Один шаг мигания"""
        self._blink_count += 1
        if self._blink_count % 2 == 1:
            self._set_active_tab_status(self._blink_saved_status, self._blink_saved_color)
        else:
            self._set_active_tab_status(self._blink_message, "orange")
        if self._blink_count >= self._blink_max:
            self._blink_timer.stop()
            self._set_active_tab_status(self._blink_saved_status, self._blink_saved_color)

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
            self,
            manual_mode=False
        )
        
        # Блокируем закрытие до завершения очистки
        event.ignore()
        
        # После закрытия диалога — выходим
        if cleanup_dialog.exec():
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()
    
    def _on_resource_acquired(self, module_name):
        """Ресурс захвачен модулем"""
        # Получаем имя выбранной модели из активного таба
        model_name = ""
        try:
            if module_name == "ollama" and self.ollama_tab:
                model_name = self.ollama_tab.settings_panel.model_combo.currentText()
            elif module_name == "diffusers" and self.diffusers_tab:
                model_name = self.diffusers_tab.settings_panel.model_combo.currentText()
        except Exception:
            pass
        self.shared_bar.set_mode(module_name, model_name)
        self._set_active_tab_status(f"⚠ {module_name}: генерация...", "orange")
    
    def _on_resource_released(self):
        """Ресурс освобождён"""
        self.shared_bar.set_mode("free")
        self._set_active_tab_status("Готово", "green")
