from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QLineEdit, QPushButton, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from core.path_validator import PathValidator

class PathsSettingsWidget(QWidget):
    """Виджет общих настроек путей"""
    
    # Сигнал о готовности (все поля зелёные)
    all_valid = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.validator = PathValidator()
        self._ollama_retry_count = 0
        self._ollama_max_retries = 5
        self._ollama_retry_timer = QTimer()
        self._ollama_retry_timer.timeout.connect(self._on_ollama_retry)
        # Загружаем пути через PathsManager (единая точка доступа)
        from core.paths_manager import PathsManager
        pm = PathsManager()
        paths = pm.get_effective_paths(self.config)

        layout = QVBoxLayout(self)

        # Diffusers
        diffusers_group = QGroupBox("Diffusers")
        diffusers_layout = QVBoxLayout()

        # venv
        venv_layout = QHBoxLayout()
        venv_layout.addWidget(QLabel("venv:"))
        self.venv_edit = QLineEdit()
        self.venv_edit.setText(paths["sdxl_venv"])
        self.venv_edit.editingFinished.connect(lambda: self._on_path_changed("venv"))
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
        self.models_edit.setText(paths["sdxl_models"])
        self.models_edit.editingFinished.connect(lambda: self._on_path_changed("models"))
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
        self.output_edit.setText(paths["sdxl_output"])
        self.output_edit.editingFinished.connect(lambda: self._on_path_changed("output"))
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

        # Ollama бинарник
        ollama_bin_layout = QHBoxLayout()
        ollama_bin_layout.addWidget(QLabel("Бинарник:"))
        self.ollama_bin_edit = QLineEdit()
        self.ollama_bin_edit.setText(paths["ollama_binary"])
        self.ollama_bin_edit.editingFinished.connect(lambda: self._on_path_changed("ollama_bin"))
        ollama_bin_layout.addWidget(self.ollama_bin_edit, 1)
        ollama_bin_browse = QPushButton("📁")
        ollama_bin_browse.setFixedWidth(40)
        ollama_bin_browse.clicked.connect(lambda: self._browse_file(self.ollama_bin_edit))
        ollama_bin_layout.addWidget(ollama_bin_browse)
        self.ollama_bin_status = QLabel("")
        ollama_bin_layout.addWidget(self.ollama_bin_status)
        ollama_layout.addLayout(ollama_bin_layout)

        self.ollama_bin_error = QLabel("")
        self.ollama_bin_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_bin_error.hide()
        ollama_layout.addWidget(self.ollama_bin_error)

        # Ollama модели
        ollama_models_layout = QHBoxLayout()
        ollama_models_layout.addWidget(QLabel("Модели:"))
        self.ollama_models_edit = QLineEdit()
        from core.paths_manager import PathsManager
        pm = PathsManager()
        ollama_models_path = pm.get_path(config, "ollama_models")
        self.ollama_models_edit.setText(ollama_models_path)
        self.ollama_models_edit.editingFinished.connect(lambda: self._on_path_changed("ollama_models"))
        ollama_models_layout.addWidget(self.ollama_models_edit, 1)
        ollama_models_browse = QPushButton("📁")
        ollama_models_browse.setFixedWidth(40)
        ollama_models_browse.clicked.connect(lambda: self._browse_folder(self.ollama_models_edit))
        ollama_models_layout.addWidget(ollama_models_browse)
        self.ollama_models_status = QLabel("")
        ollama_models_layout.addWidget(self.ollama_models_status)
        ollama_layout.addLayout(ollama_models_layout)

        self.ollama_models_error = QLabel("")
        self.ollama_models_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_models_error.hide()
        ollama_layout.addWidget(self.ollama_models_error)

        # Ollama URL
        ollama_url_layout = QHBoxLayout()
        ollama_url_layout.addWidget(QLabel("URL:"))
        self.ollama_edit = QLineEdit()
        self.ollama_edit.setText(paths["ollama_url"])
        self.ollama_edit.editingFinished.connect(lambda: self._on_path_changed("ollama"))
        ollama_url_layout.addWidget(self.ollama_edit, 1)
        self.ollama_refresh = QPushButton("🔄")
        self.ollama_refresh.setFixedWidth(40)
        self.ollama_refresh.setToolTip("Перепроверить связь с Ollama")
        self.ollama_refresh.clicked.connect(self._start_ollama_retries)
        ollama_url_layout.addWidget(self.ollama_refresh)
        self.ollama_status = QLabel("")
        ollama_url_layout.addWidget(self.ollama_status)
        ollama_layout.addLayout(ollama_url_layout)

        self.ollama_error = QLabel("")
        self.ollama_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_error.hide()
        ollama_layout.addWidget(self.ollama_error)

        ollama_group.setLayout(ollama_layout)
        layout.addWidget(ollama_group)

        layout.addStretch()

        # Первоначальная валидация (кроме Ollama URL — его проверим с retry)
        self._on_path_changed("venv")
        self._on_path_changed("models")
        self._on_path_changed("output")
        self._on_path_changed("ollama_bin")
        self._on_path_changed("ollama_models")
        
        # Запускаем авто-попытки подключения Ollama
        self._start_ollama_retries()

    def _start_ollama_retries(self):
        """Запускает 5 попыток подключения к Ollama с интервалом 1 сек"""
        self._ollama_retry_count = 0
        self.ollama_status.setText("⏳")
        self.ollama_status.setStyleSheet("color: orange;")
        self.ollama_error.setText("Подключение...")
        self.ollama_error.setStyleSheet("color: #DAA520; font-size: 11px;")  # Жёлтый
        self.ollama_error.show()
        self._on_ollama_retry()

    def _on_ollama_retry(self):
        """Одна попытка подключения к Ollama"""
        self._ollama_retry_count += 1
        
        # Проверяем подключение
        result = self.validator.validate_ollama_url(self.ollama_edit.text())
        
        if result["valid"]:
            # Успех
            self._ollama_retry_timer.stop()
            self._update_status(self.ollama_status, self.ollama_error, result)
            self.ollama_error.setText("Подключено")
            self.ollama_error.setStyleSheet("color: green; font-size: 11px;")
            self.ollama_error.show()
            self._check_all_valid()
        elif self._ollama_retry_count < self._ollama_max_retries:
            # Ещё есть попытки
            self.ollama_error.setText(f"Подключение... (попытка {self._ollama_retry_count}/{self._ollama_max_retries})")
            self.ollama_error.setStyleSheet("color: #DAA520; font-size: 11px;")
            self.ollama_error.show()
            self._ollama_retry_timer.start(1000)  # 1 секунда
        else:
            # Все попытки исчерпаны
            self._ollama_retry_timer.stop()
            self._update_status(self.ollama_status, self.ollama_error, result)

    def load_settings(self):
        """Загружает настройки из конфига в UI (через PathsManager)"""
        from core.paths_manager import PathsManager
        pm = PathsManager()
        paths = pm.get_effective_paths(self.config)
        self.venv_edit.setText(paths["sdxl_venv"])
        self.models_edit.setText(paths["sdxl_models"])
        self.output_edit.setText(paths["sdxl_output"])
        self.ollama_edit.setText(paths["ollama_url"])
        self.ollama_bin_edit.setText(paths["ollama_binary"])
        self.ollama_models_edit.setText(paths["ollama_models"])
        self._on_path_changed("venv")
        self._on_path_changed("models")
        self._on_path_changed("output")
        self._on_path_changed("ollama_bin")
        self._on_path_changed("ollama_models")
        self._start_ollama_retries()

    def save_settings(self):
        """Сохраняет настройки из UI в конфиг (ТОЛЬКО через PathsManager)"""
        from core.paths_manager import PathsManager
        pm = PathsManager()
        pm.set_path(self.config, "sdxl_venv", self.venv_edit.text())
        pm.set_path(self.config, "sdxl_models", self.models_edit.text())
        pm.set_path(self.config, "sdxl_output", self.output_edit.text())
        pm.set_path(self.config, "ollama_url", self.ollama_edit.text())
        pm.set_path(self.config, "ollama_binary", self.ollama_bin_edit.text())
        pm.set_path(self.config, "ollama_models", self.ollama_models_edit.text())

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
            # Ручное изменение URL — запускаем retry
            self._start_ollama_retries()
        elif field_name == "ollama_bin":
            result = self.validator.validate_ollama_binary(self.ollama_bin_edit.text())
            self._update_status(self.ollama_bin_status, self.ollama_bin_error, result)
        elif field_name == "ollama_models":
            result = self.validator.validate_ollama_models_path(self.ollama_models_edit.text())
            self._update_status(self.ollama_models_status, self.ollama_models_error, result)
        
        self._check_all_valid()

    def _check_all_valid(self):
        """Проверяет, все ли поля валидны, и эмитит сигнал"""
        venv_valid = self.validator.validate_venv(self.venv_edit.text())["valid"]
        models_valid = self.validator.validate_models_path(self.models_edit.text())["valid"]
        output_valid = self.validator.validate_output_dir(self.output_edit.text())["valid"]
        ollama_valid = self.validator.validate_ollama_url(self.ollama_edit.text())["valid"]
        ollama_bin_valid = self.validator.validate_ollama_binary(self.ollama_bin_edit.text())["valid"]
        
        # Ollama models не критичны (могут быть ещё не скачаны)
        if venv_valid and models_valid and output_valid and ollama_valid and ollama_bin_valid:
            self.all_valid.emit()

    def _update_status(self, status_label, error_label, result):
        """Обновляет индикатор статуса"""
        if result["valid"]:
            status_label.setText("✅")
            status_label.setStyleSheet("color: green;")
            error_label.hide()
        else:
            status_label.setText("❌")
            status_label.setStyleSheet("color: red;")
            error_label.setText(result.get("error", ""))
            error_label.setStyleSheet("color: red; font-size: 11px;")
            error_label.show()

    def _browse_folder(self, line_edit):
        """Открытие диалога выбора папки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку",
            line_edit.text()
        )
        if folder:
            line_edit.setText(folder)
            # Программный setText не эмитит editingFinished — вызываем вручную
            line_edit.editingFinished.emit()

    def _browse_file(self, line_edit):
        """Открытие диалога выбора файла (для бинарника Ollama)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл",
            line_edit.text(),
            "Все файлы (*)"
        )
        if file_path:
            line_edit.setText(file_path)
            # Программный setText не эмитит editingFinished — вызываем вручную
            line_edit.editingFinished.emit()
