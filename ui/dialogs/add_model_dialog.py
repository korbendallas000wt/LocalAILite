"""
Диалог добавления модели (ui/dialogs/add_model_dialog.py).

Две вкладки:
1. По ссылке — HF repo ID для Diffusers / имя:тег для Ollama
2. С диска — выбор пути к папке/файлу

После добавления модель регистрируется в реестре v3.0 и появляется в менеджере.
"""

import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                              QWidget, QLabel, QLineEdit, QPushButton,
                              QFileDialog, QMessageBox, QComboBox)
from PyQt6.QtCore import Qt
from utils.config import Config
from core.models_registry import register_from_path, add_model_by_ref
from core.paths_manager import PathsManager


class AddModelDialog(QDialog):
    """Диалог добавления модели (по ссылке или с диска)."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Добавить модель")
        self.resize(500, 300)
        self.setMinimumSize(450, 250)

        self._result = None  # {"model_id": str, "type": str} или None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Вкладки: по ссылке / с диска
        self._tabs = QTabWidget()

        # === Вкладка 1: По ссылке ===
        url_tab = QWidget()
        url_layout = QVBoxLayout(url_tab)

        url_layout.addWidget(QLabel("<b>Добавить модель по ссылке</b>"))

        # Тип модели
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Тип:"))
        self._url_type_combo = QComboBox()
        self._url_type_combo.addItems(["Ollama", "Diffusers"])
        type_layout.addWidget(self._url_type_combo)
        url_layout.addLayout(type_layout)

        # Ссылка
        url_layout.addWidget(QLabel("Ссылка:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("Ollama: qwen2.5:14b  /  Diffusers: stabilityai/stable-diffusion-xl-base-1.0")
        url_layout.addWidget(self._url_edit)

        url_layout.addStretch()
        self._tabs.addTab(url_tab, "По ссылке")

        # === Вкладка 2: С диска ===
        disk_tab = QWidget()
        disk_layout = QVBoxLayout(disk_tab)

        disk_layout.addWidget(QLabel("<b>Добавить модель с диска</b>"))

        # Тип модели
        disk_type_layout = QHBoxLayout()
        disk_type_layout.addWidget(QLabel("Тип:"))
        self._disk_type_combo = QComboBox()
        self._disk_type_combo.addItems(["Ollama", "Diffusers"])
        disk_type_layout.addWidget(self._disk_type_combo)
        disk_layout.addLayout(disk_type_layout)

        # Путь
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Путь к папке модели или файлу .safetensors/.gguf")
        path_layout.addWidget(self._path_edit)
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self._browse_path)
        path_layout.addWidget(browse_btn)
        disk_layout.addLayout(path_layout)

        disk_layout.addStretch()
        self._tabs.addTab(disk_tab, "С диска")

        layout.addWidget(self._tabs)

        # Кнопки OK / Cancel
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_path(self):
        """Выбор пути через QFileDialog."""
        pm = PathsManager()
        models_path = pm.get_path(self.config, "sdxl_models")
        start_dir = models_path if models_path and os.path.exists(models_path) else os.path.expanduser("~")

        path = QFileDialog.getExistingDirectory(self, "Выберите папку модели", start_dir)
        if path:
            self._path_edit.setText(path)

    def _on_ok(self):
        """Обработка OK: регистрация модели."""
        if self._tabs.currentIndex() == 0:
            # По ссылке
            ref = self._url_edit.text().strip()
            if not ref:
                QMessageBox.warning(self, "Ошибка", "Укажите ссылку")
                return
            model_type = "ollama" if self._url_type_combo.currentText() == "Ollama" else "diffusers"
            # Базовая проверка формата
            if model_type == "diffusers" and "/" not in ref:
                QMessageBox.warning(self, "Ошибка",
                                    "Для Diffusers укажите репо в формате «автор/модель»")
                return
            if model_type == "ollama" and ":" not in ref:
                ref = ref + ":latest"
            model_id = add_model_by_ref(self.config, ref, model_type)
            if not model_id:
                QMessageBox.warning(self, "Ошибка", "Не удалось добавить модель")
                return
            self._result = {"model_id": model_id, "type": model_type}
            self.accept()
        else:
            # С диска
            path = self._path_edit.text().strip()
            if not path or not os.path.exists(path):
                QMessageBox.warning(self, "Ошибка", "Укажите существующий путь")
                return

            model_type = "ollama" if self._disk_type_combo.currentText() == "Ollama" else "diffusers"
            model_id = register_from_path(path, model_type, self.config)

            if not model_id:
                QMessageBox.warning(self, "Ошибка", "Не удалось зарегистрировать модель")
                return

            self._result = {"model_id": model_id, "type": model_type}
            self.accept()

    def get_result(self) -> dict:
        """Возвращает результат: {"model_id": str, "type": str} или None."""
        return self._result

