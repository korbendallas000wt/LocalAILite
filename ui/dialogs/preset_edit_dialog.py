"""Диалог настройки пресета модели.

Этап 5.3: калька панели настроек + ссылка на страницу модели.

Открывается из Менеджера моделей (кнопка «Настроить пресет»).
Позволяет пользователю настроить параметры по умолчанию для модели,
сверившись с рекомендациями на странице модели (ссылка вверху диалога).

Структура полей зависит от типа модели:
- Диффузерс: планировщик, timestep_spacing, размер, сид, шаги,
  cfg, strength, негативный промпт
- Оллама: температура, топ-п, макс-токены, таймаут (опционально)

При сохранении вызывает save_preset() — пресет сохраняется в реестр
и автоматически применяется при выборе модели в комбобоксе.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
                             QLineEdit, QTextEdit, QPushButton, QGroupBox)
from PyQt6.QtCore import Qt
from core.model_presets import get_effective_preset, save_preset, get_builtin_default
from core.models_registry import get_model_page_url


class PresetEditDialog(QDialog):
    """Диалог настройки пресета модели."""

    def __init__(self, config, model_id: str, model_type: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.model_id = model_id
        self.model_type = model_type

        self.setWindowTitle("Настройка пресета модели")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        # === Ссылка на страницу модели (для сверки с рекомендациями) ===
        url = get_model_page_url(config, model_id)
        if url:
            link_label = QLabel(f'<a href="{url}">🔗 Открыть страницу модели (рекомендации)</a>')
            link_label.setTextFormat(Qt.TextFormat.RichText)
            link_label.setOpenExternalLinks(True)
            link_label.setToolTip(url)
            layout.addWidget(link_label)

            hint = QLabel("Сверьтесь с рекомендациями на странице модели и заполните поля ниже.")
            hint.setStyleSheet("color: gray; font-size: 11px;")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        else:
            no_link = QLabel("Страница модели недоступна (нестандартный источник).")
            no_link.setStyleSheet("color: gray; font-size: 11px;")
            layout.addWidget(no_link)

        layout.addSpacing(8)

        # === Поля пресета (зависят от типа модели) ===
        preset = get_effective_preset(config, model_id)

        if model_type == "diffusers":
            self._build_diffusers_fields(layout, preset)
        elif model_type == "ollama":
            self._build_ollama_fields(layout, preset)
        else:
            layout.addWidget(QLabel(f"Неизвестный тип модели: {model_type}"))

        layout.addStretch()

        # === Кнопки ===
        btn_layout = QHBoxLayout()

        self.reset_btn = QPushButton("Сбросить к дефолтам")
        self.reset_btn.setToolTip("Вернуть встроенные дефолты для этого типа модели")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(self.reset_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    # ─── Поля Диффузерс ───

    def _build_diffusers_fields(self, layout: QVBoxLayout, preset: dict):
        """Создаёт поля пресета для Диффузерс (калька панели настроек)."""
        group = QGroupBox("Параметры генерации")
        grid = QGridLayout(group)
        grid.setSpacing(8)

        row = 0

        # Планировщик
        grid.addWidget(QLabel("Планировщик:"), row, 0)
        self.scheduler_combo = QComboBox()
        self.scheduler_combo.addItems([
            "EulerDiscreteScheduler",
            "EulerAncestralDiscreteScheduler",
            "DPMSolverMultistepScheduler",
            "DDIMScheduler",
            "PNDMScheduler"
        ])
        self.scheduler_combo.setCurrentText(preset.get("scheduler", "EulerDiscreteScheduler"))
        grid.addWidget(self.scheduler_combo, row, 1)
        row += 1

        # Timestep Spacing
        grid.addWidget(QLabel("Timestep Spacing:"), row, 0)
        self.timestep_spacing_combo = QComboBox()
        self.timestep_spacing_combo.addItems(["leading", "linspace", "trailing"])
        self.timestep_spacing_combo.setCurrentText(preset.get("timestep_spacing", "leading"))
        grid.addWidget(self.timestep_spacing_combo, row, 1)
        row += 1

        # Размер
        grid.addWidget(QLabel("Размер:"), row, 0)
        self.size_combo = QComboBox()
        self.size_combo.addItems(["512×512", "768×768", "1024×1024", "1024×768", "768×1024"])
        width = preset.get("width", 1024)
        height = preset.get("height", 1024)
        size_text = f"{width}×{height}"
        idx = self.size_combo.findText(size_text)
        if idx >= 0:
            self.size_combo.setCurrentIndex(idx)
        grid.addWidget(self.size_combo, row, 1)
        row += 1

        # Сид
        grid.addWidget(QLabel("Сид (-1 = случайный):"), row, 0)
        self.seed_edit = QLineEdit()
        self.seed_edit.setText(str(preset.get("seed", -1)))
        grid.addWidget(self.seed_edit, row, 1)
        row += 1

        # Шаги
        grid.addWidget(QLabel("Шаги:"), row, 0)
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 150)
        self.steps_spin.setValue(preset.get("steps", 30))
        grid.addWidget(self.steps_spin, row, 1)
        row += 1

        # CFG
        grid.addWidget(QLabel("CFG Scale:"), row, 0)
        self.cfg_spin = QDoubleSpinBox()
        self.cfg_spin.setRange(1.0, 30.0)
        self.cfg_spin.setSingleStep(0.5)
        self.cfg_spin.setValue(preset.get("cfg", 7.5))
        grid.addWidget(self.cfg_spin, row, 1)
        row += 1

        # Strength
        grid.addWidget(QLabel("Strength (img2img):"), row, 0)
        self.strength_spin = QDoubleSpinBox()
        self.strength_spin.setRange(0.0, 1.0)
        self.strength_spin.setSingleStep(0.05)
        self.strength_spin.setValue(preset.get("strength", 0.75))
        grid.addWidget(self.strength_spin, row, 1)
        row += 1

        layout.addWidget(group)

        # Негативный промпт (отдельный блок)
        neg_group = QGroupBox("Негативный промпт")
        neg_layout = QVBoxLayout(neg_group)
        self.negative_prompt_edit = QTextEdit()
        self.negative_prompt_edit.setPlaceholderText("Что исключить из генерации (например: blurry, low quality)")
        self.negative_prompt_edit.setPlainText(preset.get("negative_prompt", ""))
        self.negative_prompt_edit.setFixedHeight(60)
        neg_layout.addWidget(self.negative_prompt_edit)
        layout.addWidget(neg_group)

    # ─── Поля Олламы ───

    def _build_ollama_fields(self, layout: QVBoxLayout, preset: dict):
        """Создаёт поля пресета для Олламы (параметры чата)."""
        group = QGroupBox("Параметры чата")
        grid = QGridLayout(group)
        grid.setSpacing(8)

        row = 0

        # Температура
        grid.addWidget(QLabel("Температура:"), row, 0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(preset.get("temperature", 0.8))
        grid.addWidget(self.temperature_spin, row, 1)
        row += 1

        # Топ-п
        grid.addWidget(QLabel("Топ-п:"), row, 0)
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(preset.get("top_p", 0.9))
        grid.addWidget(self.top_p_spin, row, 1)
        row += 1

        # Макс-токены
        grid.addWidget(QLabel("Макс. токенов:"), row, 0)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 8192)
        self.max_tokens_spin.setSingleStep(256)
        self.max_tokens_spin.setValue(preset.get("max_tokens", 2048))
        grid.addWidget(self.max_tokens_spin, row, 1)
        row += 1

        # Таймаут (опционально)
        grid.addWidget(QLabel("Таймаут (-1 = не менять):"), row, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(-1, 3600)
        self.timeout_spin.setSingleStep(30)
        self.timeout_spin.setValue(preset.get("timeout", -1))
        grid.addWidget(self.timeout_spin, row, 1)
        row += 1

        layout.addWidget(group)

        # Системный промпт (отдельный блок)
        sys_group = QGroupBox("Системный промпт")
        sys_layout = QVBoxLayout(sys_group)
        sys_hint = QLabel("Оставьте пустым, чтобы не менять текущий системный промпт при выборе модели.")
        sys_hint.setStyleSheet("color: gray; font-size: 11px;")
        sys_hint.setWordWrap(True)
        sys_layout.addWidget(sys_hint)
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setPlaceholderText("Системный промпт для этой модели (пусто = не менять текущий)")
        self.system_prompt_edit.setPlainText(preset.get("system_prompt", ""))
        self.system_prompt_edit.setFixedHeight(80)
        sys_layout.addWidget(self.system_prompt_edit)
        layout.addWidget(sys_group)

    # ─── Обработчики ───

    def _on_reset_clicked(self):
        """Сбрасывает поля к встроенным дефолтам для типа модели."""
        defaults = get_builtin_default(self.model_type)
        if not defaults:
            return

        if self.model_type == "diffusers":
            self._fill_diffusers_fields(defaults)
        elif self.model_type == "ollama":
            self._fill_ollama_fields(defaults)

    def _fill_diffusers_fields(self, preset: dict):
        """Заполняет поля Диффузерс из словаря пресета."""
        idx = self.scheduler_combo.findText(preset.get("scheduler", ""))
        if idx >= 0:
            self.scheduler_combo.setCurrentIndex(idx)

        idx = self.timestep_spacing_combo.findText(preset.get("timestep_spacing", ""))
        if idx >= 0:
            self.timestep_spacing_combo.setCurrentIndex(idx)

        width = preset.get("width", 1024)
        height = preset.get("height", 1024)
        size_text = f"{width}×{height}"
        idx = self.size_combo.findText(size_text)
        if idx >= 0:
            self.size_combo.setCurrentIndex(idx)

        self.seed_edit.setText(str(preset.get("seed", -1)))
        self.steps_spin.setValue(preset.get("steps", 30))
        self.cfg_spin.setValue(preset.get("cfg", 7.5))
        self.strength_spin.setValue(preset.get("strength", 0.75))
        self.negative_prompt_edit.setPlainText(preset.get("negative_prompt", ""))

    def _fill_ollama_fields(self, preset: dict):
        """Заполняет поля Олламы из словаря пресета."""
        self.temperature_spin.setValue(preset.get("temperature", 0.8))
        self.top_p_spin.setValue(preset.get("top_p", 0.9))
        self.max_tokens_spin.setValue(preset.get("max_tokens", 2048))
        self.timeout_spin.setValue(preset.get("timeout", -1))
        self.system_prompt_edit.setPlainText(preset.get("system_prompt", ""))

    def _on_save_clicked(self):
        """Собирает значения полей и сохраняет пресет в реестр."""
        preset = {}

        if self.model_type == "diffusers":
            size_text = self.size_combo.currentText()
            width, height = map(int, size_text.replace("×", "x").split("x"))
            preset = {
                "scheduler": self.scheduler_combo.currentText(),
                "timestep_spacing": self.timestep_spacing_combo.currentText(),
                "width": width,
                "height": height,
                "seed": int(self.seed_edit.text()) if self.seed_edit.text().lstrip("-").isdigit() else -1,
                "steps": self.steps_spin.value(),
                "cfg": self.cfg_spin.value(),
                "strength": self.strength_spin.value(),
                "negative_prompt": self.negative_prompt_edit.toPlainText(),
            }
        elif self.model_type == "ollama":
            preset = {
                "temperature": self.temperature_spin.value(),
                "top_p": self.top_p_spin.value(),
                "max_tokens": self.max_tokens_spin.value(),
                "timeout": self.timeout_spin.value(),
                "system_prompt": self.system_prompt_edit.toPlainText(),
            }

        if preset:
            save_preset(self.config, self.model_id, preset)

        self.accept()
