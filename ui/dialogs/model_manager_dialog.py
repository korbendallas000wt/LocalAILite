"""
Менеджер моделей (ui/dialogs/model_manager_dialog.py).

Единая точка входа для управления моделями:
- Просмотр доступных (список с вердиктами по железу)
- Скачивание с прогрессом и отменой (одна загрузка за раз)
- Удаление установленных (Ollama через 'ollama rm', Diffusers — папка + реестр)
- Проверка целостности установленных моделей

Трёхуровневые вердикты по ДОСТУПНОЙ RAM:
- ✅ Потянет  (min_ram <= 0.90 * available)
- ⚠ Впритык   (0.90 * available < min_ram <= 1.05 * available) — приглушён + совет
- ❌ Не потянет (min_ram > 1.05 * available) — скрывается галочкой «Только совместимые»
"""

import psutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                              QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
                              QProgressBar, QCheckBox, QFrame, QHeaderView,
                              QMessageBox, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from utils.config import Config
from core.models_registry import (list_available_models, list_installed_ollama_models,
                                   load_registry)
from core.model_downloader import OllamaDownloader, DiffusersDownloader
from core.model_lifecycle import (delete_ollama_model, delete_diffusers_model,
                                   validate_installed_model)


# Маппинг секций реестра → флаги features/* (секция diffusers живёт под флагом sdxl)
SECTION_TO_FEATURE = {
    "ollama": "ollama",
    "diffusers": "sdxl",
}


