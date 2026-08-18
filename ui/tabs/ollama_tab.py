from PyQt6.QtWidgets import QWidget, QHBoxLayout
from ui.chat_widget import ChatWidget
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QTimer
import time
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
        self._had_error = False          # была ли ошибка в текущей генерации
        self._last_status_update = 0.0   # для троттлинга live-строки

        # Таймер для прогресс-бара (привязан к таймауту)
        self._progress_timer = QTimer()
        self._progress_timer.setInterval(1000)
        self._progress_timer.timeout.connect(self._update_progress)
        self._generation_start_time = None
        # Состояние для SharedBottomBar
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

        self.chat_widget = ChatWidget()
        self.settings_panel = SettingsPanel(self.config)

        # Инициализируем прогресс-бар под таймаут
        timeout_sec = self.settings_panel.timeout_spin.value()
        self._bar_state["progress_total"] = timeout_sec

        layout.addWidget(self.chat_widget, 3)
        layout.addWidget(self.settings_panel, 1)

        self.settings_panel.clear_btn.clicked.connect(self.clear_chat)
        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)

    def _on_timeout_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())

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

        # Настраиваем прогресс-бар под таймаут
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

        # Чат-поведение: очищаем поле промпта после отправки
        self.update_bar_state("prompt", "")

    def on_token(self, token):
        """Получен токен — накопление буфера + live-строка в статусбар."""
        self._current_response_text += token

        # Троттлинг: обновляем статус не чаще чем раз в 100 мс
        now = time.time()
        if now - self._last_status_update >= 0.1:
            self._last_status_update = now
            last_line = self._current_response_text.split('\n')[-1]
            display = last_line if len(last_line) <= 80 else last_line[:77] + "..."
            self._set_status(display, "gray")

    def _update_progress(self):
        """Обновляет прогресс-бар и таймер каждую секунду"""
        if self._generation_start_time:
            elapsed = int(time.time() - self._generation_start_time)
            self.update_bar_state("progress_current", elapsed)
            self.update_bar_state("elapsed_seconds", elapsed)

    def on_finished(self):
        """Генерация завершена — кладём готовый ответ в чат (append-only)."""
        # Останавливаем таймер и сбрасываем прогресс
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self.chat_manager.add_assistant_message(self._current_response_text)
        self.settings_panel.save_settings()

        # Готовый ответ — один раз в чат
        self.chat_widget.append_assistant_message(self._current_response_text, self.last_stats)

        # Обновляем состояние
        self.resource_manager.release_resource()
        self.update_bar_state("is_running", False)
        if not self._had_error:
            self._set_status("Готово", "green")

        # Сбрасываем кнопку в ready
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def on_stats(self, stats_dict):
        """Получена статистика"""
        self.last_stats = stats_dict

    def on_error(self, error_msg):
        """Ошибка генерации — пометка попадёт в финальное сообщение."""
        # Останавливаем таймер и сбрасываем прогресс
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self._had_error = True
        # Пометка об ошибке добавится к буферу и попадёт в чат через on_finished
        self._current_response_text += f"\n\n⚠ Ошибка: {error_msg}"

        # Обновляем состояние (ресурс освободится в on_finished)
        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")

        # Сбрасываем кнопку в ready
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def stop_generation(self):
        """Остановка генерации"""
        # Останавливаем таймер прогресса
        self._progress_timer.stop()

        # Переключаем кнопку в состояние "Завершение..."
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.set_stopping_state()

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
