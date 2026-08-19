from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from ui.chat_widget import ChatWidget
from ui.chat_control_panel import ChatControlPanel
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal, QTimer
import time
import requests


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

        self.settings_panel.clear_btn.clicked.connect(self.clear_chat)
        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)
        
        self.chat_control_panel.new_chat_clicked.connect(self.clear_chat)
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
        # Активна, если идет генерация ИЛИ если есть хотя бы одно сообщение в истории
        can_undo = self._bar_state.get("is_running", False) or len(msgs) > 0
        self.chat_control_panel.set_undo_enabled(can_undo)

    def handle_prompt(self, text):
        if not text:
            return

        self.update_bar_state("prompt", text)
        if not self.resource_manager.acquire_resource("ollama"):
            self._set_status("⚠ Ресурс занят другой моделью", "orange")
            self.update_bar_state("is_running", False)
            return
        self.update_bar_state("is_running", True)

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

        self.chat_manager.add_assistant_message(self._current_response_text)
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
        self.chat_manager.clear()
        self.chat_widget.clear_chat()
        self._update_undo_button_state()
        self.update_bar_state("prompt", "")
        self._set_status("Чат очищен", "green")

    def undo_last_message(self):
        # Если идет генерация, останавливаем её
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
        self._set_status("💾 Сохранение чата пока в разработке", "#DAA520")

    def unload(self):
        try:
            requests.post(f"{self.config.get_ollama_url()}/api/generate",
                         json={"model": self.settings_panel.model_combo.currentText(),
                               "keep_alive": 0},
                         timeout=5)
        except Exception:
            pass
