from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QDoubleSpinBox, QSpinBox, QTextEdit,
                             QPushButton, QCheckBox, QRadioButton, QLineEdit)
from PyQt6.QtCore import pyqtSignal
from utils.config import Config
import requests


class SettingsPanel(QWidget):
    # Сигналы для OllamaTab
    chat_selected = pyqtSignal(str)  # Путь к JSON файлу
    mode_changed = pyqtSignal(str)   # "new" | "resume" | "edit"

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        
        layout = QVBoxLayout(self)
        
        # === Модель ===
        layout.addWidget(QLabel("Модель:"))
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        model_row.addWidget(self.model_combo, 1)
        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedWidth(40)
        self.refresh_models_btn.setToolTip("Обновить список моделей из Ollama")
        self.refresh_models_btn.clicked.connect(self.load_models)
        model_row.addWidget(self.refresh_models_btn)
        layout.addLayout(model_row)
        
        # === Параметры генерации ===
        layout.addWidget(QLabel("Temperature:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        layout.addWidget(self.temp_spin)
        
        layout.addWidget(QLabel("Top P:"))
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        layout.addWidget(self.top_p_spin)
        
        layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setSingleStep(64)
        layout.addWidget(self.max_tokens_spin)
        
        layout.addWidget(QLabel("Timeout (сек):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 3600)
        self.timeout_spin.setSingleStep(60)
        layout.addWidget(self.timeout_spin)
        
        self.stream_check = QCheckBox("Stream (потоковый вывод)")
        layout.addWidget(self.stream_check)
        
        layout.addWidget(QLabel("System Prompt:"))
        self.sys_prompt = QTextEdit()
        self.sys_prompt.setMaximumHeight(100)
        layout.addWidget(self.sys_prompt)
        
        layout.addSpacing(10)
        
        # === Выбор сохранённого чата ===
        layout.addWidget(QLabel("Сохранённый чат:"))
        chat_row = QHBoxLayout()
        self.chat_file_edit = QLineEdit()
        self.chat_file_edit.setReadOnly(True)
        self.chat_file_edit.setPlaceholderText("не выбран")
        chat_row.addWidget(self.chat_file_edit)
        self.chat_browse_btn = QPushButton("📂")
        self.chat_browse_btn.setFixedWidth(40)
        self.chat_browse_btn.clicked.connect(self._browse_chat)
        chat_row.addWidget(self.chat_browse_btn)
        layout.addLayout(chat_row)
        
        # === Кнопка сброса настроек ===
        self.reset_settings_btn = QPushButton("Сбросить настройки")
        self.reset_settings_btn.clicked.connect(self._reset_settings)
        layout.addWidget(self.reset_settings_btn)
        
        layout.addStretch()
        
        # === Радиокнопки режимов ===
        layout.addSpacing(10)
        mode_row = QHBoxLayout()
        
        self.mode_new_radio = QRadioButton("Новый")
        self.mode_new_radio.setChecked(True)
        self.mode_new_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_new_radio)
        
        self.mode_resume_radio = QRadioButton("Продолжить")
        self.mode_resume_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_resume_radio)
        
        self.mode_edit_radio = QRadioButton("Изменить")
        self.mode_edit_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_edit_radio)
        
        layout.addLayout(mode_row)
        
        self.load_settings()
        self.load_models()
        
        # Начальное состояние: свободное, режим "Новый"
        self._update_ui_state("new", locked=False)

    def _on_mode_changed(self):
        if self.mode_new_radio.isChecked():
            self.mode_changed.emit("new")
        elif self.mode_resume_radio.isChecked():
            self.mode_changed.emit("resume")
        elif self.mode_edit_radio.isChecked():
            self.mode_changed.emit("edit")

    def _browse_chat(self):
        from PyQt6.QtWidgets import QFileDialog
        chats_dir = self.config.get("chats_dir", "data/ollama/chats")
        folder_path = QFileDialog.getExistingDirectory(
            self, "Выберите папку чата", chats_dir
        )
        if folder_path:
            self.chat_file_edit.setText(folder_path)
            self.chat_selected.emit(folder_path)

    def _reset_settings(self):
        """Сбрасывает только настройки генерации к дефолтным значениям"""
        self.temp_spin.setValue(0.7)
        self.top_p_spin.setValue(0.9)
        self.max_tokens_spin.setValue(1024)
        self.timeout_spin.setValue(600)
        self.stream_check.setChecked(True)
        self.sys_prompt.clear()
        self.config.set("temperature", 0.7)
        self.config.set("top_p", 0.9)
        self.config.set("max_tokens", 1024)
        self.config.set("timeout", 600)
        self.config.set("stream", "true")
        self.config.set("system_prompt", "")

    def _update_ui_state(self, mode: str, locked: bool):
        """
        Обновляет состояние UI в зависимости от режима и блокировки.
        
        mode: "new" | "resume" | "edit"
        locked: True если режим зафиксирован (чат начат или загружен)
        """
        # Радиокнопки: активны только в свободном состоянии
        self.mode_new_radio.setEnabled(not locked)
        self.mode_resume_radio.setEnabled(not locked)
        self.mode_edit_radio.setEnabled(not locked)
        
        # Поле выбора чата: активно только в режимах "Продолжить"/"Изменить"
        chat_browse_enabled = (mode in ["resume", "edit"])
        self.chat_file_edit.setEnabled(chat_browse_enabled)
        self.chat_browse_btn.setEnabled(chat_browse_enabled)
        
        # Настройки: заблокированы только в режиме "Продолжить"
        settings_enabled = (mode != "resume")
        self.model_combo.setEnabled(settings_enabled)
        self.refresh_models_btn.setEnabled(settings_enabled)
        self.temp_spin.setEnabled(settings_enabled)
        self.top_p_spin.setEnabled(settings_enabled)
        self.max_tokens_spin.setEnabled(settings_enabled)
        self.timeout_spin.setEnabled(settings_enabled)
        self.stream_check.setEnabled(settings_enabled)
        self.sys_prompt.setEnabled(settings_enabled)
        
        # Кнопка сброса настроек: активна в "Новый" и "Изменить"
        self.reset_settings_btn.setEnabled(settings_enabled)

    def set_mode(self, mode: str, locked: bool):
        """Публичный метод для установки режима и блокировки из OllamaTab"""
        # Устанавливаем радиокнопку
        if mode == "new":
            self.mode_new_radio.setChecked(True)
        elif mode == "resume":
            self.mode_resume_radio.setChecked(True)
        elif mode == "edit":
            self.mode_edit_radio.setChecked(True)
        
        # Обновляем UI
        self._update_ui_state(mode, locked)

    def load_settings(self):
        self.temp_spin.setValue(float(self.config.get("temperature", 0.7)))
        self.top_p_spin.setValue(float(self.config.get("top_p", 0.9)))
        self.max_tokens_spin.setValue(int(self.config.get("max_tokens", 1024)))
        self.timeout_spin.setValue(int(self.config.get("timeout", 600)))
        self.stream_check.setChecked(self.config.get("stream", "true") == "true")
        self.sys_prompt.setPlainText(self.config.get("system_prompt", ""))
        self.model_combo.setCurrentText(self.config.get("model", "qwen2.5-coder:3b"))

    def save_settings(self):
        self.config.set("temperature", self.temp_spin.value())
        self.config.set("top_p", self.top_p_spin.value())
        self.config.set("max_tokens", self.max_tokens_spin.value())
        self.config.set("timeout", self.timeout_spin.value())
        self.config.set("stream", str(self.stream_check.isChecked()).lower())
        self.config.set("system_prompt", self.sys_prompt.toPlainText())
        self.config.set("model", self.model_combo.currentText())

    def load_models(self):
        current_model = self.model_combo.currentText()
        try:
            url = self.config.get("url", "http://localhost:11434")
            res = requests.get(f"{url}/api/tags", timeout=5)
            models = [m['name'] for m in res.json().get('models', [])]
            self.model_combo.clear()
            self.model_combo.addItems(models)
            if current_model and current_model in models:
                self.model_combo.setCurrentText(current_model)
        except Exception:
            pass

    def apply_settings_from_chat(self, settings: dict):
        """Применяет настройки из загруженного чата"""
        if "model" in settings and settings["model"] in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
            self.model_combo.setCurrentText(settings["model"])
        if "temperature" in settings:
            self.temp_spin.setValue(float(settings["temperature"]))
        if "top_p" in settings:
            self.top_p_spin.setValue(float(settings["top_p"]))
        if "max_tokens" in settings:
            self.max_tokens_spin.setValue(int(settings["max_tokens"]))
        if "system_prompt" in settings:
            self.sys_prompt.setPlainText(str(settings["system_prompt"]))
        self.save_settings()
