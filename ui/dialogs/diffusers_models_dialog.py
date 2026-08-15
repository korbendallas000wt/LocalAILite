from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QPushButton, QListWidget,
                              QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
import os
import shutil
import subprocess


class DiffusersModelsDialog(QDialog):
    """Диалог управления моделями Diffusers"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.models_path = config.get_sdxl_models_path()

        self.setWindowTitle("Управление моделями Diffusers")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)

        # Группа ссылок на ресурсы (через PathsManager)
        from core.paths_manager import PathsManager
        pm = PathsManager()
        sources = pm.get_model_sources().get("sdxl", [])
        links_group = QGroupBox("Где найти модели")
        links_layout = QVBoxLayout()

        for source in sources:
            link_btn = QPushButton(source["label"])
            link_btn.setStyleSheet("text-align: left; padding: 5px;")
            link_btn.clicked.connect(lambda checked, u=source["url"]: QDesktopServices.openUrl(QUrl(u)))
            links_layout.addWidget(link_btn)

        links_group.setLayout(links_layout)
        layout.addWidget(links_group)

        # Группа списка моделей
        models_group = QGroupBox("Установленные модели")
        models_layout = QVBoxLayout()

        # Список моделей
        self.models_list = QListWidget()
        self.models_list.itemSelectionChanged.connect(self._on_model_selected)
        models_layout.addWidget(self.models_list, 1)

        # Кнопки управления
        buttons_layout = QHBoxLayout()

        self.open_folder_btn = QPushButton("📂 Открыть папку")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        buttons_layout.addWidget(self.open_folder_btn)

        self.delete_btn = QPushButton("🗑 Удалить")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        buttons_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self._load_models)
        buttons_layout.addWidget(self.refresh_btn)

        models_layout.addLayout(buttons_layout)

        models_group.setLayout(models_layout)
        layout.addWidget(models_group)

        # Загружаем список моделей
        self._load_models()

    def _load_models(self):
        """Загружает список установленных моделей из реестра v2.0.
        Показывает короткие имена + полное имя с типом.
        """
        self.models_list.clear()

        from core.models_registry import load_registry
        registry = load_registry(self.config)
        if not registry:
            return

        # Иконки и подписи по типу модели
        type_icons = {"hf_cache": "📦", "file": "📄", "folder": "📁"}
        type_labels = {"hf_cache": "HF cache", "file": "файл", "folder": "папка"}

        for display_name, info in sorted(registry.items()):
            if not isinstance(info, dict):
                continue
            model_type = info.get("type", "file")
            full_name = info.get("full_name", "")
            icon = type_icons.get(model_type, "❓")
            # Показываем: иконка + короткое имя (тип: полное имя)
            label = f"{icon} {display_name} ({type_labels.get(model_type, '?')}: {full_name})"
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.ItemDataRole.UserRole, info.get("path", ""))
            self.models_list.addItem(list_item)

    def _on_model_selected(self):
        """Обновляет доступность кнопки удаления"""
        self.delete_btn.setEnabled(len(self.models_list.selectedItems()) > 0)

    def _on_open_folder(self):
        """Открывает папку моделей в файловом менеджере"""
        if self.models_path and os.path.exists(self.models_path):
            subprocess.run(['xdg-open', self.models_path])

    def _on_delete(self):
        """Удаляет выбранную модель"""
        selected_items = self.models_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        model_path = item.data(Qt.ItemDataRole.UserRole)
        model_name = item.text()

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить модель:\n{model_name}?\n\nПуть: {model_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(model_path):
                    shutil.rmtree(model_path)
                else:
                    os.remove(model_path)

                self._load_models()
                QMessageBox.information(self, "Готово", "Модель удалена")

            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить:\n{str(e)}")