class ModelManagerDialog(QDialog):
    def __init__(self, config: Config, resource_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.resource_manager = resource_manager
        self.setWindowTitle("Менеджер моделей")
        self.resize(780, 560)

        # Состояние
        self._current_downloader = None
        self._is_downloading = False

        # RAM для вердиктов (доступная, не total!)
        vm = psutil.virtual_memory()
        self._available_ram_gb = vm.available / (1024**3)
        self._total_ram_gb = vm.total / (1024**3)

        # Доступные модели
        self._available = list_available_models(config)

        # Установленные модели
        self._installed_ollama = list_installed_ollama_models(config)
        self._installed_diffusers_registry = load_registry(config)

        # UI
        self._setup_ui()
        self._populate_tabs()

    # === Вердикты ===

    def _verdict_level(self, model_info: dict) -> str:
        """Возвращает 'ok', 'warn' или 'no' на основе min_ram_gb и доступной RAM.

        Допуски:
        - ok:  min_ram <= 0.90 * available  (Потянет)
        - warn: 0.90 * available < min_ram <= 1.05 * available  (Впритык)
        - no:  min_ram > 1.05 * available  (Не потянет)
        """
        min_ram = model_info.get("min_ram_gb", 0)
        if min_ram <= 0:
            return "ok"

        threshold_warn = 0.90 * self._available_ram_gb
        threshold_no = 1.05 * self._available_ram_gb

        if min_ram <= threshold_warn:
            return "ok"
        elif min_ram <= threshold_no:
            return "warn"
        else:
            return "no"

    # === UI ===

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Вкладки
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        # Чекбокс "Только совместимые" (скрывает только ❌)
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
        """Заполняет вкладки моделями с кнопками действий."""
        for section_name, models in self._available.items():
            # Фильтр по features/* (diffusers → sdxl)
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue

            tab_widget = QTreeWidget()
            tab_widget.setColumnCount(5)
            tab_widget.setHeaderLabels(["Имя", "Размер", "Мин. ОЗУ", "Статус", "Действие"])
            tab_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for col in (1, 2, 3):
                tab_widget.header().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            tab_widget.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            tab_widget.setColumnWidth(4, 170)

            tab_widget.itemSelectionChanged.connect(self._on_selection_changed)

            for model_info in models:
                if section_name == "diffusers":
                    if model_info.get("packaging") != "hf_cache":
                        continue

                is_installed = self._is_installed(section_name, model_info)
                verdict = self._verdict_level(model_info)

                name = model_info["name"]
                size_gb = model_info.get("size_gb", 0)
                min_ram = model_info.get("min_ram_gb", 0)

                status_text = "✓ Установлена" if is_installed else "Не установлена"

                item = QTreeWidgetItem([
                    name,
                    f"{size_gb:.1f} GB",
                    f"{min_ram} GB",
                    status_text,
                    ""
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, model_info)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, section_name)
                item.setData(0, Qt.ItemDataRole.UserRole + 3, verdict)
                item.setData(0, Qt.ItemDataRole.UserRole + 4, is_installed)

                # Приглушаем ⚠ (но не скрываем)
                if verdict == "warn":
                    pal = self.palette()
                    dim_color = pal.color(QPalette.ColorRole.WindowText)
                    dim_color.setAlpha(120)
                    from PyQt6.QtGui import QColor, QBrush
                    for col in range(5):
                        item.setForeground(col, QBrush(QColor(dim_color)))

                tab_widget.addTopLevelItem(item)

                # Виджет с кнопками действий
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(4, 2, 4, 2)
                action_layout.setSpacing(4)

                if is_installed:
                    validate_btn = QPushButton("🔍")
                    validate_btn.setToolTip("Проверить целостность")
                    validate_btn.setFixedWidth(40)
                    validate_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._validate_model(s, m)
                    )
                    action_layout.addWidget(validate_btn)

                    delete_btn = QPushButton("🗑 Удалить")
                    delete_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._delete_model(s, m)
                    )
                    action_layout.addWidget(delete_btn)
                else:
                    download_btn = QPushButton("⬇ Скачать")
                    download_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._download_model(s, m)
                    )
                    action_layout.addWidget(download_btn)

                tab_widget.setItemWidget(item, 4, action_widget)

            self._tabs.addTab(tab_widget, section_name.capitalize())

        # Применяем фильтр сразу
        self._on_compat_filter_changed(self._compat_checkbox.checkState())

    def _is_installed(self, section: str, model_info: dict) -> bool:
        if section == "ollama":
            return model_info["source"] in self._installed_ollama
        elif section == "diffusers":
            source = model_info["source"]
            for info in self._installed_diffusers_registry.values():
                if isinstance(info, dict) and info.get("full_name") == source:
                    return True
            return False
        return False

    # === Панель деталей ===

    def _on_selection_changed(self):
        current_tab = self._tabs.currentWidget()
        if not current_tab or not isinstance(current_tab, QTreeWidget):
            return

        items = current_tab.selectedItems()
        if not items:
            self._details_label.setText("Выберите модель для просмотра деталей")
            return

        item = items[0]
        model_info = item.data(0, Qt.ItemDataRole.UserRole)
        verdict = item.data(0, Qt.ItemDataRole.UserRole + 3)

        name = model_info["name"]
        source = model_info.get("source", "")
        size_gb = model_info.get("size_gb", 0)
        min_ram = model_info.get("min_ram_gb", 0)
        tag = model_info.get("tag", "")
        description = model_info.get("description", "")

        details = f"<b>{name}</b><br>"
        details += f"Тег: {tag}<br>"
        details += f"Размер: {size_gb:.1f} GB<br>"
        details += f"Мин. ОЗУ: {min_ram} GB (у вас {self._available_ram_gb:.1f} GB свободно / {self._total_ram_gb:.1f} GB всего)<br>"
        details += f"Источник: {source}<br>"
        details += f"<br>{description}"

        # Вердикт совместимости (трёхуровневый)
        if verdict == "ok":
            details += f"<br><br><font color='green'>✅ Потянет</font>"
        elif verdict == "warn":
            details += (f"<br><br><font color='orange'>⚠ Впритык — модель потребует "
                        f"~{min_ram} ГБ, у вас свободно {self._available_ram_gb:.1f} ГБ. "
                        f"Совет: закройте другие приложения перед запуском.</font>")
        else:
            details += (f"<br><br><font color='red'>❌ Не потянет — нужно {min_ram} ГБ, "
                        f"у вас свободно {self._available_ram_gb:.1f} ГБ.</font>")

        self._details_label.setText(details)

    def _on_compat_filter_changed(self, state):
        """Скрывает ТОЛЬКО модели с вердиктом ❌ (не трогает ⚠)."""
        hide_incompatible = (state == Qt.CheckState.Checked.value)
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if not isinstance(tab_widget, QTreeWidget):
                continue
            for j in range(tab_widget.topLevelItemCount()):
                item = tab_widget.topLevelItem(j)
                verdict = item.data(0, Qt.ItemDataRole.UserRole + 3)
                if verdict == "no":
                    item.setHidden(hide_incompatible)
                else:
                    item.setHidden(False)

    # === Проверка занятости ресурса ===

    def _is_resource_busy(self) -> bool:
        return (self.resource_manager is not None and
                self.resource_manager.is_resource_busy())

    def _show_busy_warning(self):
        QMessageBox.warning(
            self,
            "Ресурс занят",
            "Сейчас идёт генерация в другом модуле.\n\n"
            "Остановите генерацию, чтобы управлять моделями."
        )

    # === Скачивание ===

    def _download_model(self, section: str, model_info: dict):
        if self._is_downloading:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        self._is_downloading = True

        # Блокируем все кнопки действий
        self._set_all_action_buttons_enabled(False)

        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._status_label.setText(f"Начинаем скачивание {model_info['name']}...")
        self._status_label.setVisible(True)
        self._cancel_btn.setVisible(True)

        size_gb = model_info.get("size_gb", 2.0)

        if section == "ollama":
            self._current_downloader = OllamaDownloader(self.config, model_info["source"])
            self._current_downloader.set_model_size(size_gb)
        elif section == "diffusers":
            self._current_downloader = DiffusersDownloader(self.config, model_info["name"])
            self._current_downloader.set_repo_id(model_info["source"])
            self._current_downloader.set_model_size(size_gb)

        self._current_downloader.progress_updated.connect(self._on_progress)
        self._current_downloader.download_finished.connect(self._on_download_finished)
        self._current_downloader.error_occurred.connect(self._on_download_error)
        self._current_downloader.start()

    def _on_progress(self, percent: int, message: str):
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_download_finished(self, success: bool, message: str):
        self._is_downloading = False
        self._current_downloader = None

        self._set_all_action_buttons_enabled(True)

        self._progress_bar.setVisible(False)
        self._cancel_btn.setVisible(False)

        if success:
            self._installed_ollama = list_installed_ollama_models(self.config)
            self._installed_diffusers_registry = load_registry(self.config)

            current_index = self._tabs.currentIndex()
            self._tabs.clear()
            self._populate_tabs()
            if 0 <= current_index < self._tabs.count():
                self._tabs.setCurrentIndex(current_index)

            self._status_label.setText(f"✓ {message}")
        else:
            self._status_label.setText(f"✗ {message}")

    def _on_download_error(self, error_msg: str):
        self._status_label.setText(f"✗ {error_msg}")

    def _cancel_download(self):
        if self._current_downloader:
            self._current_downloader.cancel()

    # === Удаление ===

    def _delete_model(self, section: str, model_info: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        name = model_info["name"]
        source = model_info.get("source", "")

        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить модель:\n\n<b>{name}</b>\n({source})\n\n"
            f"{'Файлы модели будут удалены с диска.' if section == 'diffusers' else 'Модель будет удалена из Ollama.'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if section == "ollama":
            result = delete_ollama_model(source, self.config)
        else:
            result = delete_diffusers_model(source, self.config)

        if result["success"]:
            QMessageBox.information(self, "Готово", result["message"])
        else:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить:\n{result['message']}")
            return

        # Обновляем списки и перерисовываем
        self._installed_ollama = list_installed_ollama_models(self.config)
        self._installed_diffusers_registry = load_registry(self.config)

        current_index = self._tabs.currentIndex()
        self._tabs.clear()
        self._populate_tabs()
        if 0 <= current_index < self._tabs.count():
            self._tabs.setCurrentIndex(current_index)

    # === Проверка валидности ===

    def _validate_model(self, section: str, model_info: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        name = model_info["name"]
        source = model_info.get("source", "")

        self._status_label.setText(f"Проверка {name}...")
        self._status_label.setVisible(True)

        result = validate_installed_model(source, section, self.config)

        if not result["success"]:
            QMessageBox.warning(
                self, "Проверка не удалась",
                f"Модель: {name}\n\nОшибки:\n" + "\n".join(result["errors"])
            )
        elif result["valid"]:
            msg = f"✅ Модель {name} цела и валидна"
            if result["warnings"]:
                msg += "\n\nПредупреждения:\n" + "\n".join(result["warnings"])
            QMessageBox.information(self, "Проверка целостности", msg)
        else:
            QMessageBox.critical(
                self, "Модель повреждена",
                f"Модель: {name}\n\nОшибки:\n" + "\n".join(result["errors"])
            )

        self._status_label.setVisible(False)

    # === Утилиты ===

    def _set_all_action_buttons_enabled(self, enabled: bool):
        """Включает/выключает все кнопки действий во всех вкладках."""
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if not isinstance(tab_widget, QTreeWidget):
                continue
            for j in range(tab_widget.topLevelItemCount()):
                item = tab_widget.topLevelItem(j)
                widget = tab_widget.itemWidget(item, 4)
                if isinstance(widget, QWidget):
                    for btn in widget.findChildren(QPushButton):
                        btn.setEnabled(enabled)

    def closeEvent(self, event):
        """Отменяет загрузку при закрытии диалога."""
        if self._is_downloading and self._current_downloader:
            self._current_downloader.cancel()
        event.accept()
