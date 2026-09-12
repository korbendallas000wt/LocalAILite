from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QComboBox,
QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton,
QTextEdit, QHBoxLayout, QLabel, QRadioButton, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
import random
import os
from core.model_presets import get_effective_preset
from core.models_registry import get_model_id_by_display_name

class DiffusersSettingsPanel(QWidget):
    """Панель настроек Diffusers с управлением чекпоинтами и режимами"""
    
    # Сигналы для DiffusersTab
    checkpoint_selected = pyqtSignal(str, str)  # history_dir, step_filename
    init_image_selected = pyqtSignal(str)  # filename
    mode_changed = pyqtSignal(str)  # "create" | "resume" | "edit"
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)
        
        # === Model ===
        layout.addWidget(QLabel("Model:"))
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        # editable=False: пользователь выбирает только из списка реестра
        model_row.addWidget(self.model_combo, 1)
        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedWidth(40)
        self.refresh_models_btn.setToolTip("Обновить список моделей")
        self.refresh_models_btn.clicked.connect(self._load_models)
        model_row.addWidget(self.refresh_models_btn)
        layout.addLayout(model_row)
        
        # Автоприменение пресета при выборе модели
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        
        # === Scheduler ===
        layout.addWidget(QLabel("Scheduler:"))
        self.scheduler_combo = QComboBox()
        self.scheduler_combo.addItems([
            "EulerDiscreteScheduler",
            "EulerAncestralDiscreteScheduler",
            "DPMSolverMultistepScheduler",
            "DDIMScheduler",
            "PNDMScheduler"
        ])
        self.scheduler_combo.setCurrentText(self.config.get_sdxl_scheduler())
        self.scheduler_combo.currentTextChanged.connect(self._on_scheduler_changed)
        layout.addWidget(self.scheduler_combo)
        
        # === Karras sigmas (только для DPMSolverMultistepScheduler) ===
        self.use_karras_check = QCheckBox("Использовать сигмы Карраса (Karras)")
        self.use_karras_check.setChecked(self.config.get("sdxl/use_karras_sigmas", "false") == "true")
        self.use_karras_check.toggled.connect(
            lambda checked: self.config.set("sdxl/use_karras_sigmas", "true" if checked else "false"))
        layout.addWidget(self.use_karras_check)
        # Начальная активация чекбокса в зависимости от планировщика
        self._on_scheduler_changed(self.scheduler_combo.currentText())
        
        # === Timestep Spacing (распределение шагов по шкале времени) ===
        layout.addWidget(QLabel("Timestep Spacing:"))
        self.timestep_spacing_combo = QComboBox()
        self.timestep_spacing_combo.addItems(["leading", "linspace", "trailing"])
        self.timestep_spacing_combo.setCurrentText(self.config.get("sdxl/timestep_spacing", "leading"))
        self.timestep_spacing_combo.setToolTip("Как шаги распределяются по шкале времени:\nleading (по умолчанию) / linspace (равномерно) / trailing (с конца)")
        self.timestep_spacing_combo.currentTextChanged.connect(
            lambda text: self.config.set("sdxl/timestep_spacing", text))
        layout.addWidget(self.timestep_spacing_combo)
        
        # === Size + Seed в QGridLayout (лейблы НАД полями) ===
        size_seed_grid = QGridLayout()
        size_seed_grid.addWidget(QLabel("Size:"), 0, 0)
        size_seed_grid.addWidget(QLabel("Seed:"), 0, 1)
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "512×512", "768×768", "1024×1024", "1024×768", "768×1024"
        ])
        size_seed_grid.addWidget(self.size_combo, 1, 0)
        seed_row = QHBoxLayout()
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("-1 (случайный)")
        self.seed_edit.setText("-1")
        seed_row.addWidget(self.seed_edit)
        self.random_seed_btn = QPushButton("🎲")
        self.random_seed_btn.setFixedWidth(40)
        self.random_seed_btn.clicked.connect(self._random_seed)
        seed_row.addWidget(self.random_seed_btn)
        size_seed_grid.addLayout(seed_row, 1, 1)
        layout.addLayout(size_seed_grid)
        
        # === Steps + CFG + Strength в QGridLayout (лейблы НАД полями) ===
        steps_cfg_grid = QGridLayout()
        steps_cfg_grid.addWidget(QLabel("Steps:"), 0, 0)
        steps_cfg_grid.addWidget(QLabel("CFG Scale:"), 0, 1)
        steps_cfg_grid.addWidget(QLabel("Strength:"), 0, 2)
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 150)
        self.steps_spin.setValue(self.config.get_sdxl_default_steps())
        steps_cfg_grid.addWidget(self.steps_spin, 1, 0)
        self.cfg_spin = QDoubleSpinBox()
        self.cfg_spin.setRange(1.0, 30.0)
        self.cfg_spin.setValue(self.config.get_sdxl_default_cfg())
        self.cfg_spin.setSingleStep(0.5)
        self.cfg_spin.setDecimals(1)
        steps_cfg_grid.addWidget(self.cfg_spin, 1, 1)
        self.strength_spin = QDoubleSpinBox()
        self.strength_spin.setRange(0.0, 1.0)
        self.strength_spin.setValue(0.75)
        self.strength_spin.setSingleStep(0.05)
        self.strength_spin.setDecimals(2)
        steps_cfg_grid.addWidget(self.strength_spin, 1, 2)
        layout.addLayout(steps_cfg_grid)
        
        # === Negative Prompt ===
        layout.addWidget(QLabel("Negative Prompt:"))
        self.negative_prompt = QTextEdit()
        self.negative_prompt.setPlaceholderText("ugly, blurry, low quality, deformed...")
        self.negative_prompt.setMaximumHeight(120)
        layout.addWidget(self.negative_prompt)
        
        # === Чекпоинт ===
        layout.addWidget(QLabel("Чекпоинт:"))
        checkpoint_row = QHBoxLayout()
        self.checkpoint_edit = QLineEdit()
        self.checkpoint_edit.setReadOnly(True)
        self.checkpoint_edit.setPlaceholderText("не выбран")
        checkpoint_row.addWidget(self.checkpoint_edit)
        self.checkpoint_browse_btn = QPushButton("📂")
        self.checkpoint_browse_btn.setFixedWidth(40)
        self.checkpoint_browse_btn.clicked.connect(self._browse_checkpoint)
        checkpoint_row.addWidget(self.checkpoint_browse_btn)
        layout.addLayout(checkpoint_row)
        
        # === Картинка (init) ===
        layout.addWidget(QLabel("Картинка (init):"))
        image_row = QHBoxLayout()
        self.init_image_edit = QLineEdit()
        self.init_image_edit.setReadOnly(True)
        self.init_image_edit.setPlaceholderText("не выбрана")
        image_row.addWidget(self.init_image_edit)
        self.init_image_browse_btn = QPushButton("📂")
        self.init_image_browse_btn.setFixedWidth(40)
        self.init_image_browse_btn.clicked.connect(self._browse_init_image)
        image_row.addWidget(self.init_image_browse_btn)
        layout.addLayout(image_row)
        
        # === Кнопка очистки ===
        self.clear_btn = QPushButton("Сбросить к пресету")
        self.clear_btn.clicked.connect(self._clear_settings)
        layout.addWidget(self.clear_btn)
        
        # === Радиокнопки режимов (горизонтально, без надписи) ===
        layout.addSpacing(10)
        mode_row = QHBoxLayout()
        self.mode_create_radio = QRadioButton("Создать")
        self.mode_create_radio.setChecked(True)
        self.mode_create_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_create_radio)
        
        self.mode_resume_radio = QRadioButton("Продолжить")
        self.mode_resume_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_resume_radio)
        
        self.mode_edit_radio = QRadioButton("Изменить")
        self.mode_edit_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_edit_radio)
        
        layout.addLayout(mode_row)
        
        layout.addStretch()
        
        # Загружаем модели при старте
        self._load_models()
    
    def _browse_checkpoint(self):
        """Открывает диалог выбора step файла из data/history/"""
        from PyQt6.QtWidgets import QFileDialog
        
        # Начальная папка: data/history/ (абсолютный путь)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        history_dir = os.path.join(project_root, "data", "diffusers", "history")
        
        # Один диалог выбора файла, фильтр *.pt
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите шаг для продолжения",
            history_dir,
            "Step files (*.pt);;Все файлы (*)"
        )
        if not file_path:
            return
        
        # Извлекаем history_dir и step_filename из полного пути
        history_dir = os.path.dirname(file_path)
        step_filename = os.path.basename(file_path)
        
        # Отображаем в поле: "папка / файл"
        folder_name = os.path.basename(history_dir)
        self.checkpoint_edit.setText(f"{folder_name} / {step_filename}")
        
        # Эмитим сигнал с полной информацией
        self.checkpoint_selected.emit(history_dir, step_filename)

    def _browse_init_image(self):
        """Открывает диалог выбора init-картинки"""
        from PyQt6.QtWidgets import QFileDialog
        init_images_dir = self.config.get_init_images_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение",
            init_images_dir,
            "Изображения (*.png *.jpg *.jpeg *.webp);;Все файлы (*)"
        )
        if file_path:
            self.init_image_edit.setText(os.path.basename(file_path))
            self.init_image_selected.emit(os.path.basename(file_path))
    
    def _on_mode_changed(self):
        """Обновляет активность полей при смене режима"""
        if self.mode_create_radio.isChecked():
            mode = "create"
        elif self.mode_resume_radio.isChecked():
            mode = "resume"
        else:
            mode = "edit"
        
        self.mode_changed.emit(mode)
    
    def get_current_mode(self) -> str:
        """Возвращает текущий режим: create/resume/edit"""
        if self.mode_create_radio.isChecked():
            return "create"
        elif self.mode_resume_radio.isChecked():
            return "resume"
        else:
            return "edit"
    
    def set_field_enabled(self, field_name: str, enabled: bool):
        """Включает/отключает поле по имени"""
        field_map = {
            "strength": self.strength_spin,
            "checkpoint": (self.checkpoint_edit, self.checkpoint_browse_btn),
            "init_image": (self.init_image_edit, self.init_image_browse_btn)
        }
        
        if field_name in field_map:
            field = field_map[field_name]
            if isinstance(field, tuple):
                for f in field:
                    f.setEnabled(enabled)
            else:
                field.setEnabled(enabled)
    
    def _load_models(self):
        """Загружает список моделей из реестра v2.0 (короткие имена).
        Если реестр пуст — ComboBox остаётся пустым (без fallback).
        """
        from core.models_registry import load_registry
        
        current_text = self.model_combo.currentText()
        self.model_combo.clear()
        
        registry = load_registry(self.config)
        
        if registry:
            display_names = sorted(registry.keys())
            self.model_combo.addItems(display_names)
            
            if current_text and current_text in display_names:
                self.model_combo.setCurrentText(current_text)
    
    def _on_scheduler_changed(self, scheduler_name: str):
        """Активирует/деактивирует чекбокс Karras в зависимости от планировщика.
        
        Karras сигмы поддерживаются только планировщиком DPMSolverMultistepScheduler.
        Для остальных чекбокс деактивируется (значение игнорируется скриптом).
        """
        supports_karras = (scheduler_name == "DPMSolverMultistepScheduler")
        self.use_karras_check.setEnabled(supports_karras)
        if not supports_karras:
            self.use_karras_check.setChecked(False)

    def _on_model_changed(self, display_name: str):
        """Применяет пресет модели при смене выбора в комбобоксе.
        
        Загружает эффективный пресет (сохранённый + дефолты) и устанавливает
        значения во все поля панели. Использует blockSignals для защиты
        от рекурсии при установке значений.
        
        Режимы:
        - «Создать»: пресет применяется автоматически при смене модели
        - «Изменить»: смена модели НЕ применяет пресет (настройки из чекпоинта)
        - «Продолжить»: модель заблокирована, смена невозможна
        """
        if not display_name:
            return
        
        # Пресет применяется только в режиме «Создать»
        # В режиме «Изменить» пользователь меняет модель, но настройки из чекпоинта сохраняются
        if not self.mode_create_radio.isChecked():
            return
        
        # Получаем ключ реестра (model_id) по отображаемому имени
        model_id = get_model_id_by_display_name(self.config, display_name)
        
        if not model_id:
            return
        
        # Загружаем эффективный пресет
        preset = get_effective_preset(self.config, model_id)
        if not preset:
            return
        
        # Блокируем сигналы при установке значений (защита от рекурсии)
        self.blockSignals(True)
        try:
            # Планировщик
            scheduler = preset.get("scheduler", "")
            if scheduler:
                idx = self.scheduler_combo.findText(scheduler)
                if idx >= 0:
                    self.scheduler_combo.setCurrentIndex(idx)
            
            # Timestep Spacing
            timestep_spacing = preset.get("timestep_spacing", "")
            if timestep_spacing:
                idx = self.timestep_spacing_combo.findText(timestep_spacing)
                if idx >= 0:
                    self.timestep_spacing_combo.setCurrentIndex(idx)
            
            # Karras sigmas (применяется только если планировщик поддерживает)
            use_karras = preset.get("use_karras_sigmas", False)
            if self.use_karras_check.isEnabled():
                self.use_karras_check.setChecked(use_karras)
            
            # Шаги
            steps = preset.get("steps")
            if steps is not None:
                self.steps_spin.setValue(steps)
            
            # CFG
            cfg = preset.get("cfg")
            if cfg is not None:
                self.cfg_spin.setValue(cfg)
            
            # Размер
            width = preset.get("width")
            height = preset.get("height")
            if width and height:
                size_text = f"{width}×{height}"
                idx = self.size_combo.findText(size_text)
                if idx >= 0:
                    self.size_combo.setCurrentIndex(idx)
            
            # Сид
            seed = preset.get("seed")
            if seed is not None:
                self.seed_edit.setText(str(seed))
            
            # Негативный промпт
            negative_prompt = preset.get("negative_prompt")
            if negative_prompt is not None:
                self.negative_prompt.setPlainText(negative_prompt)
            
            # Strength
            strength = preset.get("strength")
            if strength is not None:
                self.strength_spin.setValue(strength)
        finally:
            self.blockSignals(False)

    def _random_seed(self):
        self.seed_edit.setText(str(random.randint(0, 2**32 - 1)))
    
    def _clear_settings(self):
        """Применяет пресет текущей выбранной модели.
        
        Загружает эффективный пресет через get_effective_preset() и устанавливает
        значения во все поля пресета (планировщик, timestep_spacing, размер, сид,
        шаги, cfg, strength, негативный промпт).
        
        НЕ трогает: checkpoint_edit, init_image_edit (не параметры пресета).
        """
        display_name = self.model_combo.currentText()
        if not display_name:
            return
        
        # Получаем ключ реестра (model_id) по display_name
        from core.models_registry import get_model_id_by_display_name
        model_id = get_model_id_by_display_name(self.config, display_name)
        if not model_id:
            return
        
        # Загружаем эффективный пресет
        preset = get_effective_preset(self.config, model_id)
        if not preset:
            return
        
        # Блокируем сигналы при установке значений (защита от рекурсии)
        self.blockSignals(True)
        try:
            # Планировщик
            scheduler = preset.get("scheduler", "")
            if scheduler:
                idx = self.scheduler_combo.findText(scheduler)
                if idx >= 0:
                    self.scheduler_combo.setCurrentIndex(idx)
            
            # Timestep Spacing
            timestep_spacing = preset.get("timestep_spacing", "")
            if timestep_spacing:
                idx = self.timestep_spacing_combo.findText(timestep_spacing)
                if idx >= 0:
                    self.timestep_spacing_combo.setCurrentIndex(idx)
            
            # Karras sigmas (применяется только если планировщик поддерживает)
            use_karras = preset.get("use_karras_sigmas", False)
            if self.use_karras_check.isEnabled():
                self.use_karras_check.setChecked(use_karras)
            
            # Шаги
            steps = preset.get("steps")
            if steps is not None:
                self.steps_spin.setValue(steps)
            
            # CFG
            cfg = preset.get("cfg")
            if cfg is not None:
                self.cfg_spin.setValue(cfg)
            
            # Размер
            width = preset.get("width")
            height = preset.get("height")
            if width and height:
                size_text = f"{width}×{height}"
                idx = self.size_combo.findText(size_text)
                if idx >= 0:
                    self.size_combo.setCurrentIndex(idx)
            
            # Сид
            seed = preset.get("seed")
            if seed is not None:
                self.seed_edit.setText(str(seed))
            
            # Негативный промпт
            negative_prompt = preset.get("negative_prompt")
            if negative_prompt is not None:
                self.negative_prompt.setPlainText(negative_prompt)
            
            # Strength
            strength = preset.get("strength")
            if strength is not None:
                self.strength_spin.setValue(strength)
        finally:
            self.blockSignals(False)
    
    def set_params_from_checkpoint(self, json_data: dict):
        """Заполняет поля настроек из JSON чекпоинта"""
        # Model
        model = json_data.get("model", "")
        if model:
            # 1. Ищем по красивому имени
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                # 2. Если не нашли — пробуем найти по пути в реестре (формат v2.0)
                from core.models_registry import load_registry
                registry = load_registry(self.config)
                found = False
                for display_name, info in registry.items():
                    path = info.get("path", "") if isinstance(info, dict) else str(info)
                    if model in path or os.path.basename(path) == model:
                        idx = self.model_combo.findText(display_name)
                        if idx >= 0:
                            self.model_combo.setCurrentIndex(idx)
                            found = True
                            break
                if not found:
                    # 3. Совсем не нашли — ComboBox остаётся без выбора
                    # (editable=False, setEditText недоступен)
                    pass
        
        # Scheduler
        scheduler = json_data.get("scheduler", "")
        if scheduler:
            index = self.scheduler_combo.findText(scheduler)
            if index >= 0:
                self.scheduler_combo.setCurrentIndex(index)
        
        # Timestep Spacing
        timestep_spacing = json_data.get("timestep_spacing", "")
        if timestep_spacing:
            index = self.timestep_spacing_combo.findText(timestep_spacing)
            if index >= 0:
                self.timestep_spacing_combo.setCurrentIndex(index)
        
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
    
    def save_settings(self):
        """Сохраняет настройки в конфиг"""
        self.config.set_sdxl_scheduler(self.scheduler_combo.currentText())
        self.config.set("sdxl/steps", self.steps_spin.value())
        self.config.set("sdxl/cfg", self.cfg_spin.value())
    
    def get_params(self):
        """Возвращает параметры генерации"""
        size_text = self.size_combo.currentText()
        width, height = map(int, size_text.replace('×', 'x').split('x'))
        params = {
            "model": self.model_combo.currentText(),
            "scheduler": self.scheduler_combo.currentText(),
            "timestep_spacing": self.timestep_spacing_combo.currentText(),
            "use_karras_sigmas": self.use_karras_check.isChecked(),
            "steps": self.steps_spin.value(),
            "cfg": self.cfg_spin.value(),
            "width": width,
            "height": height,
            "seed": int(self.seed_edit.text()) if self.seed_edit.text().isdigit() else -1,
            "strength": self.strength_spin.value(),
            "init_image_path": self.init_image_edit.text() if self.init_image_edit.text() else ""
        }
        return params
