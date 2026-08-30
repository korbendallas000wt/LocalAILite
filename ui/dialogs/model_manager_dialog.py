"""
Менеджер моделей (ui/dialogs/model_manager_dialog.py).
Просмотр доступных моделей, вердикты по железу, скачивание с прогрессом и отменой.
"""

import psutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QTreeWidget, QTreeWidgetItem, QLabel, QPushButton, 
                              QProgressBar, QCheckBox, QFrame, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from utils.config import Config
from core.models_registry import (list_available_models, list_installed_ollama_models, 
                                   load_registry)
from core.model_downloader import OllamaDownloader, DiffusersDownloader


# Маппинг секций реестра → флаги features/* (секция diffusers живёт под флагом sdxl)
SECTION_TO_FEATURE = {
    "ollama": "ollama",
    "diffusers": "sdxl",
}


class ModelManagerDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Менеджер моделей")
        self.resize(720, 520)
        
        # Состояние
        self._current_downloader = None
        self._is_downloading = False
        
        # Получаем RAM для вердиктов
        self._total_ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # Получаем доступные модели
        self._available = list_available_models(config)
        
        # Получаем установленные модели
        self._installed_ollama = list_installed_ollama_models(config)
        self._installed_diffusers_registry = load_registry(config)
        
        # UI
        self._setup_ui()
        self._populate_tabs()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Вкладки
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)
        
        # Чекбокс "Только совместимые"
        self._compat_checkbox = QCheckBox("Только совместимые")
        self._compat_checkbox.stateChanged.connect(self._on_compat_filter_changed)
        layout.addWidget(self._compat_checkbox)
        
        # Панель деталей
        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.Shape.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        
        self._details_label = QLabel("Выберите модель для просмотра деталей")
        self._details_label.setWordWrap(True)
        details_layout.addWidget(self._details_label)
        
        layout.addWidget(details_frame)
        
        # Зона загрузки
        download_frame = QFrame()
        download_layout = QVBoxLayout(download_frame)
        
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        download_layout.addWidget(self._progress_bar)
        
        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        download_layout.addWidget(self._status_label)
        
        self._cancel_btn = QPushButton("Отменить")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_download)
        download_layout.addWidget(self._cancel_btn)
        
        layout.addWidget(download_frame)
    
    def _populate_tabs(self):
        """Заполняет вкладки моделями."""
        for section_name, models in self._available.items():
            # Проверяем features/* (diffusers → sdxl)
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue
            
            # Создаём вкладку с QTreeWidget
            tab_widget = QTreeWidget()
            tab_widget.setColumnCount(5)
            tab_widget.setHeaderLabels(["Имя", "Размер", "Мин. ОЗУ", "Статус", "Действие"])
            tab_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            tab_widget.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            tab_widget.setColumnWidth(4, 100)
            
            tab_widget.itemSelectionChanged.connect(
                lambda: self._on_selection_changed()
            )
            
            # Заполняем список моделей
            for model_info in models:
                # Для diffusers проверяем packaging
                if section_name == "diffusers":
                    if model_info.get("packaging") != "hf_cache":
                        continue
                
                # Определяем статус
                is_installed = self._is_installed(section_name, model_info)
                is_compatible = self._is_compatible(model_info)
                
                # Текст элемента
                name = model_info["name"]
                size_gb = model_info.get("size_gb", 0)
                min_ram = model_info.get("min_ram_gb", 0)
                
                status = "✓ Установлена" if is_installed else "Не установлена"
                
                item = QTreeWidgetItem([
                    name,
                    f"{size_gb:.1f} GB",
                    f"{min_ram} GB",
                    status,
                    ""
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, model_info)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, section_name)
                
                # Приглушаем несовместимые
                if not is_compatible:
                    item.setHidden(self._compat_checkbox.isChecked())
                    item.setData(0, Qt.ItemDataRole.UserRole + 2, "incompatible")
                
                tab_widget.addTopLevelItem(item)
                
                # Добавляем кнопку скачивания для неустановленных
                if not is_installed:
                    btn = QPushButton("⬇ Скачать")
                    btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._download_model(s, m)
                    )
                    tab_widget.setItemWidget(item, 4, btn)
            
            self._tabs.addTab(tab_widget, section_name.capitalize())
    
    def _is_installed(self, section: str, model_info: dict) -> bool:
        """Проверяет, установлена ли модель."""
        if section == "ollama":
            source = model_info["source"]
            return source in self._installed_ollama
        elif section == "diffusers":
            # Сравниваем по HF repo id (full_name) — надёжнее, чем по отображаемому имени
            source = model_info["source"]
            for info in self._installed_diffusers_registry.values():
                if isinstance(info, dict) and info.get("full_name") == source:
                    return True
            return False
        return False
    
    def _is_compatible(self, model_info: dict) -> bool:
        """Проверяет совместимость модели с железом."""
        min_ram = model_info.get("min_ram_gb", 0)
        return self._total_ram_gb >= min_ram
    
    def _on_selection_changed(self):
        """Обновляет панель деталей при выборе модели."""
        current_tab = self._tabs.currentWidget()
        if not current_tab or not isinstance(current_tab, QTreeWidget):
            return
        
        items = current_tab.selectedItems()
        if not items:
            self._details_label.setText("Выберите модель для просмотра деталей")
            return
        
        item = items[0]
        model_info = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Формируем текст деталей
        name = model_info["name"]
        source = model_info.get("source", "")
        size_gb = model_info.get("size_gb", 0)
        min_ram = model_info.get("min_ram_gb", 0)
        tag = model_info.get("tag", "")
        description = model_info.get("description", "")
        
        details = f"<b>{name}</b><br>"
        details += f"Тег: {tag}<br>"
        details += f"Размер: {size_gb:.1f} GB<br>"
        details += f"Мин. ОЗУ: {min_ram} GB (у вас {self._total_ram_gb:.1f} GB)<br>"
        details += f"Источник: {source}<br>"
        details += f"<br>{description}"
        
        # Вердикт совместимости
        if not self._is_compatible(model_info):
            details += f"<br><br><font color='orange'>⚠ Нужно {min_ram} ГБ ОЗУ, у вас {self._total_ram_gb:.1f} ГБ</font>"
        
        self._details_label.setText(details)
    
    def _on_compat_filter_changed(self, state):
        """Фильтрует список по совместимости."""
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if isinstance(tab_widget, QTreeWidget):
                for j in range(tab_widget.topLevelItemCount()):
                    item = tab_widget.topLevelItem(j)
                    is_incompatible = item.data(0, Qt.ItemDataRole.UserRole + 2) == "incompatible"
                    if is_incompatible:
                        item.setHidden(state == Qt.CheckState.Checked.value)
    
    def _download_model(self, section: str, model_info: dict):
        """Запускает скачивание модели."""
        if self._is_downloading:
            return
        
        self._is_downloading = True
        
        # Блокируем все кнопки скачивания
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if isinstance(tab_widget, QTreeWidget):
                for j in range(tab_widget.topLevelItemCount()):
                    item = tab_widget.topLevelItem(j)
                    btn = tab_widget.itemWidget(item, 4)
                    if isinstance(btn, QPushButton):
                        btn.setEnabled(False)
        
        # Показываем зону загрузки
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._status_label.setText(f"Начинаем скачивание {model_info['name']}...")
        self._status_label.setVisible(True)
        self._cancel_btn.setVisible(True)
        
        # Создаём загрузчик
        size_gb = model_info.get("size_gb", 2.0)
        
        if section == "ollama":
            self._current_downloader = OllamaDownloader(self.config, model_info["source"])
            self._current_downloader.set_model_size(size_gb)
        elif section == "diffusers":
            self._current_downloader = DiffusersDownloader(self.config, model_info["name"])
            self._current_downloader.set_repo_id(model_info["source"])
            self._current_downloader.set_model_size(size_gb)
        
        # Подключаем сигналы
        self._current_downloader.progress_updated.connect(self._on_progress)
        self._current_downloader.download_finished.connect(self._on_download_finished)
        self._current_downloader.error_occurred.connect(self._on_download_error)
        
        # Запускаем
        self._current_downloader.start()
    
    def _on_progress(self, percent: int, message: str):
        """Обновляет прогресс-бар."""
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)
    
    def _on_download_finished(self, success: bool, message: str):
        """Обрабатывает завершение скачивания."""
        self._is_downloading = False
        self._current_downloader = None
        
        # Разблокируем кнопки
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if isinstance(tab_widget, QTreeWidget):
                for j in range(tab_widget.topLevelItemCount()):
                    item = tab_widget.topLevelItem(j)
                    btn = tab_widget.itemWidget(item, 4)
                    if isinstance(btn, QPushButton):
                        btn.setEnabled(True)
        
        # Скрываем зону загрузки
        self._progress_bar.setVisible(False)
        self._cancel_btn.setVisible(False)
        
        if success:
            # Обновляем список установленных
            self._installed_ollama = list_installed_ollama_models(self.config)
            self._installed_diffusers_registry = load_registry(self.config)
            
            # Перерисовываем вкладки, сохраняя текущую
            current_index = self._tabs.currentIndex()
            self._tabs.clear()
            self._populate_tabs()
            if 0 <= current_index < self._tabs.count():
                self._tabs.setCurrentIndex(current_index)
            
            self._status_label.setText(f"✓ {message}")
        else:
            self._status_label.setText(f"✗ {message}")
    
    def _on_download_error(self, error_msg: str):
        """Обрабатывает ошибку скачивания."""
        self._status_label.setText(f"✗ {error_msg}")
    
    def _cancel_download(self):
        """Отменяет активную загрузку."""
        if self._current_downloader:
            self._current_downloader.cancel()
    
    def closeEvent(self, event):
        """Отменяет загрузку при закрытии диалога."""
        if self._is_downloading and self._current_downloader:
            self._current_downloader.cancel()
        event.accept()
