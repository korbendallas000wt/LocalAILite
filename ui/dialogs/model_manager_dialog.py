"""
Менеджер моделей (ui/dialogs/model_manager_dialog.py).

Единая точка входа для управления моделями:
- Просмотр доступных (список с вердиктами по железу)
- Скачивание с прогрессом и отменой (одна загрузка за раз)
- Удаление установленных (Ollama через 'ollama rm', Diffusers — папка + реестр)
- Проверка целостности установленных моделей

Трёхуровневые вердикты по УСТАНОВЛЕННОЙ RAM (стабильно, не зависит от кэша):
- ✅ Потянет  (min_ram <= 0.90 * total)
- ⚠ Впритык   (0.90 * total < min_ram <= 1.05 * total) — приглушён + совет
- ❌ Не потянет (min_ram > 1.05 * total) — скрывается галочкой «Только совместимые»

Структура диалога (3 блока в QGroupBox, ничего не прыгает):
1. Список моделей — вкладки с QTreeWidget (колонки пропорциональны ширине окна)
2. Статус загрузки — две строки: [статусбар + чекбокс] / [прогрессбар во всю ширину]
3. Информация о модели — метаданные + описание (две колонки, без прокрутки)

Кнопки в колонке «Действие» (одинаковый размер):
- Левая: 🔍 Проверить (установлена) / ❔ Вердикт (не установлена)
- Правая (3 состояния): ⬇ Загрузить → ✕ Отменить (во время загрузки) → 🗑 Удалить
"""

import psutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                              QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
                              QProgressBar, QCheckBox, QGroupBox, QHeaderView,
                              QMessageBox, QWidget, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor, QBrush
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

# Единый размер кнопок действий (не прыгают при смене состояния)
BTN_WIDTH = 90
BTN_HEIGHT = 22

# Пропорции колонок 0-4 (в сумме 0.70). Колонка 5 «Действие» получает остаток (~0.30),
# чтобы кнопки влезли и не было горизонтального скролла.
COLUMN_PERCENTS = [0.03, 0.27, 0.11, 0.13, 0.15]

