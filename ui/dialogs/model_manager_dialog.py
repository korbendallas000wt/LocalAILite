"""
Менеджер моделей v3 (ui/dialogs/model_manager_dialog.py).

Единая точка входа для управления моделями на основе реестра v3.0
(статусы вычисляются сверкой с диском):

- 5 статусов: Скачать / Закачана / Валидна / Установлена / Невалидна
- Вкладки по типам (Ollama / Diffusers)
- Объединение источников: каталог + реестр v3.0 + обнаруженные при сканировании
- Информация о модели: 3 колонки (Данные / Описание / Вердикт и проверка)
- При клике на строку: заполнение колонок + автоматическая быстрая проверка
- Тулбар: [+ Добавить] [Обновить] + фильтр «Только совместимые»

Кнопки в колонке «Действие» (2 кнопки, зависят от статуса):
- Скачать:      [Вердикт]        [Загрузить]
- Закачана:     [Проверить]      [Удалить файлы]
- Валидна:      [Установить]     [Удалить]
- Установлена:  [Проверить]      [Удалить]
- Невалидна:    [Проверить]      [Перекачать]
"""

import psutil
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                              QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
                              QProgressBar, QCheckBox, QHeaderView,
                              QMessageBox, QWidget, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush
from utils.config import Config
from core.models_registry import (list_available_models, list_installed_ollama_models,
                                   list_all_models, update_model_validation)
from core.model_verifier import DeepValidationWorker
from core.model_installer import (DiffusersInstallWorker, OllamaInstallWorker,
                                   derive_ollama_name_from_gguf)
from core.model_downloader import OllamaDownloader, DiffusersDownloader
from core.model_lifecycle import delete_ollama_model, delete_diffusers_model
from core.model_validator import validate_model_fast, validate_ollama_model
from core.paths_manager import PathsManager
from ui.dialogs.add_model_dialog import AddModelDialog


# Маппинг секций реестра → флаги features/* (diffusers живёт под флагом sdxl)
SECTION_TO_FEATURE = {
    "ollama": "ollama",
    "diffusers": "sdxl",
}

# Статусы: цвет (RGB) и подпись
STATUS_COLORS = {
    "download":   (150, 150, 150),  # серый
    "downloaded": (70, 130, 220),   # синий
    "valid":      (60, 170, 80),    # зелёный
    "installed":  (30, 130, 60),    # тёмно-зелёный
    "invalid":    (220, 70, 70),    # красный
}
STATUS_LABELS = {
    "download":   "Скачать",
    "downloaded": "Закачана",
    "valid":      "Валидна",
    "installed":  "Установлена",
    "invalid":    "Невалидна",
}

# Единый размер кнопок действий
BTN_WIDTH = 92
BTN_HEIGHT = 22

# Пропорции колонок 0-4 (в сумме 0.72). Колонка 5 «Действие» получает остаток.
COLUMN_PERCENTS = [0.03, 0.26, 0.10, 0.12, 0.14]

TREE_STYLE = (
    "QTreeWidget::item {"
    "  border-bottom: 1px solid rgba(128, 128, 128, 60);"
    "  padding: 3px 2px;"
    "}"
)


