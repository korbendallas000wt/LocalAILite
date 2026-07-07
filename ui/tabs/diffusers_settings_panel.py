from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                             QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton,
                             QTextEdit, QHBoxLayout, QLabel, QCheckBox)
from PyQt6.QtCore import Qt
import random
import os
from core.checkpoint_manager import list_archived_checkpoints, load_archived_checkpoint


class DiffusersSettingsPanel(QWidget):
    """Панель настроек Diffusers с управлением чекпоинтами"""

    def __init__(self, config):
        super().__init__()
        self.config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # === Чекпоинты (в самом верху) ===
        checkpoint_row = QHBoxLayout()
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setSizePolicy(
            self.checkpoint_combo.sizePolicy().horizontalPolicy(),
            self.checkpoint_combo.sizePolicy().verticalPolicy()
        )
        checkpoint_row.addWidget(self.checkpoint_combo, 1)

        self.load_checkpoint_btn = QPushButton("📥")
        self.load_checkpoint_btn.setFixedWidth(40)
        self.load_checkpoint_btn.setToolTip("Загрузить выбранный чекпоинт")
        checkpoint_row.addWidget(self.load_checkpoint_btn)

        layout.addLayout(checkpoint_row)

        # === Основные настройки ===
        form = QFormLayout()
        form.setSpacing(8)

        # Model + кнопка обновления
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        model_row.addWidget(self.model_combo, 1)

        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedWidth(40)
        self.refresh_models_btn.setToolTip("Обновить список моделей")
        self.refresh_models_btn.clicked.connect(self._load_models)
        model_row.addWidget(self.refresh_models_btn)

        form.addRow("Model:", model_row)

        # Scheduler
        self.scheduler_combo = QComboBox()
        self.scheduler_combo.addItems([
            "EulerDiscreteScheduler",
            "EulerAncestralDiscreteScheduler",
            "DPMSolverMultistepScheduler",
            "DDIMScheduler",
            "PNDMScheduler"
        ])
        self.scheduler_combo.setCurrentText(self.config.get_sdxl_scheduler())
        form.addRow("Scheduler:", self.scheduler_combo)

        # Steps
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 150)
        self.steps_spin.setValue(self.config.get_sdxl_default_steps())
        form.addRow("Steps:", self.steps_spin)

        # CFG Scale
        self.cfg_spin = QDoubleSpinBox()
        self.cfg_spin.setRange(1.0, 30.0)
        self.cfg_spin.setValue(self.config.get_sdxl_default_cfg())
        self.cfg_spin.setSingleStep(0.5)
        self.cfg_spin.setDecimals(1)
        form.addRow("CFG Scale:", self.cfg_spin)

        # Size
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "512×512", "768×768", "1024×1024", "1024×768", "768×1024"
        ])
        form.addRow("Size:", self.size_combo)

        # Seed
        seed_layout = QHBoxLayout()
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("-1 (случайный)")
        self.seed_edit.setText("-1")
        seed_layout.addWidget(self.seed_edit)

        self.random_seed_btn = QPushButton("🎲")
        self.random_seed_btn.setFixedWidth(40)
        self.random_seed_btn.clicked.connect(self._random_seed)
        seed_layout.addWidget(self.random_seed_btn)

        form.addRow("Seed:", seed_layout)

        # Preview Every
        self.preview_every_spin = QSpinBox()
        self.preview_every_spin.setRange(0, 100)
        self.preview_every_spin.setValue(int(self.config.get("sdxl/preview_every", 0)))
        self.preview_every_spin.setToolTip(
            "Сохранять превью каждые N шагов (0 = выключено, 1 = каждый шаг)"
        )
        form.addRow("Превью каждые N шагов:", self.preview_every_spin)

        # Preview Start
        self.preview_start_spin = QSpinBox()
        self.preview_start_spin.setRange(1, 150)
        self.preview_start_spin.setValue(int(self.config.get("sdxl/preview_start", 1)))
        self.preview_start_spin.setToolTip(
            "Начинать сохранение превью с этого шага (ранние шаги = шум)"
        )
        form.addRow("Начальный шаг превью:", self.preview_start_spin)

        layout.addLayout(form)

        # Negative Prompt
        layout.addWidget(QLabel("Negative Prompt:"))
        self.negative_prompt = QTextEdit()
        self.negative_prompt.setPlaceholderText("ugly, blurry, low quality, deformed...")
        self.negative_prompt.setMaximumHeight(120)
        layout.addWidget(self.negative_prompt)

        layout.addStretch()

        # Кнопка очистки
        self.clear_btn = QPushButton("Очистить настройки")
        self.clear_btn.clicked.connect(self._clear_settings)
        layout.addWidget(self.clear_btn)

        # Загружаем модели и чекпоинты при старте
        self._load_models()

    def load_checkpoints_list(self):
        """Загружает список архивных чекпоинтов в ComboBox"""
        self.checkpoint_combo.clear()
        self.checkpoint_combo.addItem("-- Выберите чекпоинт --", None)

        checkpoints = list_archived_checkpoints()
        for cp in checkpoints:
            self.checkpoint_combo.addItem(cp["display_name"], cp["filename"])

    def get_selected_checkpoint(self):
        """Возвращает имя файла выбранного чекпоинта или None"""
        index = self.checkpoint_combo.currentIndex()
        if index <= 0:  # 0 — это placeholder
            return None
        return self.checkpoint_combo.itemData(index)

    def set_params_from_checkpoint(self, json_data: dict):
        """Заполняет поля настроек из JSON чекпоинта"""
        # Model
        model = json_data.get("model", "")
        if model:
            # Проверяем, есть ли такая модель в списке
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                self.model_combo.setEditText(model)

        # Scheduler
        scheduler = json_data.get("scheduler", "")
        if scheduler:
            index = self.scheduler_combo.findText(scheduler)
            if index >= 0:
                self.scheduler_combo.setCurrentIndex(index)

        # Steps
        steps = json_data.get("total_steps", 0)
        if steps > 0:
            self.steps_spin.setValue(steps)

        # CFG
        cfg = json_data.get("cfg", 0)
        if cfg > 0:
            self.cfg_spin.setValue(cfg)

        # Size
        width = json_data.get("width", 0)
        height = json_data.get("height", 0)
        if width > 0 and height > 0:
            size_text = f"{width}×{height}"
            index = self.size_combo.findText(size_text)
            if index >= 0:
                self.size_combo.setCurrentIndex(index)

        # Seed
        seed = json_data.get("seed", -1)
        self.seed_edit.setText(str(seed))

        # Negative prompt
        negative = json_data.get("negative_prompt", "")
        if negative:
            self.negative_prompt.setPlainText(negative)

    def get_end_label(self) -> str:
        """Возвращает текст для end_label (например, '30 шагов')"""
        return f"{self.steps_spin.value()} шагов"

    def _load_models(self):
        """Загружает список моделей из папки"""
        models_path = self.config.get_sdxl_models_path()
        current_text = self.model_combo.currentText()

        self.model_combo.clear()

        if not models_path or not os.path.exists(models_path):
            self.model_combo.addItem("model.safetensors")
            return

        models = set()
        for item in os.listdir(models_path):
            item_path = os.path.join(models_path, item)

            if os.path.isdir(item_path) and item.startswith("models--"):
                model_id = item[len("models--"):].replace("--", "/")
                models.add(model_id)
            elif os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    name = os.path.splitext(item)[0]
                    models.add(name)
            elif os.path.isdir(item_path) and not item.startswith("models--"):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    models.add(item)

        if models:
            self.model_combo.addItems(sorted(models))
            if current_text and current_text in models:
                self.model_combo.setCurrentText(current_text)
        else:
            self.model_combo.addItem("model.safetensors")

    def _random_seed(self):
        self.seed_edit.setText(str(random.randint(0, 2**32 - 1)))

    def _clear_settings(self):
        self.negative_prompt.clear()
        self.seed_edit.setText("-1")

    def save_settings(self):
        """Сохраняет настройки в конфиг"""
        self.config.set_sdxl_scheduler(self.scheduler_combo.currentText())
        self.config.set("sdxl/steps", self.steps_spin.value())
        self.config.set("sdxl/cfg", self.cfg_spin.value())
        self.config.set("sdxl/preview_every", self.preview_every_spin.value())
        self.config.set("sdxl/preview_start", self.preview_start_spin.value())

    def get_params(self):
        """Возвращает параметры генерации"""
        size_text = self.size_combo.currentText()
        width, height = map(int, size_text.replace('×', 'x').split('x'))

        params = {
            "model": self.model_combo.currentText(),
            "scheduler": self.scheduler_combo.currentText(),
            "steps": self.steps_spin.value(),
            "cfg": self.cfg_spin.value(),
            "width": width,
            "height": height,
            "seed": int(self.seed_edit.text()) if self.seed_edit.text().isdigit() else -1,
            "preview_every": self.preview_every_spin.value(),
            "preview_start": self.preview_start_spin.value()
        }

        return params
