from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QDoubleSpinBox, QSpinBox, QTextEdit,
                             QPushButton, QCheckBox)
from utils.config import Config
import requests


class SettingsPanel(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        
        layout = QVBoxLayout(self)
        
        # Модель (надпись сверху)
        layout.addWidget(QLabel("Модель:"))
        
        # ComboBox + кнопка обновления (в одной строке)
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
        
        # Temperature
        layout.addWidget(QLabel("Temperature:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        layout.addWidget(self.temp_spin)
        
        # Top P
        layout.addWidget(QLabel("Top P:"))
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        layout.addWidget(self.top_p_spin)
        
        # Max Tokens
        layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setSingleStep(64)
        layout.addWidget(self.max_tokens_spin)
        
        # Timeout
        layout.addWidget(QLabel("Timeout (сек):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 3600)
        self.timeout_spin.setSingleStep(60)
        layout.addWidget(self.timeout_spin)
        
        # Stream
        self.stream_check = QCheckBox("Stream (потоковый вывод)")
        layout.addWidget(self.stream_check)
        
        # System Prompt
        layout.addWidget(QLabel("System Prompt:"))
        self.sys_prompt = QTextEdit()
        self.sys_prompt.setMaximumHeight(100)
        layout.addWidget(self.sys_prompt)
        
        # Очистить чат
        self.clear_btn = QPushButton("Очистить чат")
        layout.addWidget(self.clear_btn)
        
        layout.addStretch()
        
        # Кнопка Отправить внизу
        self.send_btn = QPushButton("Отправить")
        layout.addWidget(self.send_btn)
        
        self.load_settings()
        self.load_models()
    
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
        """Загружает список моделей из Ollama API. Сохраняет текущий выбор."""
        current_model = self.model_combo.currentText()
        try:
            url = self.config.get("url", "http://localhost:11434")
            res = requests.get(f"{url}/api/tags", timeout=5)
            models = [m['name'] for m in res.json().get('models', [])]
            self.model_combo.clear()
            self.model_combo.addItems(models)
            # Восстанавливаем выбранную модель
            if current_model and current_model in models:
                self.model_combo.setCurrentText(current_model)
        except Exception:
            pass