# Разделители строк таблицы (+ вертикальный паддинг, чтобы кнопки влезали по высоте)
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
        self.resize(780, 560)
        self.setMinimumSize(720, 480)

        # Состояние
        self._current_downloader = None
        self._is_downloading = False
        # Кнопки строк: {(section, source): {"state_btn": ..., "info_btn": ...}}
        self._row_buttons = {}

        # RAM для вердиктов — УСТАНОВЛЕННАЯ (стабильная, не прыгает)
        vm = psutil.virtual_memory()
        self._total_ram_gb = vm.total / (1024**3)

        # Доступные модели
        self._available = list_available_models(config)

        # Установленные модели
        self._installed_ollama = list_installed_ollama_models(config)
        self._installed_diffusers_registry = load_registry(config)

        # UI
        self._setup_ui()
        self._populate_tabs()

    # === Вердикты (по установленной RAM) ===

    def _verdict_level(self, model_info: dict) -> str:
        """Возвращает 'ok', 'warn' или 'no' на основе min_ram_gb и УСТАНОВЛЕННОЙ RAM."""
        min_ram = model_info.get("min_ram_gb", 0)
        if min_ram <= 0:
            return "ok"
        total = self._total_ram_gb
        if min_ram <= 0.90 * total:
            return "ok"
        elif min_ram <= 1.05 * total:
            return "warn"
        else:
            return "no"

    # === UI ===

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # === Блок 1: Список моделей (вкладки) ===
        table_group = QGroupBox("Список моделей")
        table_layout = QVBoxLayout(table_group)
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        table_layout.addWidget(self._tabs)
        layout.addWidget(table_group, 1)

        # === Блок 2: Статус загрузки (две строки) ===
        status_group = QGroupBox("Статус загрузки")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(6)

        # Строка 1: статусбар (растягивается) + чекбокс (фикс. ширина справа)
        status_row = QHBoxLayout()
        self._status_label = QLabel("Готов к работе")
        status_row.addWidget(self._status_label, 1)
        self._compat_checkbox = QCheckBox("Только совместимые")
        self._compat_checkbox.setFixedWidth(180)
        self._compat_checkbox.stateChanged.connect(self._on_compat_filter_changed)
        status_row.addWidget(self._compat_checkbox)
        status_layout.addLayout(status_row)

        # Строка 2: прогрессбар во всю ширину
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        status_layout.addWidget(self._progress_bar)

        layout.addWidget(status_group)

        # === Блок 3: Информация о модели (две колонки, без прокрутки) ===
        info_group = QGroupBox("Информация о модели")
        info_group.setFixedHeight(110)
        info_layout = QHBoxLayout(info_group)

        self._meta_label = QLabel("Выберите модель")
        self._meta_label.setFixedWidth(220)
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._meta_label)

        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._desc_label, 1)

        layout.addWidget(info_group)

    def _create_tree_widget(self) -> QTreeWidget:
        """Создаёт таблицу. Ширины колонок пропорциональны (задаются в _apply_column_widths)."""
        tree = QTreeWidget()
        tree.setColumnCount(6)
        tree.setHeaderLabels(["№", "Имя", "Размер", "Мин. ОЗУ", "Статус", "Действие"])

        header = tree.header()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # Интерактивный режим: ширины задаём вручную пропорционально, без скролла
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        # Строка при клике не выделяется (детали обновляются через itemClicked)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tree.setStyleSheet(TREE_STYLE)
        tree.itemClicked.connect(self._on_item_clicked)
        return tree

    def _apply_column_widths(self, tree: QTreeWidget):
        """Пропорциональные ширины колонок; «Действие» получает остаток (точно влезает)."""
        # Запас 22px: резерв под вертикальный скроллбар + люфт,
        # чтобы его появление не вызывало горизонтальный скролл
        viewport_w = tree.viewport().width() - 22
        if viewport_w <= 10:
            return
        used = 0
        for col, pct in enumerate(COLUMN_PERCENTS):
            w = int(viewport_w * pct)
            tree.setColumnWidth(col, w)
            used += w
        # Остаток — под кнопки, но не меньше двух кнопок
        action_w = max(viewport_w - used, BTN_WIDTH * 2 + 24)
        tree.setColumnWidth(5, action_w)

    def _apply_all_column_widths(self):
        for i in range(self._tabs.count()):
            tree = self._tabs.widget(i)
            if isinstance(tree, QTreeWidget):
                self._apply_column_widths(tree)

    def resizeEvent(self, event):
        """При изменении размера окна пересчитываем пропорции колонок (без скролла)."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._apply_all_column_widths)

    def _populate_tabs(self):
        """Заполняет вкладки моделями с кнопками действий."""
        self._row_buttons = {}
        for section_name, models in self._available.items():
            # Фильтр по features/* (diffusers → sdxl)
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue

            tab_widget = self._create_tree_widget()
            row_num = 0
            for model_info in models:
                if section_name == "diffusers":
                    if model_info.get("packaging") != "hf_cache":
                        continue

                row_num += 1
                is_installed = self._is_installed(section_name, model_info)
                verdict = self._verdict_level(model_info)

                name = model_info["name"]
                size_gb = model_info.get("size_gb", 0)
                min_ram = model_info.get("min_ram_gb", 0)
                status_text = "✓ Установлена" if is_installed else "Не установлена"

                item = QTreeWidgetItem([
                    str(row_num),
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

                # Центрируем служебные колонки (№, Размер, ОЗУ, Статус)
                for col in (0, 2, 3, 4):
                    item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)

                # Приглушаем ⚠ (но не скрываем)
                if verdict == "warn":
                    dim_color = self.palette().color(QPalette.ColorRole.WindowText)
                    dim_color.setAlpha(120)
                    for col in range(6):
                        item.setForeground(col, QBrush(QColor(dim_color)))

                tab_widget.addTopLevelItem(item)

                # Виджет с кнопками действий (2 кнопки одинакового размера)
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(4, 2, 4, 2)
                action_layout.setSpacing(6)

                info_btn = QPushButton()
                info_btn.setFixedSize(BTN_WIDTH, BTN_HEIGHT)
                state_btn = QPushButton()
                state_btn.setFixedSize(BTN_WIDTH, BTN_HEIGHT)

                if is_installed:
                    info_btn.setText("🔍 Проверить")
                    info_btn.setToolTip("Проверить целостность модели")
                    info_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._validate_model(s, m))
                    state_btn.setText("🗑 Удалить")
                    state_btn.setToolTip("Удалить модель")
                    state_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._delete_model(s, m))
                else:
                    info_btn.setText("❔ Вердикт")
                    info_btn.setToolTip("Вердикт по железу (ОЗУ)")
                    info_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._show_verdict(s, m))
                    state_btn.setText("⬇ Загрузить")
                    state_btn.setToolTip("Скачать модель")
                    state_btn.clicked.connect(
                        lambda checked, m=model_info, s=section_name: self._download_model(s, m))

                action_layout.addWidget(info_btn)
                action_layout.addWidget(state_btn)
                tab_widget.setItemWidget(item, 5, action_widget)

                key = (section_name, model_info.get("source", name))
                self._row_buttons[key] = {"state_btn": state_btn, "info_btn": info_btn}

            self._tabs.addTab(tab_widget, section_name.capitalize())

        # Применяем фильтр сразу
        self._on_compat_filter_changed(self._compat_checkbox.checkState())
        # Пропорции колонок — после того, как вкладки получили размер
        QTimer.singleShot(0, self._apply_all_column_widths)

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

    # === Панель деталей (две колонки: метаданные + описание) ===

    def _on_item_clicked(self, item, column):
        """Клик по строке обновляет детали (без выделения строки)."""
        self._update_details(item)

    def _update_details(self, item):
        """Только метаданные + описание. Без вердиктов и без «у вас установлено»."""
        model_info = item.data(0, Qt.ItemDataRole.UserRole)

        name = model_info["name"]
        source = model_info.get("source", "")
        size_gb = model_info.get("size_gb", 0)
        min_ram = model_info.get("min_ram_gb", 0)
        tag = model_info.get("tag", "")
        description = model_info.get("description", "")

        meta = f"<b>{name}</b><br>"
        meta += f"Тег: {tag}<br>"
        meta += f"Размер: {size_gb:.1f} GB<br>"
        meta += f"Мин. ОЗУ: {min_ram} GB<br>"
        meta += f"Источник: {source}"

        self._meta_label.setText(meta)
        self._desc_label.setText(description)

    def _on_tab_changed(self, index):
        """Фикс бага: при переключении вкладки инфо-поле сбрасывается."""
        self._meta_label.setText("Выберите модель")
        self._desc_label.setText("")

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

    # === Скачивание ===

    def _download_model(self, section: str, model_info: dict):
        if self._is_downloading:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        self._is_downloading = True
        self._set_downloading_ui(section, model_info.get("source", ""))

        self._progress_bar.setValue(0)
        self._status_label.setText(f"Начинаем скачивание {model_info['name']}...")

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
                state_btn.setText("✕ Отменить")
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
        self._status_label.setText(f"✓ {message}" if success else f"✗ {message}")

    def _on_download_error(self, error_msg: str):
        self._status_label.setText(f"✗ {error_msg}")

    def _cancel_download(self):
        if self._current_downloader:
            self._status_label.setText("Отмена скачивания...")
            self._current_downloader.cancel()

    # === Удаление ===

    def _delete_model(self, section: str, model_info: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        name = model_info["name"]
        source = model_info.get("source", "")
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

    # === Проверка валидности ===

    def _validate_model(self, section: str, model_info: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        name = model_info["name"]
        source = model_info.get("source", "")

        self._status_label.setText(f"Проверка {name}...")
        result = validate_installed_model(source, section, self.config)

        if not result["success"]:
            icon = QMessageBox.Icon.Warning
            title = "Проверка не удалась"
            msg = f"Модель: {name}\n\nОшибки:\n" + "\n".join(result["errors"])
        elif result["valid"]:
            icon = QMessageBox.Icon.Information
            title = "Проверка целостности"
            msg = f"✅ Модель {name} цела и валидна"
            if result["warnings"]:
                msg += "\n\nПредупреждения:\n" + "\n".join(result["warnings"])
        else:
            icon = QMessageBox.Icon.Critical
            title = "Модель повреждена"
            msg = f"Модель: {name}\n\nОшибки:\n" + "\n".join(result["errors"])

        self._make_msg_box(icon, title, msg).exec()
        self._status_label.setText("Готово к работе")

    # === Вердикт для неустановленной модели ===

    def _show_verdict(self, section: str, model_info: dict):
        verdict = self._verdict_level(model_info)
        name = model_info["name"]
        min_ram = model_info.get("min_ram_gb", 0)
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

    # === Утилиты ===

    def _refresh_tabs(self):
        """Перечитывает установленные модели и перестраивает вкладки."""
        self._installed_ollama = list_installed_ollama_models(self.config)
        self._installed_diffusers_registry = load_registry(self.config)
        current_index = self._tabs.currentIndex()
        self._tabs.clear()
        self._populate_tabs()
        if 0 <= current_index < self._tabs.count():
            self._tabs.setCurrentIndex(current_index)

    def closeEvent(self, event):
        """Отменяет загрузку при закрытии диалога."""
        if self._is_downloading and self._current_downloader:
            self._current_downloader.cancel()
        event.accept()