class ModelManagerDialog(QDialog):
    def __init__(self, config: Config, resource_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.resource_manager = resource_manager
        self.setWindowTitle("Менеджер моделей")
        self.resize(820, 600)
        self.setMinimumSize(760, 520)

        # Состояние загрузки
        self._current_downloader = None
        self._is_downloading = False
        self._row_buttons = {}
        # Что качаем (для автопроверки после загрузки)
        self._downloading_section = None
        self._downloading_source = None

        # Состояние глубокой проверки
        self._current_verifier = None
        self._is_verifying = False
        self._verifying_model_id = None

        # Состояние установки
        self._current_installer = None
        self._is_installing = False
        self._installing_model_id = None

        # RAM для вердиктов — УСТАНОВЛЕННАЯ (стабильная)
        vm = psutil.virtual_memory()
        self._total_ram_gb = vm.total / (1024**3)

        # Загрузка данных (каталог + реестр v3.0 + обнаруженные)
        self._load_data()

        # UI
        self._setup_ui()
        self._populate_tabs()

    # === Загрузка данных ===

    def _load_data(self):
        """Загружает каталог, реестр v3.0 и обнаруженные Ollama-модели."""
        self._available = list_available_models(self.config)
        self._registry_models = list_all_models(self.config)  # вызывает reconcile
        self._installed_ollama = list_installed_ollama_models(self.config)

    # === Вердикты по установленной RAM ===

    def _verdict_level(self, model_row: dict) -> str:
        """Возвращает 'ok', 'warn' или 'no' на основе min_ram_gb и УСТАНОВЛЕННОЙ RAM."""
        min_ram = model_row.get("min_ram_gb", 0)
        if min_ram <= 0:
            return "ok"
        total = self._total_ram_gb
        if min_ram <= 0.90 * total:
            return "ok"
        elif min_ram <= 1.05 * total:
            return "warn"
        return "no"

    # === UI ===

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # === Тулбар ===
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("+ Добавить")
        self._add_btn.setToolTip("Добавить модель по ссылке или с диска")
        self._add_btn.clicked.connect(self._on_add_model)
        toolbar.addWidget(self._add_btn)

        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.setToolTip("Перечитать реестр и пересканировать папку моделей")
        self._refresh_btn.clicked.connect(self._refresh_tabs)
        toolbar.addWidget(self._refresh_btn)

        toolbar.addStretch()

        self._compat_checkbox = QCheckBox("Только совместимые")
        self._compat_checkbox.stateChanged.connect(self._on_compat_filter_changed)
        toolbar.addWidget(self._compat_checkbox)
        layout.addLayout(toolbar)

        # === Блок 1: Список моделей (вкладки) ===
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, 1)

        # === Блок 2: Статус операции ===
        status_layout = QVBoxLayout()
        status_layout.setSpacing(6)
        self._status_label = QLabel("Готов к работе")
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)  # скрыт, пока нет операции
        status_layout.addWidget(self._status_label)
        status_layout.addWidget(self._progress_bar)
        layout.addLayout(status_layout)

        # === Блок 3: Информация о модели (3 колонки) ===
        info_layout = QHBoxLayout()
        info_layout.setSpacing(10)

        # Колонка 1: Данные
        self._meta_label = QLabel("Выберите модель")
        self._meta_label.setFixedWidth(230)
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._meta_label.setWordWrap(True)
        info_layout.addWidget(self._meta_label)

        # Колонка 2: Описание
        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._desc_label, 1)

        # Колонка 3: Вердикт и проверка
        self._verdict_label = QLabel("")
        self._verdict_label.setFixedWidth(230)
        self._verdict_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._verdict_label.setWordWrap(True)
        info_layout.addWidget(self._verdict_label)

        # Обёртка с фиксированной высотой
        info_widget = QWidget()
        info_widget.setFixedHeight(170)
        info_widget.setLayout(info_layout)
        layout.addWidget(info_widget)

    def _create_tree_widget(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(6)
        tree.setHeaderLabels(["№", "Имя", "Размер", "Мин. ОЗУ", "Статус", "Действие"])

        header = tree.header()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tree.setStyleSheet(TREE_STYLE)
        tree.itemClicked.connect(self._on_item_clicked)
        return tree

    def _apply_column_widths(self, tree: QTreeWidget):
        viewport_w = tree.viewport().width() - 22
        if viewport_w <= 10:
            return
        used = 0
        for col, pct in enumerate(COLUMN_PERCENTS):
            w = int(viewport_w * pct)
            tree.setColumnWidth(col, w)
            used += w
        action_w = max(viewport_w - used, BTN_WIDTH * 2 + 24)
        tree.setColumnWidth(5, action_w)

    def _apply_all_column_widths(self):
        for i in range(self._tabs.count()):
            tree = self._tabs.widget(i)
            if isinstance(tree, QTreeWidget):
                self._apply_column_widths(tree)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._apply_all_column_widths)

    # === Построение списка моделей ===

    def _build_model_list(self, section: str) -> list:
        """Объединяет каталог + реестр v3.0 + обнаруженные модели для секции."""
        models = []
        seen = set()

        # 1. Каталог
        for cat_model in self._available.get(section, []):
            if section == "diffusers" and cat_model.get("packaging") != "hf_cache":
                continue
            source = cat_model["source"]
            reg = self._find_in_registry(section, source)
            if reg:
                # Модель есть в реестре v3.0 — берём её статус и id
                status = reg["status"]
                model_id = reg["model_id"]
                path = reg["paths"].get("installed", "")
            elif section == "ollama" and source in self._installed_ollama:
                # Fallback: нет в реестре, но есть в манифестах Ollama
                status = "installed"
                model_id = None
                path = ""
            else:
                status = "download"
                model_id = None
                path = ""

            models.append({
                "name": cat_model["name"],
                "size_gb": cat_model.get("size_gb", 0),
                "min_ram_gb": cat_model.get("min_ram_gb", 0),
                "description": cat_model.get("description", ""),
                "source": source,
                "status": status,
                "model_id": model_id,
                "path": path,
                "origin": "catalog",
            })
            seen.add(source)

        # 2. Реестр: модели, которых нет в каталоге
        for reg_model in self._registry_models:
            if reg_model["type"] != section:
                continue
            ref = reg_model["source"].get("ref", "")
            if not ref or ref in seen:
                continue
            seen.add(ref)
            meta = reg_model.get("meta", {})
            models.append({
                "name": reg_model["display_name"],
                "size_gb": meta.get("size_gb", 0),
                "min_ram_gb": meta.get("min_ram_gb", 0),
                "description": meta.get("description", ""),
                "source": ref,
                "status": reg_model["status"],
                "model_id": reg_model["model_id"],
                "path": reg_model["paths"].get("installed", ""),
                "origin": "registry",
            })

        # 3. Обнаруженные Ollama (через манифесты), которых нет нигде
        if section == "ollama":
            for ollama_name in self._installed_ollama:
                if ollama_name in seen:
                    continue
                seen.add(ollama_name)
                models.append({
                    "name": ollama_name,
                    "size_gb": 0,
                    "min_ram_gb": 0,
                    "description": "(обнаружена в папке Ollama)",
                    "source": ollama_name,
                    "status": "installed",
                    "model_id": None,
                    "path": "",
                    "origin": "discovered",
                })

        return models

    def _find_in_registry(self, section: str, source: str) -> dict:
        """Ищет модель в реестре v3.0 по типу и источнику."""
        for reg_model in self._registry_models:
            if reg_model["type"] != section:
                continue
            if reg_model["source"].get("ref") == source:
                return reg_model
        return None

    # === Заполнение вкладок ===

    def _populate_tabs(self):
        self._row_buttons = {}
        self._tabs.clear()

        for section_name in self._available.keys():
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue

            tab_widget = self._create_tree_widget()
            model_list = self._build_model_list(section_name)

            for row_num, model_row in enumerate(model_list, 1):
                status = model_row["status"]
                status_text = STATUS_LABELS.get(status, status)
                status_color = STATUS_COLORS.get(status, (150, 150, 150))

                size_gb = model_row["size_gb"]
                min_ram = model_row["min_ram_gb"]

                item = QTreeWidgetItem([
                    str(row_num),
                    model_row["name"],
                    f"{size_gb:.1f} GB" if size_gb > 0 else "—",
                    f"{min_ram} GB" if min_ram > 0 else "—",
                    status_text,
                    ""
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, model_row)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, section_name)

                # Центрируем служебные колонки
                for col in (0, 2, 3, 4):
                    item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)

                # Цвет статуса
                item.setForeground(4, QBrush(QColor(*status_color)))

                # Приглушаем несовместимые (вердикт ❌)
                if self._verdict_level(model_row) == "no":
                    dim = QColor(150, 150, 150)
                    for col in range(6):
                        if col != 4:
                            item.setForeground(col, QBrush(dim))

                tab_widget.addTopLevelItem(item)

                # Кнопки действий
                self._create_action_buttons(tab_widget, item, model_row, section_name)

            self._tabs.addTab(tab_widget, section_name.capitalize())

        self._on_compat_filter_changed(self._compat_checkbox.checkState())
        QTimer.singleShot(0, self._apply_all_column_widths)

    def _create_action_buttons(self, tree, item, model_row, section_name):
        """Создаёт 2 кнопки действий в зависимости от статуса."""
        status = model_row["status"]
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(4, 2, 4, 2)
        action_layout.setSpacing(6)

        info_btn = QPushButton()
        info_btn.setFixedSize(BTN_WIDTH, BTN_HEIGHT)
        state_btn = QPushButton()
        state_btn.setFixedSize(BTN_WIDTH, BTN_HEIGHT)

        m = model_row
        s = section_name

        if status == "download":
            info_btn.setText("Вердикт")
            info_btn.setToolTip("Вердикт по железу (ОЗУ)")
            info_btn.clicked.connect(lambda checked, m=m, s=s: self._show_verdict(m))
            state_btn.setText("Загрузить")
            state_btn.setToolTip("Скачать модель")
            state_btn.clicked.connect(lambda checked, m=m, s=s: self._download_model(s, m))
        elif status in ("downloaded", "valid", "installed", "invalid"):
            info_btn.setText("Полная")
            info_btn.setToolTip("Полная проверка: сверка хэшей всех файлов (долго)")
            info_btn.clicked.connect(lambda checked, m=m, s=s: self._deep_validate_model(s, m))
            if status == "valid":
                state_btn.setText("Установить")
                state_btn.setToolTip("Переместить в папку моделей")
                state_btn.clicked.connect(lambda checked, m=m, s=s: self._install_model(s, m))
            elif status == "invalid":
                state_btn.setText("Перекачать")
                state_btn.setToolTip("Скачать заново")
                state_btn.clicked.connect(lambda checked, m=m, s=s: self._download_model(s, m))
            else:
                state_btn.setText("Удалить")
                state_btn.setToolTip("Удалить модель")
                state_btn.clicked.connect(lambda checked, m=m, s=s: self._delete_model(s, m))

        action_layout.addWidget(info_btn)
        action_layout.addWidget(state_btn)
        tree.setItemWidget(item, 5, action_widget)

        key = (section_name, model_row.get("source", model_row["name"]))
        self._row_buttons[key] = {"state_btn": state_btn, "info_btn": info_btn}

    # === Панель деталей (3 колонки) ===

    def _on_item_clicked(self, item, column):
        model_row = item.data(0, Qt.ItemDataRole.UserRole)
        section = item.data(0, Qt.ItemDataRole.UserRole + 1)
        self._update_details(model_row, section)

    def _update_details(self, model_row: dict, section: str):
        """Заполняет 3 колонки: Данные / Описание / Вердикт и проверка."""
        # Колонка 1: Данные
        name = model_row["name"]
        source = model_row.get("source", "")
        size_gb = model_row.get("size_gb", 0)
        min_ram = model_row.get("min_ram_gb", 0)
        path = model_row.get("path", "")
        origin = model_row.get("origin", "")

        meta = f"<b>{name}</b><br>"
        meta += f"Размер: {size_gb:.1f} GB<br>" if size_gb > 0 else "Размер: —<br>"
        meta += f"Мин. ОЗУ: {min_ram} GB<br>" if min_ram > 0 else "Мин. ОЗУ: —<br>"
        meta += f"Источник: {source}<br>"
        if path:
            meta += f"Путь: {path}"
        self._meta_label.setText(meta)

        # Колонка 2: Описание
        self._desc_label.setText(model_row.get("description", ""))

        # Колонка 3: Вердикт по железу + быстрая проверка
        verdict = self._verdict_level(model_row)
        total = self._total_ram_gb
        if verdict == "ok":
            verdict_text = f"ОЗУ: ✅ {min_ram} ГБ из {total:.1f} ГБ — потянет"
        elif verdict == "warn":
            verdict_text = f"ОЗУ: ⚠ {min_ram} ГБ из {total:.1f} ГБ — впритык"
        else:
            verdict_text = f"ОЗУ: ❌ {min_ram} ГБ из {total:.1f} ГБ — не потянет"

        # Быстрая проверка (автоматически при клике)
        check_result = self._quick_check(model_row, section)
        self._verdict_label.setText(f"{verdict_text}<br><br>{check_result}")

    def _quick_check(self, model_row: dict, section: str) -> str:
        """Быстрая проверка модели. Возвращает HTML для 3-й колонки."""
        status = model_row["status"]
        path = model_row.get("path", "")
        source = model_row.get("source", "")

        # Не скачана — проверять нечего
        if status == "download" or (not path and section == "diffusers"):
            return "Быстрая проверка: —<br><i>Модель не скачана</i>"

        try:
            if section == "ollama":
                pm = PathsManager()
                ollama_path = pm.get_path(self.config, "ollama_models")
                result = validate_ollama_model(source, ollama_path)
            else:
                if not path or not os.path.exists(path):
                    return "Быстрая проверка: ❌<br><i>Путь не найден</i>"
                result = validate_model_fast(path)

            if result.valid:
                return "Быстрая проверка: ✅ Валидна"
            else:
                errors = "<br>".join(f"• {e}" for e in result.errors[:3])
                return f"Быстрая проверка: ❌ Невалидна<br>{errors}"
        except Exception as e:
            return f"Быстрая проверка: ⚠<br><i>Ошибка: {e}</i>"

    def _on_tab_changed(self, index):
        self._meta_label.setText("Выберите модель")
        self._desc_label.setText("")
        self._verdict_label.setText("")

    def _on_compat_filter_changed(self, state):
        """Скрывает модели с вердиктом ❌ (не трогает ⚠)."""
        hide_incompatible = (state == Qt.CheckState.Checked.value)
        for i in range(self._tabs.count()):
            tab_widget = self._tabs.widget(i)
            if not isinstance(tab_widget, QTreeWidget):
                continue
            for j in range(tab_widget.topLevelItemCount()):
                item = tab_widget.topLevelItem(j)
                model_row = item.data(0, Qt.ItemDataRole.UserRole)
                if self._verdict_level(model_row) == "no":
                    item.setHidden(hide_incompatible)
                else:
                    item.setHidden(False)

    # === Проверка занятости ресурса ===

    def _is_resource_busy(self) -> bool:
        return (self.resource_manager is not None and
                self.resource_manager.is_resource_busy())

    def _make_msg_box(self, icon, title, text,
                      buttons=QMessageBox.StandardButton.Ok) -> QMessageBox:
        """Явный QMessageBox с DontUseNativeDialog — фикс краша в деструкторе на KDE."""
        box = QMessageBox(self)
        box.setOption(QMessageBox.Option.DontUseNativeDialog)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        return box

    def _show_busy_warning(self):
        self._make_msg_box(
            QMessageBox.Icon.Warning,
            "Ресурс занят",
            "Сейчас идёт генерация в другом модуле.\n\n"
            "Остановите генерацию, чтобы управлять моделями."
        ).exec()

    # === Добавление модели ===

    def _on_add_model(self):
        dlg = AddModelDialog(self.config, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                self._refresh_tabs()
                self._status_label.setText(f"Модель добавлена: {result.get('model_id', '')}")

    # === Скачивание ===

    def _download_model(self, section: str, model_row: dict):
        if self._is_downloading:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        self._is_downloading = True
        self._downloading_section = section
        self._downloading_source = model_row.get("source", "")
        self._set_downloading_ui(section, model_row.get("source", ""))

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Начинаем скачивание {model_row['name']}...")

        size_gb = model_row.get("size_gb", 2.0) or 2.0
        if section == "ollama":
            self._current_downloader = OllamaDownloader(self.config, model_row["source"])
            self._current_downloader.set_model_size(size_gb)
        elif section == "diffusers":
            self._current_downloader = DiffusersDownloader(self.config, model_row["name"])
            self._current_downloader.set_repo_id(model_row["source"])
            self._current_downloader.set_model_size(size_gb)

        self._current_downloader.progress_updated.connect(self._on_progress)
        self._current_downloader.download_finished.connect(self._on_download_finished)
        self._current_downloader.error_occurred.connect(self._on_download_error)
        self._current_downloader.start()

    def _set_downloading_ui(self, section: str, source: str):
        """Все кнопки блокируются, кроме «Отменить» у загружаемой модели."""
        current_key = (section, source)
        for key, btns in self._row_buttons.items():
            state_btn = btns["state_btn"]
            info_btn = btns["info_btn"]
            if key == current_key:
                try:
                    state_btn.clicked.disconnect()
                except TypeError:
                    pass
                state_btn.setText("Отменить")
                state_btn.setToolTip("Отменить скачивание")
                state_btn.clicked.connect(self._cancel_download)
                state_btn.setEnabled(True)
                info_btn.setEnabled(False)
            else:
                state_btn.setEnabled(False)
                info_btn.setEnabled(False)

    def _on_progress(self, percent: int, message: str):
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_download_finished(self, success: bool, message: str):
        self._is_downloading = False
        self._current_downloader = None
        self._progress_bar.setValue(100 if success else 0)
        self._refresh_tabs()
        if success:
            self._status_label.setText(f"✓ {message}")
            # Автопроверка целостности (хэши) после успешной загрузки
            self._auto_deep_check_after_download()
        else:
            self._status_label.setText(f"✗ {message}")
            QTimer.singleShot(3000, lambda: self._progress_bar.setVisible(False))

    def _on_download_error(self, error_msg: str):
        self._status_label.setText(f"✗ {error_msg}")

    def _cancel_download(self):
        if self._current_downloader:
            self._status_label.setText("Отмена скачивания...")
            self._current_downloader.cancel()

    # === Установка с диска ===

    def _install_model(self, section: str, model_row: dict):
        """Установка: перемещение в папку моделей (Diffusers) или
        создание в Ollama из GGUF."""
        if self._is_downloading or self._is_verifying or self._is_installing:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        model_id = model_row.get("model_id")
        if not model_id:
            self._make_msg_box(QMessageBox.Icon.Warning, "Установка",
                               "Модель не зарегистрирована в реестре.").exec()
            return

        if section == "ollama":
            gguf_path = model_row.get("path", "")
            if not gguf_path or not os.path.isfile(gguf_path):
                self._make_msg_box(QMessageBox.Icon.Warning, "Установка",
                                   "GGUF-файл не найден.").exec()
                return
            name = derive_ollama_name_from_gguf(gguf_path)
            box = self._make_msg_box(
                QMessageBox.Icon.Question, "Установка в Ollama",
                f"Создать модель в Ollama как:\n\n<b>{name}:latest</b>\n\n"
                f"из файла:\n{gguf_path}\n\n"
                "Файл будет импортирован в хранилище Ollama.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            self._start_ollama_install(model_id, f"{name}:latest")
        else:
            src = model_row.get("path", "")
            if not src or not os.path.exists(src):
                self._make_msg_box(QMessageBox.Icon.Warning, "Установка",
                                   "Путь к модели не найден.").exec()
                return
            pm = PathsManager()
            models_dir = pm.get_path(self.config, "sdxl_models")
            box = self._make_msg_box(
                QMessageBox.Icon.Question, "Установка модели",
                f"Переместить модель в папку моделей:\n\n"
                f"Откуда: {src}\n"
                f"Куда: {models_dir}\n\n"
                "После перемещения модель пройдёт полную проверку хэшей.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            self._start_diffusers_install(model_id)

    def _start_diffusers_install(self, model_id: str):
        self._is_installing = True
        self._installing_model_id = model_id
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText("Установка модели (перемещение)...")
        self._block_all_buttons()
        self._current_installer = DiffusersInstallWorker(self.config, model_id, parent=self)
        self._current_installer.progress_updated.connect(self._on_install_progress)
        self._current_installer.install_finished.connect(self._on_install_finished)
        self._current_installer.start()

    def _start_ollama_install(self, model_id: str, model_name: str):
        self._is_installing = True
        self._installing_model_id = model_id
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Создание модели {model_name} в Ollama...")
        self._block_all_buttons()
        self._current_installer = OllamaInstallWorker(self.config, model_id, model_name, parent=self)
        self._current_installer.progress_updated.connect(self._on_install_progress)
        self._current_installer.install_finished.connect(self._on_install_finished)
        self._current_installer.start()

    def _block_all_buttons(self):
        for btns in self._row_buttons.values():
            btns["state_btn"].setEnabled(False)
            btns["info_btn"].setEnabled(False)

    def _on_install_progress(self, percent: int, message: str):
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _on_install_finished(self, success: bool, message: str, needs_deep_check: bool):
        self._is_installing = False
        self._current_installer = None
        model_id = self._installing_model_id
        self._installing_model_id = None

        self._refresh_tabs()

        if success:
            self._status_label.setText(f"✓ {message}")
            if needs_deep_check:
                # Модель с диска не была проверена по хэшам — проверяем теперь
                self._deep_check_by_model_id(model_id)
            else:
                QTimer.singleShot(3000, lambda: self._progress_bar.setVisible(False))
                self._make_msg_box(QMessageBox.Icon.Information, "Установка", message).exec()
        else:
            self._progress_bar.setVisible(False)
            self._make_msg_box(QMessageBox.Icon.Critical, "Ошибка установки", message).exec()

    def _deep_check_by_model_id(self, model_id: str):
        """Глубокая проверка модели по model_id (после установки)."""
        reg = next((m for m in self._registry_models if m["model_id"] == model_id), None)
        if not reg:
            self._progress_bar.setVisible(False)
            return
        section = reg["type"]
        if section == "ollama":
            target = reg["source"].get("ref", "")
        else:
            target = reg["paths"].get("installed", "")
            if not target or not os.path.exists(target):
                self._progress_bar.setVisible(False)
                return
        self._start_deep_validation(section, model_id, target)

    # === Удаление ===

    def _delete_model(self, section: str, model_row: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        name = model_row["name"]
        source = model_row.get("source", "")
        what = ("Файлы модели будут удалены с диска." if section == "diffusers"
                else "Модель будет удалена из Ollama.")

        box = self._make_msg_box(
            QMessageBox.Icon.Question,
            "Подтверждение удаления",
            f"Удалить модель:\n\n<b>{name}</b>\n({source})\n\n{what}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        if section == "ollama":
            result = delete_ollama_model(source, self.config)
        else:
            result = delete_diffusers_model(source, self.config)

        if result["success"]:
            self._make_msg_box(QMessageBox.Icon.Information, "Готово",
                               result["message"]).exec()
        else:
            self._make_msg_box(QMessageBox.Icon.Critical, "Ошибка",
                               f"Не удалось удалить:\n{result['message']}").exec()
            return

        self._refresh_tabs()

    # === Полная (хэш) проверка ===

    def _deep_validate_model(self, section: str, model_row: dict):
        """Явная полная проверка по кнопке «Полная»."""
        if self._is_downloading or self._is_verifying:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        model_id = model_row.get("model_id")
        if not model_id:
            self._make_msg_box(
                QMessageBox.Icon.Warning, "Проверка",
                "Модель не зарегистрирована в реестре.\n"
                "Добавьте её через «+ Добавить».").exec()
            return

        if section == "ollama":
            target = model_row.get("source", "")
        else:
            target = model_row.get("path", "")
            if not target or not os.path.exists(target):
                self._make_msg_box(QMessageBox.Icon.Warning, "Проверка",
                                   "Путь к модели не найден").exec()
                return

        self._start_deep_validation(section, model_id, target)

    def _auto_deep_check_after_download(self):
        """Автопроверка хэшей после успешного скачивания."""
        section = self._downloading_section
        source = self._downloading_source
        if not section or not source:
            return

        reg = self._find_in_registry(section, source)
        if not reg:
            self._status_label.setText(
                "✓ Загружено. Модель не найдена в реестре — проверьте вручную.")
            return

        model_id = reg["model_id"]
        if section == "ollama":
            target = source
        else:
            target = reg["paths"].get("installed", "")
            if not target or not os.path.exists(target):
                self._status_label.setText(
                    "✓ Загружено. Путь не найден — проверьте вручную.")
                return

        self._start_deep_validation(section, model_id, target)

    def _start_deep_validation(self, section: str, model_id: str, target: str):
        """Запускает фоновую глубокую проверку (хэши)."""
        if self._is_verifying or self._is_downloading:
            return

        self._is_verifying = True
        self._verifying_model_id = model_id
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText("Полная проверка: сверка хэшей...")

        # Блокируем все кнопки на время проверки
        for btns in self._row_buttons.values():
            btns["state_btn"].setEnabled(False)
            btns["info_btn"].setEnabled(False)

        self._current_verifier = DeepValidationWorker(
            section, target, self.config, parent=self)
        self._current_verifier.progress_updated.connect(self._on_verify_progress)
        self._current_verifier.verification_finished.connect(self._on_verify_finished)
        self._current_verifier.start()

    def _on_verify_progress(self, current: int, total: int, message: str):
        if total > 0:
            self._progress_bar.setValue(int(current * 100 / total))
        self._status_label.setText(message)

    def _on_verify_finished(self, valid: bool, errors: list, warnings: list,
                            cancelled: bool):
        self._is_verifying = False
        self._current_verifier = None
        model_id = self._verifying_model_id
        self._verifying_model_id = None

        if cancelled:
            self._status_label.setText("Проверка отменена")
        else:
            # Записываем результат в реестр (глубокая авторитетнее быстрой)
            update_model_validation(self.config, model_id, "deep", valid, errors)
            if valid:
                self._status_label.setText(
                    "✓ Полная проверка пройдена: хэши совпадают")
            else:
                self._status_label.setText(
                    "✗ Полная проверка провалена: модель повреждена")

        self._refresh_tabs()
        QTimer.singleShot(5000, lambda: self._progress_bar.setVisible(False))

        if not cancelled:
            if valid:
                self._make_msg_box(
                    QMessageBox.Icon.Information, "Полная проверка",
                    "✅ Модель цела: все хэши совпадают.").exec()
            else:
                err_text = "\n".join(errors[:5])
                self._make_msg_box(
                    QMessageBox.Icon.Critical, "Полная проверка",
                    f"Модель повреждена.\n\n{err_text}\n\n"
                    "Рекомендуется перекачать модель.").exec()

    # === Вердикт для неустановленной модели ===

    def _show_verdict(self, model_row: dict):
        verdict = self._verdict_level(model_row)
        name = model_row["name"]
        min_ram = model_row.get("min_ram_gb", 0)
        total = self._total_ram_gb

        if verdict == "ok":
            icon = QMessageBox.Icon.Information
            title = "Вердикт: потянет"
            msg = (f"✅ Модель {name} должна запуститься.\n\n"
                   f"Мин. ОЗУ: {min_ram} ГБ\nУ вас установлено: {total:.1f} ГБ")
        elif verdict == "warn":
            icon = QMessageBox.Icon.Warning
            title = "Вердикт: впритык"
            msg = (f"⚠ Модель {name} запустится впритык.\n\n"
                   f"Мин. ОЗУ: {min_ram} ГБ\nУ вас установлено: {total:.1f} ГБ.\n"
                   f"Совет: закройте другие приложения перед запуском.")
        else:
            icon = QMessageBox.Icon.Critical
            title = "Вердикт: не потянет"
            msg = (f"❌ Модель {name} не запустится.\n\n"
                   f"Мин. ОЗУ: {min_ram} ГБ\nУ вас установлено: {total:.1f} ГБ.")

        self._make_msg_box(icon, title, msg).exec()

    # === Обновление ===

    def _refresh_tabs(self):
        """Перечитывает данные и перестраивает вкладки."""
        current_index = self._tabs.currentIndex()
        self._load_data()
        self._populate_tabs()
        if 0 <= current_index < self._tabs.count():
            self._tabs.setCurrentIndex(current_index)

    def closeEvent(self, event):
        if self._is_installing:
            # Перемещение файлов нельзя прерывать без риска оставить огрызок
            self._status_label.setText("Идёт установка модели — дождитесь завершения")
            event.ignore()
            return
        if self._is_downloading and self._current_downloader:
            self._current_downloader.cancel()
        if self._is_verifying and self._current_verifier:
            # Отмена срабатывает на следующем чанке (8 МБ) — ожидание короткое
            self._current_verifier.cancel()
            self._current_verifier.wait(5000)
        event.accept()
