from PyQt6.QtWidgets import QWidget, QHBoxLayout
from ui.chat_widget import ChatWidget
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal
import requests


class OllamaTab(QWidget):
    """Вкладка Ollama с состоянием для SharedBottomBar"""

    # Универсальный сигнал для MainWindow
    state_changed = pyqtSignal(dict)

    def __init__(self, config, resource_manager):
        super().__init__()
        self.config = config
        self.resource_manager = resource_manager
        self.chat_manager = ChatManager()
        self.client = None
        self._current_response_text = ""
        self.last_stats = None

        # Состояние для SharedBottomBar
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
            "is_running": False
        }

        layout = QHBoxLayout(self)

        self.chat_widget = ChatWidget()
        self.settings_panel = SettingsPanel(self.config)

        layout.addWidget(self.chat_widget, 3)
        layout.addWidget(self.settings_panel, 1)

        self.settings_panel.clear_btn.clicked.connect(self.clear_chat)

        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)


    def _on_timeout_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())

        timeout_minutes = self.settings_panel.timeout_spin.value() // 60
        return f"{timeout_minutes} мин"

    def get_bar_state(self) -> dict:
        """Возвращает копию состояния"""
        return self._bar_state.copy()

    def set_bar_state(self, state: dict):
        """Устанавливает состояние"""
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())

    def update_bar_state(self, key: str, value):
        """Обновляет одно поле и эмитит сигнал"""
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())

    def _set_status(self, message: str, color: str = "#DAA520"):
        """Устанавливает статус с цветом"""
        self._bar_state["status"] = message
        self._bar_state["status_color"] = color
        self.state_changed.emit(self._bar_state.copy())

    def handle_prompt(self, text):
        """Обработка промпта из общей панели"""
        if not text:
            return

        # Обновляем состояние
        self.update_bar_state("prompt", text)
        if not self.resource_manager.acquire_resource("ollama"):
            self._set_status("⚠ Ресурс занят другой моделью", "orange")
            self.update_bar_state("is_running", False)
            return
        self.update_bar_state("is_running", True)
        self._set_status("Генерация...", "#DAA520")

        self.chat_manager.add_user_message(text)
        self.chat_widget.append_user_message(text)
        self.chat_widget.start_assistant_message()

        self._current_response_text = ""
        self.last_stats = None

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

    def on_token(self, token):
        """Получен токен"""
        self._current_response_text += token
        self.chat_widget.append_token(token)

        # Обновляем статус
        self._set_status(f"Генерация... ({len(self._current_response_text)} символов)", "#DAA520")

    def on_finished(self):
        """Генерация завершена"""
        self.chat_manager.add_assistant_message(self._current_response_text)
        self.settings_panel.save_settings()

        if self.last_stats:
            self.chat_widget.finalize_response(self.last_stats)
        else:
            self.chat_widget.finalize_response({})

        # Обновляем состояние
        self.resource_manager.release_resource()
        self.update_bar_state("is_running", False)
        self._set_status("Готово", "green")

    def on_stats(self, stats_dict):
        """Получена статистика"""
        self.last_stats = stats_dict

    def on_error(self, error_msg):
        """Ошибка генерации"""
        self.chat_widget.append_token(f"\nОшибка: {error_msg}")

        # Обновляем состояние
        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")

    def stop_generation(self):
        """Остановка генерации"""
        if self.client and self.client.isRunning():
            self.client.stop()

    def clear_chat(self):
        """Очистка чата"""
        self.chat_manager.clear()
        self.chat_widget.clear_chat()

    def unload(self):
        """Выгружает модель из памяти Ollama"""
        try:
            requests.post(f"{self.config.get_ollama_url()}/api/generate",
                         json={"model": self.settings_panel.model_combo.currentText(),
                               "keep_alive": 0},
                         timeout=5)
        except Exception:
            pass
