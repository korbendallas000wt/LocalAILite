"""
Менеджер моделей v4 (ui/dialogs/model_manager_dialog.py).

Структура:
- 3 вкладки: Реестр / Добавить / Найти
- Статус-полоса внизу (статусбар + прогрессбар) — видна с любой вкладки

Вкладка «Реестр» (модель «выбрал модель → всё для неё в панели»):
- Единая таблица (без под-вкладок), колонка «Тип», сортировка кликом
- Фильтры: тип (комбобокс) + «Только совместимые» (чекбокс)
- Одна кнопка действия в строке (Загрузить/Удалить/Установить/Перекачать)
- Панель информации: 3 блока с рамками (Данные / Описание / Проверка)
- Колонка «Железо» в таблице (цветной вердикт, сортируемая)
- Блок «Проверка»: чек-лист быстрой проверки +
  кнопка «Хэш-проверка» (глубокая, на выбранной модели)
- Имя модели — в блоке «Описание» (подкрашено), путь в одну строку
- На время хэширования таблица гаснет, в статусбаре имя модели

Контракт сохранён: __init__(config, resource_manager, parent)
"""

import psutil
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                              QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
                              QProgressBar, QCheckBox, QComboBox, QHeaderView,
                              QMessageBox, QWidget, QAbstractItemView, QGroupBox,
                              QLineEdit, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QBrush, QPalette, QFont, QDesktopServices
from utils.config import Config
from core.models_registry import (list_available_models, list_installed_ollama_models,
                                   list_all_models, update_model_validation,
                                   add_model_by_ref, register_from_path)
from core.model_verifier import DeepValidationWorker
from core.model_installer import (DiffusersInstallWorker, OllamaInstallWorker,
                                   derive_ollama_name_from_gguf)
from core.model_downloader import OllamaDownloader, DiffusersDownloader
from core.model_lifecycle import delete_ollama_model, delete_diffusers_model
from core.model_validator import validate_model_fast_detailed, validate_ollama_model_detailed
from core.paths_manager import PathsManager


# Маппинг типов моделей → флаги features/*
SECTION_TO_FEATURE = {
    "ollama": "ollama",
    "diffusers": "sdxl",
}

# Статусы: цвет (RGB) и подпись
STATUS_COLORS = {
    "download":   (150, 150, 150),
    "downloaded": (70, 130, 220),
    "valid":      (60, 170, 80),
    "installed":  (30, 130, 60),
    "invalid":    (220, 70, 70),
}
STATUS_LABELS = {
    "download":   "Скачать",
    "downloaded": "Закачана",
    "valid":      "Валидна",
    "installed":  "Установлена",
    "invalid":    "Невалидна",
}

# Вердикт по железу: цвет и подпись
VERDICT_COLORS = {
    "ok":   "#3c9c3c",
    "warn": "#e09020",
    "no":   "#d9534f",
}
VERDICT_LABELS = {
    "ok":   "Потянет",
    "warn": "Впритык",
    "no":   "Не потянет",
}

# Единый размер кнопок действий
BTN_WIDTH = 92
BTN_HEIGHT = 22

# Пропорции колонок 0-5 (Имя, Тип, Размер, Мин.ОЗУ, Статус, Железо).
# Колонка 6 «Действие» — остаток.
COLUMN_PERCENTS = [0.26, 0.09, 0.09, 0.10, 0.13, 0.12]

TREE_STYLE = (
    "QTreeWidget::item {"
    "  border-bottom: 1px solid rgba(128, 128, 128, 60);"
    "  padding: 3px 2px;"
    "}"
)

# Каталог ресурсов для вкладки «Найти» (база в коде, model_sources.json — дополнения)
RESOURCES = {
    "diffusers": [
        {"label": "🌐 HuggingFace — хаб Diffusers",
         "url": "https://huggingface.co/models?pipeline_tag=text-to-image&sort=downloads",
         "description": "Главный источник Diffusers-моделей. Ссылка репо (автор/модель) вставляется в «Добавить → По ссылке»."},
        {"label": "🎨 CivitAI — SDXL-модели сообщества",
         "url": "https://civitai.com/model-versions?baseModel=SDXL%201.0",
         "description": "Комьюнити-чекпоинты SDXL (.safetensors) и LoRA. Single-file модели — через «Добавить → С диска»."},
        {"label": "📦 SDXL Base 1.0 (stabilityai)",
         "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
         "description": "Базовая модель Stability: генерация 1024×1024, ~6.9 GB."},
        {"label": "📦 SDXL Refiner 1.0 (stabilityai)",
         "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0",
         "description": "Уточнитель: улучшает детали после базовой модели."},
    ],
    "ollama": [
        {"label": "📦 Ollama Library",
         "url": "https://ollama.com/library",
         "description": "Официальный каталог Ollama. Любая модель добавляется по имя:тег через «Добавить → По ссылке»."},
        {"label": "🤗 HuggingFace — GGUF-файлы",
         "url": "https://huggingface.co/models?library=gguf&sort=downloads",
         "description": "GGUF-файлы для Ollama: скачай файл, зарегистрируй через «Добавить → С диска», затем «Установить» в реестре."},
    ],
}


