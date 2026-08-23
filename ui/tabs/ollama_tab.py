from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QInputDialog, QMessageBox
from ui.chat_widget import ChatWidget
from ui.chat_control_panel import ChatControlPanel
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.chat_exporter import ChatExporter
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal, QTimer
import time
import requests
import json
import os


class OllamaTab(QWidget):
    state_changed = pyqtSignal(dict)

    def __init__(self, config, resource_manager):
        super().__init__()
        self.config = config
        self.resource_manager = resource_manager
        self.chat_manager = ChatManager()
        self.client = None
        self._current_response_text = ""
        self.last_stats = None
        self._had_error = False
        self._last_status_update = 0.0
        
        # Состояние таба: свободное или зафиксированное
        self._chat_locked = False
        self._current_mode = "new"
        self._pending_clear_after_save = False  # Флаг для очистки после сохранения
        self._current_chat_base_path = None     # Путь к загруженному файлу (без расширения)
        self._current_chat_title = "Без названия"

        self._progress_timer = QTimer()
        self._progress_timer.setInterval(1000)
        self._progress_timer.timeout.connect(self._update_progress)
        self._generation_start_time = None
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
            "elapsed_seconds": 0,
            "is_running": False
        }

        layout = QHBoxLayout(self)

        left_layout = QVBoxLayout()
        self.chat_widget = ChatWidget()
        self.chat_widget.set_auto_scroll(self.config.get("chat_auto_scroll", True))
        self.chat_control_panel = ChatControlPanel()
        left_layout.addWidget(self.chat_widget, 1)
        left_layout.addWidget(self.chat_control_panel)

        self.settings_panel = SettingsPanel(self.config)

        timeout_sec = self.settings_panel.timeout_spin.value()
        self._bar_state["progress_total"] = timeout_sec

        layout.addLayout(left_layout, 3)
        layout.addWidget(self.settings_panel, 1)

        # Подключения
        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)
        self.settings_panel.mode_changed.connect(self._on_mode_changed)
        self.settings_panel.chat_selected.connect(self._on_chat_selected)
        
        self.chat_control_panel.new_chat_clicked.connect(self._on_new_chat_clicked)
        self.chat_control_panel.undo_last_clicked.connect(self.undo_last_message)
        self.chat_control_panel.attach_file_clicked.connect(self._on_attach_file)
        self.chat_control_panel.export_chat_clicked.connect(self._on_export_chat)

    def _on_timeout_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())

    def get_bar_state(self) -> dict:
        return self._bar_state.copy()

    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())

    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())

    def _set_status(self, message: str, color: str = "#DAA520"):
        self._bar_state["status"] = message
        self._bar_state["status_color"] = color
        self.state_changed.emit(self._bar_state.copy())

    def _update_undo_button_state(self):
        msgs = self.chat_manager.messages
        can_undo = self._bar_state.get("is_running", False) or len(msgs) > 0
        self.chat_control_panel.set_undo_enabled(can_undo)

    def _on_mode_changed(self, mode: str):
        """Обработка смены режима (только в свободном состоянии)"""
        if self._chat_locked:
            return
        
        self._current_mode = mode
        self.settings_panel._update_ui_state(mode, locked=False)
        
        if mode == "new":
            self._set_status("Режим: Новый чат", "green")
        elif mode == "resume":
            self._set_status("Режим: Выберите чат для продолжения", "#DAA520")
        elif mode == "edit":
            self._set_status("Режим: Выберите чат для редактирования", "#DAA520")

    def _on_chat_selected(self, file_path: str):
        """Загрузка чата из JSON"""
        print(f"[DEBUG] _on_chat_selected: загружаем {file_path}, текущий mode='{self._current_mode}'")
        if not os.path.exists(file_path):
            self._set_status("⚠ Файл чата не найден", "red")
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                chat_data = json.load(f)
            
            self.chat_manager.load_messages(chat_data.get("messages", []))
            self.chat_widget.load_chat(chat_data.get("messages", []))
            
            if "settings" in chat_data:
                self.settings_panel.apply_settings_from_chat(chat_data["settings"])
            
            # Сохраняем путь и название для последующего сохранения
            self._current_chat_title = chat_data.get("title", os.path.splitext(os.path.basename(file_path))[0])
            self._current_chat_base_path = os.path.splitext(file_path)[0]
            print(f"[DEBUG] _on_chat_selected: запомнили base_path='{self._current_chat_base_path}', title='{self._current_chat_title}'")
            
            self._chat_locked = True
            self.settings_panel.set_mode(self._current_mode, locked=True)
            
            self._update_undo_button_state()
            self._set_status(f"💾 Чат загружен: {os.path.basename(file_path)}", "green")
            
        except Exception as e:
            self._set_status(f"❌ Ошибка загрузки чата: {e}", "red")

    def _on_new_chat_clicked(self):
        """Кнопка '+ Новый чат' с защитным вопросом"""
        if len(self.chat_manager.messages) > 0:
            reply = QMessageBox.question(
                self,
                "Новый чат",
                "Текущий чат не сохранён. Сохранить перед очисткой?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Устанавливаем флаг очистки после сохранения
                self._pending_clear_after_save = True
                self._on_export_chat()
            elif reply == QMessageBox.StandardButton.No:
                self._clear_chat_internal()
            else:
                return
        else:
            self._clear_chat_internal()

    def _clear_chat_internal(self):
        """Внутренний метод очистки чата"""
        self.chat_manager.clear()
        self.chat_widget.clear_chat()
        self.settings_panel.chat_file_edit.clear()
        self._chat_locked = False
        self._current_mode = "new"
        self._current_chat_base_path = None
        self._current_chat_title = "Без названия"
        self.settings_panel.set_mode("new", locked=False)
        self._update_undo_button_state()
        self.update_bar_state("prompt", "")
        self._set_status("Чат очищен", "green")

    def handle_prompt(self, text):
        if not text:
            return

        if self._current_mode in ["resume", "edit"] and not self._chat_locked:
            self._set_status("⚠ Загрузите чат через 📂", "orange")
            return

        self.update_bar_state("prompt", text)
        if not self.resource_manager.acquire_resource("ollama"):
            self._set_status("⚠ Ресурс занят другой моделью", "orange")
            self.update_bar_state("is_running", False)
            return
        self.update_bar_state("is_running", True)

        if not self._chat_locked:
            self._chat_locked = True
            self.settings_panel.set_mode(self._current_mode, locked=True)

        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)
        self.update_bar_state("progress_current", 0)
        self._generation_start_time = time.time()
        self._progress_timer.start()
        self._set_status("Обработка промпта...", "#DAA520")

        self.chat_manager.add_user_message(text)
        self.chat_widget.append_user_message(text)

        self._current_response_text = ""
        self.last_stats = None
        self._had_error = False
        self._last_status_update = 0.0
        self._update_undo_button_state()

        sys_prompt = self.settings_panel.sys_prompt.toPlainText()
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.extend(self.chat_manager.get_messages())

        options = {
            "temperature": self.settings_panel.temp_spin.value(),
            "top_p": self.settings_panel.top_p_spin.value(),
            "num_predict": self.settings_panel.max_tokens_spin.value()
        }

        self.client = OllamaClient(
            url=self.config.get("url", "http://localhost:11434"),
            model=self.settings_panel.model_combo.currentText(),
            messages=messages,
            options=options,
            timeout=self.settings_panel.timeout_spin.value(),
            stream=self.settings_panel.stream_check.isChecked()
        )

        self.client.token_received.connect(self.on_token)
        self.client.generation_finished.connect(self.on_finished)
        self.client.error_occurred.connect(self.on_error)
        self.client.stats_received.connect(self.on_stats)

        self.client.start()
        self.update_bar_state("prompt", "")

    def on_token(self, token):
        self._current_response_text += token
        now = time.time()
        if now - self._last_status_update >= 0.1:
            self._last_status_update = now
            last_line = self._current_response_text.split('\n')[-1]
            display = last_line if len(last_line) <= 100 else last_line[:97] + "..."
            self._set_status(display, "gray")

    def _update_progress(self):
        if self._generation_start_time:
            elapsed = int(time.time() - self._generation_start_time)
            self.update_bar_state("progress_current", elapsed)
            self.update_bar_state("elapsed_seconds", elapsed)

    def on_finished(self):
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self.chat_manager.add_assistant_message(self._current_response_text, self.last_stats)
        self.settings_panel.save_settings()

        self.chat_widget.append_assistant_message(self._current_response_text, self.last_stats)
        self._update_undo_button_state()

        self.resource_manager.release_resource()
        self.update_bar_state("is_running", False)
        if not self._had_error:
            self._set_status("Готово", "green")

        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def on_stats(self, stats_dict):
        self.last_stats = stats_dict

    def on_error(self, error_msg):
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self._had_error = True
        self._current_response_text += f"\n\n⚠ Ошибка: {error_msg}"

        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")

        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def stop_generation(self):
        self._progress_timer.stop()
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.set_stopping_state()
        if self.client and self.client.isRunning():
            self.client.stop()

    def clear_chat(self):
        """Публичный метод очистки (используется извне)"""
        self._clear_chat_internal()

    def undo_last_message(self):
        if self._bar_state.get("is_running", False):
            self.stop_generation()
            self._current_response_text = ""
            self._had_error = False
        
        last_user_text = self.chat_manager.remove_last_message()
        if last_user_text:
            self.chat_widget.remove_last_message()
            self.update_bar_state("prompt", last_user_text)
            self._update_undo_button_state()
            self._set_status("Действие отменено, текст возвращён в промпт", "#DAA520")

    def _on_attach_file(self):
        self._set_status("📎 Загрузка файлов пока в разработке", "#DAA520")

    def _on_export_chat(self):
        print(f"[DEBUG] _on_export_chat: mode='{self._current_mode}', base_path='{self._current_chat_base_path}', title='{self._current_chat_title}'")
        if not self.chat_manager.messages:
            self._set_status("⚠ Нечего сохранять — чат пуст", "orange")
            return
        
        # Логика сохранения в зависимости от режима и наличия исходного файла
        if self._current_mode == "resume" and self._current_chat_base_path:
            # Режим "Продолжить": сохраняем поверх оригинала без диалога
            self._save_chat(self._current_chat_title, self._current_chat_base_path)
            return
        
        if self._current_mode == "edit" and self._current_chat_base_path:
            # Режим "Изменить": предлагаем выбор
            from PyQt6.QtWidgets import QMessageBox
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Сохранение изменённого чата")
            msg_box.setText("Чат был загружен и изменён. Выберите действие:")
            btn_overwrite = msg_box.addButton("Перезаписать оригинал", QMessageBox.ButtonRole.AcceptRole)
            btn_new = msg_box.addButton("Сохранить как новый", QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()
            
            if msg_box.clickedButton() == btn_overwrite:
                self._save_chat(self._current_chat_title, self._current_chat_base_path)
            elif msg_box.clickedButton() == btn_new:
                self._show_save_dialog(self._current_chat_title)
            return
        
        # Стандартное поведение для нового чата или если путь неизвестен
        if self.config.get("chat_auto_title", True):
            self._set_status("🤖 Генерация названия...", "#DAA520")
            self._generate_title_async()
        else:
            self._show_save_dialog("")

    def _generate_title_async(self):
        context_messages = []
        for msg in self.chat_manager.messages[:6]:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            content = msg["content"][:200]
            context_messages.append(f"{role}: {content}")
        
        prompt = (
            "Придумай короткий заголовок (максимум 3 слова) для этого диалога. "
            "Заголовок должен отражать основную тему. "
            "Отвечай ТОЛЬКО самим заголовком, без кавычек и пояснений.\n\n"
            + "\n".join(context_messages)
        )

        self._title_buffer = ""
        self._title_client = OllamaClient(
            url=self.config.get("url", "http://localhost:11434"),
            model=self.settings_panel.model_combo.currentText(),
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 30},
            timeout=30,
            stream=False
        )
        self._title_client.token_received.connect(self._on_title_token)
        self._title_client.generation_finished.connect(self._on_title_finished)
        self._title_client.error_occurred.connect(self._on_title_error)
        self._title_client.start()

    def _on_title_token(self, token):
        self._title_buffer += token

    def _on_title_finished(self):
        title = self._title_buffer.strip().replace('\n', ' ')[:50]
        title = title.strip('"\'')
        self._show_save_dialog(title)

    def _on_title_error(self, error_msg):
        self._set_status(f"⚠ Не удалось сгенерировать название: {error_msg}", "orange")
        self._show_save_dialog("")

    def _show_save_dialog(self, default_title: str):
        title, ok = QInputDialog.getText(
            self, "Сохранить чат", "Название чата:", text=default_title
        )
        if ok and title.strip():
            self._save_chat(title.strip())
        elif ok:
            self._set_status("⚠ Сохранение отменено: название не указано", "orange")
            # Сбрасываем флаг, если пользователь отменил ввод названия
            self._pending_clear_after_save = False

    def _save_chat(self, title: str, target_base_path: str = None):
        try:
            settings = {
                "model": self.settings_panel.model_combo.currentText(),
                "temperature": self.settings_panel.temp_spin.value(),
                "top_p": self.settings_panel.top_p_spin.value(),
                "max_tokens": self.settings_panel.max_tokens_spin.value(),
                "system_prompt": self.settings_panel.sys_prompt.toPlainText(),
                "timeout": self.settings_panel.timeout_spin.value(),
                "stream": self.settings_panel.stream_check.isChecked()
            }
            
            chats_dir = self.config.get_chats_dir()
            exporter = ChatExporter(chats_dir)
            
            result = exporter.export_chat(
                title=title,
                messages=self.chat_manager.messages,
                settings=settings,
                save_json=self.config.get("chat_save_json", True),
                save_txt=self.config.get("chat_save_txt", True),
                target_base_path=target_base_path
            )
            
            saved_files = []
            if "json" in result: saved_files.append("JSON")
            if "txt" in result: saved_files.append("TXT")
            
            # НЕ размораживаем UI после сохранения — пользователь может продолжить писать
            # self._chat_locked = False
            # self.settings_panel.set_mode(self._current_mode, locked=False)
            
            display_name = os.path.basename(target_base_path) if target_base_path else title
            self._set_status(f"💾 Чат '{display_name}' сохранён ({', '.join(saved_files)})", "green")
            
            # Проверяем флаг и очищаем чат, если нужно
            if self._pending_clear_after_save:
                self._pending_clear_after_save = False
                self._clear_chat_internal()
            
        except Exception as e:
            self._set_status(f"❌ Ошибка сохранения: {e}", "red")
            # Сбрасываем флаг при ошибке
            self._pending_clear_after_save = False

    def unload(self):
        try:
            requests.post(f"{self.config.get_ollama_url()}/api/generate",
                         json={"model": self.settings_panel.model_combo.currentText(),
                               "keep_alive": 0},
                         timeout=5)
        except Exception:
            pass
