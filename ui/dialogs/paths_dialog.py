from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QLineEdit, QPushButton, QDialogButtonBox,
                              QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
from core.path_validator import PathValidator

class PathsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.validator = PathValidator()
        
        self.setWindowTitle("Настройка путей к компонентам")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout(self)
        
        # Diffusers
        diffusers_group = QGroupBox("Diffusers")
        diffusers_layout = QVBoxLayout()
        
        # venv
        venv_layout = QHBoxLayout()
        venv_layout.addWidget(QLabel("venv:"))
        self.venv_edit = QLineEdit()
        self.venv_edit.setText(config.get_sdxl_venv_path())
        self.venv_edit.textChanged.connect(lambda: self._on_path_changed("venv"))
        venv_layout.addWidget(self.venv_edit, 1)
        
        venv_browse = QPushButton("📁")
        venv_browse.setFixedWidth(40)
        venv_browse.clicked.connect(lambda: self._browse_folder(self.venv_edit))
        venv_layout.addWidget(venv_browse)
        
        self.venv_status = QLabel("")
        venv_layout.addWidget(self.venv_status)
        
        diffusers_layout.addLayout(venv_layout)
        self.venv_error = QLabel("")
        self.venv_error.setStyleSheet("color: red; font-size: 11px;")
        self.venv_error.hide()
        diffusers_layout.addWidget(self.venv_error)
        
        # Models
        models_layout = QHBoxLayout()
        models_layout.addWidget(QLabel("Модели:"))
        self.models_edit = QLineEdit()
        self.models_edit.setText(config.get_sdxl_models_path())
        self.models_edit.textChanged.connect(lambda: self._on_path_changed("models"))
        models_layout.addWidget(self.models_edit, 1)
        
        models_browse = QPushButton("📁")
        models_browse.setFixedWidth(40)
        models_browse.clicked.connect(lambda: self._browse_folder(self.models_edit))
        models_layout.addWidget(models_browse)
        
        self.models_status = QLabel("")
        models_layout.addWidget(self.models_status)
        
        diffusers_layout.addLayout(models_layout)
        self.models_error = QLabel("")
        self.models_error.setStyleSheet("color: red; font-size: 11px;")
        self.models_error.hide()
        diffusers_layout.addWidget(self.models_error)
        
        diffusers_group.setLayout(diffusers_layout)
        layout.addWidget(diffusers_group)
        
        # Сохранение
        output_group = QGroupBox("Сохранение")
        output_layout = QVBoxLayout()
        
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("Папка для изображений:"))
        self.output_edit = QLineEdit()
        self.output_edit.setText(config.get_sdxl_output_dir())
        self.output_edit.textChanged.connect(lambda: self._on_path_changed("output"))
        output_path_layout.addWidget(self.output_edit, 1)
        
        output_browse = QPushButton("📁")
        output_browse.setFixedWidth(40)
        output_browse.clicked.connect(lambda: self._browse_folder(self.output_edit))
        output_path_layout.addWidget(output_browse)
        
        self.output_status = QLabel("")
        output_path_layout.addWidget(self.output_status)
        
        output_layout.addLayout(output_path_layout)
        self.output_error = QLabel("")
        self.output_error.setStyleSheet("color: red; font-size: 11px;")
        self.output_error.hide()
        output_layout.addWidget(self.output_error)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # Ollama
        ollama_group = QGroupBox("Ollama")
        ollama_layout = QVBoxLayout()
        
        ollama_url_layout = QHBoxLayout()
        ollama_url_layout.addWidget(QLabel("URL:"))
        self.ollama_edit = QLineEdit()
        self.ollama_edit.setText(config.get_ollama_url())
        self.ollama_edit.textChanged.connect(lambda: self._on_path_changed("ollama"))
        ollama_url_layout.addWidget(self.ollama_edit, 1)
        
        self.ollama_status = QLabel("")
        ollama_url_layout.addWidget(self.ollama_status)
        
        ollama_layout.addLayout(ollama_url_layout)
        self.ollama_error = QLabel("")
        self.ollama_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_error.hide()
        ollama_layout.addWidget(self.ollama_error)
        
        ollama_group.setLayout(ollama_layout)
        layout.addWidget(ollama_group)
        
        # Кнопки
        validate_btn = QPushButton("Проверить всё")
        validate_btn.clicked.connect(self._on_validate_all)
        layout.addWidget(validate_btn)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        
        # Первоначальная валидация
        self._on_validate_all()
    
    def _on_path_changed(self, field_name):
        """Валидация одного поля"""
        if field_name == "venv":
            result = self.validator.validate_venv(self.venv_edit.text())
            self._update_status(self.venv_status, self.venv_error, result)
        elif field_name == "models":
            result = self.validator.validate_models_path(self.models_edit.text())
            self._update_status(self.models_status, self.models_error, result)
        elif field_name == "output":
            result = self.validator.validate_output_dir(self.output_edit.text())
            self._update_status(self.output_status, self.output_error, result)
        elif field_name == "ollama":
            result = self.validator.validate_ollama_url(self.ollama_edit.text())
            self._update_status(self.ollama_status, self.ollama_error, result)
        
        self._update_ok_button()
    
    def _update_status(self, status_label, error_label, result):
        """Обновляет индикатор статуса"""
        if result["valid"]:
            status_label.setText("✅")
            error_label.hide()
        else:
            status_label.setText("❌")
            error_label.setText(result.get("error", ""))
            error_label.show()
    
    def _update_ok_button(self):
        """Обновляет доступность кнопки OK"""
        venv_valid = self.validator.validate_venv(self.venv_edit.text())["valid"]
        models_valid = self.validator.validate_models_path(self.models_edit.text())["valid"]
        output_valid = self.validator.validate_output_dir(self.output_edit.text())["valid"]
        
        self.ok_button.setEnabled(venv_valid and models_valid and output_valid)
    
    def _on_validate_all(self):
        """Проверка всех путей"""
        self._on_path_changed("venv")
        self._on_path_changed("models")
        self._on_path_changed("output")
        self._on_path_changed("ollama")
    
    def _on_accept(self):
        """Сохранение и закрытие"""
        self.config.set_sdxl_venv_path(self.venv_edit.text())
        self.config.set_sdxl_models_path(self.models_edit.text())
        self.config.set_sdxl_output_dir(self.output_edit.text())
        self.config.set("url", self.ollama_edit.text())
        self.accept()
    
    def _browse_folder(self, line_edit):
        """Открытие диалога выбора папки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку",
            line_edit.text()
        )
        if folder:
            line_edit.setText(folder)