class SortableItem(QTreeWidgetItem):
    """Элемент таблицы с числовой сортировкой для колонок Размер/Мин.ОЗУ."""
    def __lt__(self, other):
        tree = self.treeWidget()
        col = tree.sortColumn() if tree else 0
        a = self.data(col, Qt.ItemDataRole.UserRole + 10)
        b = other.data(col, Qt.ItemDataRole.UserRole + 10)
        if a is not None and b is not None:
            return a < b
        return (self.text(col) or "") < (other.text(col) or "")


class ModelManagerDialog(QDialog):
    def __init__(self, config: Config, resource_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.resource_manager = resource_manager
        self.setWindowTitle("Менеджер моделей")
        self.resize(900, 660)
        self.setMinimumSize(800, 600)

        # RAM для вердиктов — УСТАНОВЛЕННАЯ (стабильная)
        vm = psutil.virtual_memory()
        self._total_ram_gb = vm.total / (1024**3)

        # Состояние загрузки
        self._current_downloader = None
        self._is_downloading = False
        self._row_buttons = {}
        self._downloading_section = None
        self._downloading_source = None
        self._downloading_name = None

        # Состояние глубокой проверки
        self._current_verifier = None
        self._is_verifying = False
        self._verifying_model_id = None
        self._verifying_name = None

        # Состояние установки
        self._current_installer = None
        self._is_installing = False
        self._installing_model_id = None

        # Выбранная модель
        self._selected_model_id = None

        # Загрузка данных (каталог + реестр v3.0 + обнаруженные)
        self._load_data()

        # UI
        self._setup_ui()
        self._populate_table()

    # === Загрузка данных ===

    def _load_data(self):
        self._available = list_available_models(self.config)
        self._registry_models = list_all_models(self.config)  # вызывает reconcile
        self._installed_ollama = list_installed_ollama_models(self.config)

    # === Вердикты по установленной RAM ===

    def _verdict_level(self, model_row: dict) -> str:
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

        # === Вкладки: Реестр / Добавить / Найти ===
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        # --- Вкладка 1: Реестр ---
        registry_tab = QWidget()
        registry_layout = QVBoxLayout(registry_tab)
        registry_layout.setContentsMargins(6, 6, 6, 6)
        registry_layout.setSpacing(8)

        # Тулбар фильтров
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Тип:"))
        self._type_filter_combo = QComboBox()
        self._type_filter_combo.addItem("Все", None)
        self._type_filter_combo.addItem("Ollama", "ollama")
        self._type_filter_combo.addItem("Diffusers", "diffusers")
        self._type_filter_combo.currentIndexChanged.connect(lambda *_: self._apply_filters())
        filter_bar.addWidget(self._type_filter_combo)

        self._compat_checkbox = QCheckBox("Только совместимые")
        self._compat_checkbox.stateChanged.connect(lambda *_: self._apply_filters())
        filter_bar.addWidget(self._compat_checkbox)

        filter_bar.addStretch()

        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.setToolTip("Перечитать реестр и пересканировать папку моделей")
        self._refresh_btn.clicked.connect(self._refresh_tabs)
        filter_bar.addWidget(self._refresh_btn)
        registry_layout.addLayout(filter_bar)

        # Таблица моделей
        list_group = QGroupBox("Список моделей")
        list_layout = QVBoxLayout(list_group)
        self._tree = self._create_tree_widget()
        list_layout.addWidget(self._tree)
        registry_layout.addWidget(list_group, 1)

        # Панель информации: 3 блока с рамками
        info_bar = QHBoxLayout()
        info_bar.setSpacing(8)

        # Блок 1: Данные
        data_group = QGroupBox("Данные")
        data_group.setFixedWidth(250)
        data_layout = QVBoxLayout(data_group)
        self._meta_label = QLabel("Выберите модель")
        self._meta_label.setWordWrap(True)
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        data_layout.addWidget(self._meta_label)
        info_bar.addWidget(data_group)

        # Блок 2: Описание (имя модели + описание)
        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        desc_layout.addWidget(self._desc_label)
        info_bar.addWidget(desc_group, 1)

        # Блок 3: Проверка (чек-лист + хэш-проверка; железо — колонка таблицы)
        check_group = QGroupBox("Проверка")
        check_group.setFixedWidth(260)
        check_layout = QVBoxLayout(check_group)
        check_layout.setSpacing(6)
        self._checklist_label = QLabel("")
        self._checklist_label.setWordWrap(True)
        self._checklist_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        check_layout.addWidget(self._checklist_label, 1)
        self._hash_btn = QPushButton("Хэш-проверка")
        self._hash_btn.setToolTip("Сверка хэшей всех файлов с эталонными (долго)")
        self._hash_btn.setEnabled(False)
        self._hash_btn.clicked.connect(self._on_hash_btn_clicked)
        check_layout.addWidget(self._hash_btn)
        info_bar.addWidget(check_group)

        # Обёртка панели с фиксированной высотой
        info_widget = QWidget()
        info_widget.setFixedHeight(185)
        info_widget.setLayout(info_bar)
        registry_layout.addWidget(info_widget)

        self._tabs.addTab(registry_tab, "Реестр")

        # --- Вкладка 2: Добавить ---
        self._tabs.addTab(self._build_add_tab(), "Добавить")

        # --- Вкладка 3: Найти ---
        self._tabs.addTab(self._build_find_tab(), "Найти")

        # === Статус-полоса внизу (вне вкладок) ===
        status_group = QGroupBox("Статус")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(6)
        self._status_label = QLabel("Готов к работе")
        status_layout.addWidget(self._status_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        status_layout.addWidget(self._progress_bar)
        layout.addWidget(status_group)

    def _create_tree_widget(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(7)
        tree.setHeaderLabels(["Имя", "Тип", "Размер", "Мин. ОЗУ", "Статус",
                              "Железо", "Действие"])

        header = tree.header()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setStyleSheet(TREE_STYLE)
        tree.setSortingEnabled(True)  # сортировка кликом по заголовку
        tree.currentItemChanged.connect(self._on_current_item_changed)
        return tree

    def _apply_column_widths(self):
        viewport_w = self._tree.viewport().width() - 22
        if viewport_w <= 10:
            return
        used = 0
        for col, pct in enumerate(COLUMN_PERCENTS):
            w = int(viewport_w * pct)
            self._tree.setColumnWidth(col, w)
            used += w
        action_w = max(viewport_w - used, BTN_WIDTH + 24)
        self._tree.setColumnWidth(6, action_w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._apply_column_widths)

    # === Построение единого списка моделей ===

    def _build_model_list(self) -> list:
        """Объединяет каталог + реестр v3.0 + обнаруженные (оба типа)."""
        models = []
        seen = set()

        # 1. Каталог (оба типа)
        for section_name, cat_models in self._available.items():
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue
            for cat_model in cat_models:
                if section_name == "diffusers" and cat_model.get("packaging") != "hf_cache":
                    continue
                source = cat_model["source"]
                key = (section_name, source)
                reg = self._find_in_registry(section_name, source)
                if reg:
                    status = reg["status"]
                    model_id = reg["model_id"]
                    path = reg["paths"].get("installed", "")
                elif section_name == "ollama" and source in self._installed_ollama:
                    status = "installed"
                    model_id = None
                    path = ""
                else:
                    status = "download"
                    model_id = None
                    path = ""
                models.append({
                    "name": cat_model["name"],
                    "type": section_name,
                    "size_gb": cat_model.get("size_gb", 0),
                    "min_ram_gb": cat_model.get("min_ram_gb", 0),
                    "description": cat_model.get("description", ""),
                    "source": source,
                    "status": status,
                    "model_id": model_id,
                    "path": path,
                    "origin": "catalog",
                })
                seen.add(key)

        # 2. Реестр: модели, которых нет в каталоге (оба типа)
        for reg_model in self._registry_models:
            section_name = reg_model["type"]
            feature = SECTION_TO_FEATURE.get(section_name, section_name)
            if not self.config.get_feature(feature, True):
                continue
            ref = reg_model["source"].get("ref", "")
            if not ref:
                continue
            key = (section_name, ref)
            if key in seen:
                continue
            seen.add(key)
            meta = reg_model.get("meta", {})
            models.append({
                "name": reg_model["display_name"],
                "type": section_name,
                "size_gb": meta.get("size_gb", 0),
                "min_ram_gb": meta.get("min_ram_gb", 0),
                "description": meta.get("description", ""),
                "source": ref,
                "status": reg_model["status"],
                "model_id": reg_model["model_id"],
                "path": reg_model["paths"].get("installed", ""),
                "origin": "registry",
            })

        # 3. Обнаруженные Ollama (fallback: в манифестах, но нет в реестре)
        if self.config.get_feature("ollama", True):
            for ollama_name in self._installed_ollama:
                key = ("ollama", ollama_name)
                if key in seen:
                    continue
                seen.add(key)
                models.append({
                    "name": ollama_name,
                    "type": "ollama",
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
        for reg_model in self._registry_models:
            if reg_model["type"] != section:
                continue
            if reg_model["source"].get("ref") == source:
                return reg_model
        return None

    # === Заполнение таблицы ===

    def _populate_table(self):
        selected_id = self._selected_model_id
        self._row_buttons = {}
        self._tree.setSortingEnabled(False)  # не сортировать при наполнении
        self._tree.clear()
        model_list = self._build_model_list()

        for model_row in model_list:
            status = model_row["status"]
            status_text = STATUS_LABELS.get(status, status)
            status_color = STATUS_COLORS.get(status, (150, 150, 150))
            size_gb = model_row["size_gb"]
            min_ram = model_row["min_ram_gb"]
            type_label = "Ollama" if model_row["type"] == "ollama" else "Diffusers"
            verdict = self._verdict_level(model_row)
            verdict_text = VERDICT_LABELS[verdict]
            verdict_color = QColor(VERDICT_COLORS[verdict])
            verdict_rank = {"ok": 0, "warn": 1, "no": 2}[verdict]

            item = SortableItem([
                model_row["name"],
                type_label,
                f"{size_gb:.1f} GB" if size_gb > 0 else "—",
                f"{min_ram} GB" if min_ram > 0 else "—",
                status_text,
                verdict_text,
                ""
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, model_row)
            # Числовые значения для сортировки (Размер, Мин. ОЗУ, Железо)
            item.setData(2, Qt.ItemDataRole.UserRole + 10, float(size_gb))
            item.setData(3, Qt.ItemDataRole.UserRole + 10, float(min_ram))
            item.setData(5, Qt.ItemDataRole.UserRole + 10, verdict_rank)

            for col in (1, 2, 3, 4, 5):
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
            item.setForeground(4, QBrush(QColor(*status_color)))
            item.setForeground(5, QBrush(verdict_color))

            # Приглушаем несовместимые (вердикт ❌), Статус и Железо не трогаем
            if verdict == "no":
                dim = QColor(150, 150, 150)
                for col in range(7):
                    if col not in (4, 5):
                        item.setForeground(col, QBrush(dim))

            self._tree.addTopLevelItem(item)
            self._create_action_button(item, model_row)

        self._tree.setSortingEnabled(True)
        self._apply_filters()

        # Восстановление выделения и панели
        if selected_id and self._select_model_by_id(selected_id):
            pass
        else:
            self._reset_details()

        QTimer.singleShot(0, self._apply_column_widths)

    def _create_action_button(self, item, model_row):
        """Одна кнопка действия в строке (зависит от статуса)."""
        status = model_row["status"]
        state_btn = QPushButton()
        state_btn.setFixedSize(BTN_WIDTH, BTN_HEIGHT)
        m = model_row

        if status == "download":
            state_btn.setText("Загрузить")
            state_btn.setToolTip("Скачать модель")
            state_btn.clicked.connect(lambda checked, m=m: self._download_model(m))
        elif status == "valid":
            state_btn.setText("Установить")
            state_btn.setToolTip("Переместить в папку моделей")
            state_btn.clicked.connect(lambda checked, m=m: self._install_model(m))
        elif status == "invalid":
            state_btn.setText("Перекачать")
            state_btn.setToolTip("Скачать заново")
            state_btn.clicked.connect(lambda checked, m=m: self._download_model(m))
        else:  # downloaded, installed
            state_btn.setText("Удалить")
            state_btn.setToolTip("Удалить модель")
            state_btn.clicked.connect(lambda checked, m=m: self._delete_model(m))

        # Кнопка по центру колонки «Действие»
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(2, 2, 2, 2)
        action_layout.addStretch()
        action_layout.addWidget(state_btn)
        action_layout.addStretch()
        self._tree.setItemWidget(item, 6, action_widget)

        key = (model_row["type"], model_row.get("source", model_row["name"]))
        self._row_buttons[key] = {"state_btn": state_btn}

    def _select_model_by_id(self, model_id: str) -> bool:
        """Находит строку по model_id, выделяет её и обновляет панель."""
        for j in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(j)
            row = item.data(0, Qt.ItemDataRole.UserRole)
            if row and row.get("model_id") == model_id:
                self._tree.setCurrentItem(item)
                self._update_details(row)
                return True
        return False

    def _get_selected_row(self) -> dict:
        item = self._tree.currentItem()
        if item:
            return item.data(0, Qt.ItemDataRole.UserRole)
        return None

    # === Вкладка «Добавить» ===

    def _build_add_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Группа: по ссылке
        link_group = QGroupBox("По ссылке")
        link_layout = QVBoxLayout(link_group)
        link_layout.addWidget(QLabel(
            "Для Ollama — имя:тег (например, <b>qwen2.5:14b</b>). "
            "Для Diffusers — репозиторий (например, "
            "<b>stabilityai/stable-diffusion-xl-base-1.0</b>). "
            "Модель появится в «Реестре» со статусом «Скачать»."))
        link_row = QHBoxLayout()
        link_row.addWidget(QLabel("Тип:"))
        self._link_type_combo = QComboBox()
        self._link_type_combo.addItems(["Ollama", "Diffusers"])
        link_row.addWidget(self._link_type_combo)
        self._link_edit = QLineEdit()
        self._link_edit.setPlaceholderText(
            "Ollama: qwen2.5:14b   /   Diffusers: автор/модель")
        self._link_edit.returnPressed.connect(self._add_by_link)
        link_row.addWidget(self._link_edit, 1)
        link_btn = QPushButton("Добавить")
        link_btn.clicked.connect(self._add_by_link)
        link_row.addWidget(link_btn)
        link_layout.addLayout(link_row)
        layout.addWidget(link_group)

        # Группа: с диска
        disk_group = QGroupBox("С диска")
        disk_layout = QVBoxLayout(disk_group)
        disk_layout.addWidget(QLabel(
            "Для Diffusers — папка <b>models--*</b> или распакованная папка "
            "(через «Обзор»), файл .safetensors/.ckpt (вписать путь вручную). "
            "Для Ollama — файл <b>.gguf</b>: после регистрации нажмите "
            "«Установить» в «Реестре»."))
        disk_row = QHBoxLayout()
        disk_row.addWidget(QLabel("Тип:"))
        self._disk_type_combo = QComboBox()
        self._disk_type_combo.addItems(["Diffusers", "Ollama"])
        disk_row.addWidget(self._disk_type_combo)
        self._disk_path_edit = QLineEdit()
        self._disk_path_edit.setPlaceholderText("Путь к модели или файлу")
        disk_row.addWidget(self._disk_path_edit, 1)
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self._browse_disk_path)
        disk_row.addWidget(browse_btn)
        disk_btn = QPushButton("Добавить")
        disk_btn.clicked.connect(self._add_from_disk)
        disk_row.addWidget(disk_btn)
        disk_layout.addLayout(disk_row)
        layout.addWidget(disk_group)

        layout.addStretch()
        return tab

    def _browse_disk_path(self):
        model_type = ("ollama"
                      if self._disk_type_combo.currentText() == "Ollama"
                      else "diffusers")
        if model_type == "ollama":
            path, _ = QFileDialog.getOpenFileName(
                self, "Выберите GGUF-файл", os.path.expanduser("~"),
                "GGUF-модели (*.gguf)")
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Выберите папку модели (models--* или распакованную)",
                os.path.expanduser("~"))
        if path:
            self._disk_path_edit.setText(path)

    def _add_by_link(self):
        ref = self._link_edit.text().strip()
        if not ref:
            self._make_msg_box(QMessageBox.Icon.Warning, "Добавление",
                               "Укажите ссылку (имя:тег или репозиторий).").exec()
            return
        model_type = ("ollama"
                      if self._link_type_combo.currentText() == "Ollama"
                      else "diffusers")
        if model_type == "diffusers" and "/" not in ref:
            self._make_msg_box(QMessageBox.Icon.Warning, "Добавление",
                               "Для Diffusers укажите репо в формате "
                               "«автор/модель».").exec()
            return
        if model_type == "ollama" and ":" not in ref:
            ref = ref + ":latest"
        model_id = add_model_by_ref(self.config, ref, model_type)
        if not model_id:
            self._make_msg_box(QMessageBox.Icon.Warning, "Добавление",
                               "Не удалось добавить модель.").exec()
            return
        self._link_edit.clear()
        self._status_label.setText(f"✓ Добавлено: {ref} — статус «Скачать»")
        self._goto_registry(model_id)

    def _add_from_disk(self):
        path = self._disk_path_edit.text().strip()
        if not path or not os.path.exists(path):
            self._make_msg_box(QMessageBox.Icon.Warning, "Добавление",
                               "Укажите существующий путь.").exec()
            return
        model_type = ("ollama"
                      if self._disk_type_combo.currentText() == "Ollama"
                      else "diffusers")
        model_id = register_from_path(path, model_type, self.config)
        if not model_id:
            self._make_msg_box(
                QMessageBox.Icon.Warning, "Добавление",
                "Не удалось зарегистрировать модель (неопознанный формат).\n"
                "Diffusers: папка models--*, распакованная папка с "
                "model_index.json или файл .safetensors/.ckpt.\n"
                "Ollama: файл .gguf.").exec()
            return
        self._disk_path_edit.clear()
        self._status_label.setText(
            f"✓ Зарегистрировано: {os.path.basename(path)}")
        self._goto_registry(model_id)

    def _goto_registry(self, model_id: str):
        """Переключает на «Реестр» и выделяет добавленную модель."""
        self._selected_model_id = model_id
        self._refresh_tabs()
        self._tabs.setCurrentIndex(0)

    # === Вкладка «Найти» ===

    def _build_find_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(QLabel(
            "Где искать модели. Двойной клик по ресурсу — открыть в браузере."))

        self._resources_tree = QTreeWidget()
        self._resources_tree.setColumnCount(2)
        self._resources_tree.setHeaderLabels(["Ресурс", "Описание"])
        self._resources_tree.setRootIsDecorated(True)
        self._resources_tree.setUniformRowHeights(False)
        self._resources_tree.setWordWrap(True)
        header = self._resources_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        bold = QFont()
        bold.setBold(True)
        resources = self._build_resources()
        for group_title, key in (("Diffusers / SDXL", "diffusers"),
                                 ("Ollama", "ollama")):
            group = QTreeWidgetItem([group_title, ""])
            group.setFont(0, bold)
            self._resources_tree.addTopLevelItem(group)
            for r in resources[key]:
                item = QTreeWidgetItem([r["label"], r["description"]])
                item.setData(0, Qt.ItemDataRole.UserRole, r["url"])
                group.addChild(item)
            group.setExpanded(True)

        self._resources_tree.itemDoubleClicked.connect(
            self._on_resource_double_clicked)
        layout.addWidget(self._resources_tree, 1)
        return tab

    def _build_resources(self) -> dict:
        """Ресурсы: базовый каталог (в коде) + дополнения из model_sources.json."""
        resources = {k: list(v) for k, v in RESOURCES.items()}
        seen_urls = {r["url"] for entries in resources.values() for r in entries}
        try:
            extra = PathsManager().get_model_sources()
        except Exception:
            extra = {}
        for section, key in (("sdxl", "diffusers"), ("ollama", "ollama")):
            for entry in extra.get(section, []):
                url = entry.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    resources[key].append({
                        "label": entry.get("label", url),
                        "url": url,
                        "description": entry.get("description", ""),
                    })
        return resources

    def _on_resource_double_clicked(self, item, column):
        url = item.data(0, Qt.ItemDataRole.UserRole)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # === Фильтры (тип + совместимость) ===

    def _apply_filters(self):
        type_filter = self._type_filter_combo.currentData()
        hide_incompatible = (self._compat_checkbox.checkState() == Qt.CheckState.Checked.value)
        for j in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(j)
            model_row = item.data(0, Qt.ItemDataRole.UserRole)
            hidden = False
            if type_filter and model_row["type"] != type_filter:
                hidden = True
            if hide_incompatible and self._verdict_level(model_row) == "no":
                hidden = True
            item.setHidden(hidden)

    # === Панель информации (3 блока) ===

    def _on_current_item_changed(self, item, previous):
        if item is None:
            return
        model_row = item.data(0, Qt.ItemDataRole.UserRole)
        if model_row:
            self._selected_model_id = model_row.get("model_id")
            self._update_details(model_row)

    def _reset_details(self):
        self._meta_label.setText("Выберите модель")
        self._meta_label.setToolTip("")
        self._desc_label.setText("")
        self._checklist_label.setText("")
        self._hash_btn.setEnabled(False)

    def _update_details(self, model_row: dict):
        # Блок 1: Данные (без имени — оно в «Описании»; путь в одну строку)
        name = model_row["name"]
        source = model_row.get("source", "")
        size_gb = model_row.get("size_gb", 0)
        min_ram = model_row.get("min_ram_gb", 0)
        path = model_row.get("path", "")

        meta = f"Размер: {size_gb:.1f} GB<br>" if size_gb > 0 else "Размер: —<br>"
        meta += f"Мин. ОЗУ: {min_ram} GB<br>" if min_ram > 0 else "Мин. ОЗУ: —<br>"
        meta += f"Источник: {source}"
        if path:
            meta += f"<br>Путь: {self._short_path(path)}"
        self._meta_label.setText(meta)
        self._meta_label.setToolTip(path or "")

        # Блок 2: Описание (имя модели + описание)
        accent = self.palette().color(QPalette.ColorRole.Link).name()
        desc_html = f'<b><span style="color:{accent};">{name}</span></b><br><br>'
        desc_html += model_row.get("description", "") or ""
        self._desc_label.setText(desc_html)

        # Блок 3: Проверка
        self._update_checklist(model_row)
        self._update_hash_btn(model_row)

    def _short_path(self, path: str, max_len: int = 38) -> str:
        """Сокращает путь до одной строки: начало…хвост (хвост важнее)."""
        if len(path) <= max_len:
            return path
        head_len = max_len // 3
        tail_len = max_len - head_len - 1
        return path[:head_len] + "…" + path[-tail_len:]

    def _update_checklist(self, model_row: dict):
        status = model_row["status"]
        section = model_row["type"]

        if status == "download":
            self._checklist_label.setText("<i>Модель не скачана</i>")
            return

        # Быстрая проверка с построчным результатом
        try:
            if section == "ollama":
                pm = PathsManager()
                ollama_path = pm.get_path(self.config, "ollama_models")
                valid, items = validate_ollama_model_detailed(
                    model_row.get("source", ""), ollama_path)
            else:
                path = model_row.get("path", "")
                if not path or not os.path.exists(path):
                    self._checklist_label.setText("<i>Путь не найден</i>")
                    return
                valid, items = validate_model_fast_detailed(path)
        except Exception as e:
            self._checklist_label.setText(f"<i>Ошибка проверки: {e}</i>")
            return

        lines = []
        for it in items:
            if it.passed:
                mark = '<span style="color:#3c9c3c;">✓</span>'
                lines.append(f"{mark} {it.name}")
            else:
                mark = '<span style="color:#d9534f;">✗</span>'
                det = f' <span style="color:gray;">— {it.details}</span>' if it.details else ""
                lines.append(f"{mark} {it.name}{det}")

        # Строка SHA256 — из реестра (если глубокая проверка уже была)
        lines.append(self._sha256_line(model_row))

        self._checklist_label.setText("<br>".join(lines))

    def _sha256_line(self, model_row: dict) -> str:
        model_id = model_row.get("model_id")
        if not model_id:
            return '<span style="color:gray;">— SHA256 (не проверялась)</span>'
        reg = next((m for m in self._registry_models
                    if m["model_id"] == model_id), None)
        if not reg:
            return '<span style="color:gray;">— SHA256 (не проверялась)</span>'
        validation = reg.get("validation", {})
        if validation.get("last_method") == "deep":
            if validation.get("last_result") == "valid":
                return '<span style="color:#3c9c3c;">✓ SHA256</span>'
            errors = validation.get("errors", [])
            det = f' <span style="color:gray;">— {errors[0]}</span>' if errors else ""
            return f'<span style="color:#d9534f;">✗ SHA256</span>{det}'
        return '<span style="color:gray;">— SHA256 (не проверялась)</span>'

    def _update_hash_btn(self, model_row: dict):
        if self._is_verifying or self._is_downloading:
            self._hash_btn.setEnabled(False)
            return
        status = model_row["status"]
        self._hash_btn.setEnabled(status in ("downloaded", "valid", "installed", "invalid"))

    def _on_hash_btn_clicked(self):
        row = self._get_selected_row()
        if row:
            self._deep_validate_model(row)

    # === Проверка занятости ресурса ===

    def _is_resource_busy(self) -> bool:
        return (self.resource_manager is not None and
                self.resource_manager.is_resource_busy())

    def _make_msg_box(self, icon, title, text,
                      buttons=QMessageBox.StandardButton.Ok) -> QMessageBox:
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

    def _download_model(self, model_row: dict):
        if self._is_downloading:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        section = model_row["type"]
        self._is_downloading = True
        self._downloading_section = section
        self._downloading_source = model_row.get("source", "")
        self._downloading_name = model_row["name"]
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
        current_key = (section, source)
        for key, btns in self._row_buttons.items():
            state_btn = btns["state_btn"]
            if key == current_key:
                try:
                    state_btn.clicked.disconnect()
                except TypeError:
                    pass
                state_btn.setText("Отменить")
                state_btn.setToolTip("Отменить скачивание")
                state_btn.clicked.connect(self._cancel_download)
                state_btn.setEnabled(True)
            else:
                state_btn.setEnabled(False)

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

    # === Полная (хэш) проверка ===

    def _deep_validate_model(self, model_row: dict):
        if self._is_downloading or self._is_verifying:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        section = model_row["type"]
        model_id = model_row.get("model_id")
        if not model_id:
            self._make_msg_box(QMessageBox.Icon.Warning, "Проверка",
                               "Модель не зарегистрирована в реестре.\n"
                               "Добавьте её через вкладку «Добавить».").exec()
            return

        if section == "ollama":
            target = model_row.get("source", "")
        else:
            target = model_row.get("path", "")
            if not target or not os.path.exists(target):
                self._make_msg_box(QMessageBox.Icon.Warning, "Проверка",
                                   "Путь к модели не найден").exec()
                return

        self._start_deep_validation(section, model_id, target, model_row["name"])

    def _auto_deep_check_after_download(self):
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
        name = self._downloading_name or reg.get("display_name", source)
        self._start_deep_validation(section, model_id, target, name)

    def _start_deep_validation(self, section: str, model_id: str, target: str,
                               model_name: str):
        if self._is_verifying or self._is_downloading:
            return
        self._is_verifying = True
        self._verifying_model_id = model_id
        self._verifying_name = model_name

        # Гасим таблицу и органы управления
        self._tree.setEnabled(False)
        self._hash_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._type_filter_combo.setEnabled(False)
        self._compat_checkbox.setEnabled(False)
        self._block_all_buttons()

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Хэш-проверка {model_name}...")

        self._current_verifier = DeepValidationWorker(
            section, target, self.config, parent=self)
        self._current_verifier.progress_updated.connect(self._on_verify_progress)
        self._current_verifier.verification_finished.connect(self._on_verify_finished)
        self._current_verifier.start()

    def _on_verify_progress(self, current: int, total: int, message: str):
        if total > 0:
            self._progress_bar.setValue(int(current * 100 / total))
        self._status_label.setText(
            f"Хэш-проверка {self._verifying_name}: {message}")

    def _on_verify_finished(self, valid: bool, errors: list, warnings: list,
                            cancelled: bool):
        self._is_verifying = False
        self._current_verifier = None
        model_id = self._verifying_model_id
        self._verifying_model_id = None

        # Восстанавливаем таблицу и органы управления
        self._tree.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        self._type_filter_combo.setEnabled(True)
        self._compat_checkbox.setEnabled(True)

        if cancelled:
            self._status_label.setText("Проверка отменена")
            QTimer.singleShot(3000, lambda: self._progress_bar.setVisible(False))
        else:
            # Записываем результат в реестр (глубокая авторитетнее быстрой)
            update_model_validation(self.config, model_id, "deep", valid, errors)
            self._progress_bar.setValue(100)
            if valid:
                self._status_label.setText(f"✓ {self._verifying_name}: хэши совпадают")
            else:
                self._status_label.setText(f"✗ {self._verifying_name}: модель повреждена")
            QTimer.singleShot(8000, lambda: self._progress_bar.setVisible(False))

        # Обновляем таблицу и панель (выделение восстановится)
        self._refresh_tabs()

    def _deep_check_by_model_id(self, model_id: str):
        """Глубокая проверка модели по model_id (после установки с копированием)."""
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
        self._start_deep_validation(section, model_id, target, reg.get("display_name", ""))

    def _block_all_buttons(self):
        for btns in self._row_buttons.values():
            btns["state_btn"].setEnabled(False)

    # === Установка с диска ===

    def _install_model(self, model_row: dict):
        if self._is_downloading or self._is_verifying or self._is_installing:
            return
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        section = model_row["type"]
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
        self._current_installer = OllamaInstallWorker(
            self.config, model_id, model_name, parent=self)
        self._current_installer.progress_updated.connect(self._on_install_progress)
        self._current_installer.install_finished.connect(self._on_install_finished)
        self._current_installer.start()

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
                # После копирования (разные ФС) — полная проверка хэшей
                self._deep_check_by_model_id(model_id)
            else:
                QTimer.singleShot(3000, lambda: self._progress_bar.setVisible(False))
        else:
            self._progress_bar.setVisible(False)
            self._make_msg_box(QMessageBox.Icon.Critical, "Ошибка установки", message).exec()

    # === Удаление ===

    def _delete_model(self, model_row: dict):
        if self._is_resource_busy():
            self._show_busy_warning()
            return

        section = model_row["type"]
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

        self._selected_model_id = None
        self._refresh_tabs()

    # === Обновление ===

    def _refresh_tabs(self):
        self._load_data()
        self._populate_table()

    def closeEvent(self, event):
        if self._is_installing:
            # Перемещение файлов нельзя прерывать без риска оставить огрызок
            self._status_label.setText("Идёт установка модели — дождитесь завершения")
            event.ignore()
            return
        if self._is_downloading and self._current_downloader:
            self._current_downloader.cancel()
        if self._is_verifying and self._current_verifier:
            self._current_verifier.cancel()
            self._current_verifier.wait(5000)
        event.accept()
