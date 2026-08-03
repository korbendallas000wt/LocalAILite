from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QComboBox,
QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton,
QTextEdit, QHBoxLayout, QLabel, QRadioButton)
from PyQt6.QtCore import Qt, pyqtSignal
import random
import os

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
        self.model_combo.setEditable(True)
        model_row.addWidget(self.model_combo, 1)
        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedWidth(40)
        self.refresh_models_btn.setToolTip("Обновить список моделей")
        self.refresh_models_btn.clicked.connect(self._load_models)
        model_row.addWidget(self.refresh_models_btn)
        layout.addLayout(model_row)
        
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
        layout.addWidget(self.scheduler_combo)
        
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
        self.clear_btn = QPushButton("Очистить настройки")
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
        history_dir = os.path.join(project_root, "data", "history")
        
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
        """Загружает список моделей из реестра"""
        from core.models_registry import load_registry
        
        current_text = self.model_combo.currentText()
        self.model_combo.clear()
        
        registry = load_registry(self.config)
        
        if registry:
            display_names = sorted(registry.keys())
            self.model_combo.addItems(display_names)
            
            if current_text and current_text in display_names:
                self.model_combo.setCurrentText(current_text)
        else:
            self.model_combo.addItem("model.safetensors")
    
    def _random_seed(self):
        self.seed_edit.setText(str(random.randint(0, 2**32 - 1)))
    
    def _clear_settings(self):
        self.negative_prompt.clear()
        self.seed_edit.setText("-1")
        self.checkpoint_edit.clear()
        self.init_image_edit.clear()
    
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
                # 2. Если не нашли — пробуем найти по пути в реестре
                from core.models_registry import load_registry
                registry = load_registry(self.config)
                found = False
                for display_name, path in registry.items():
                    if model in path or os.path.basename(path) == model:
                        idx = self.model_combo.findText(display_name)
                        if idx >= 0:
                            self.model_combo.setCurrentIndex(idx)
                            found = True
                            break
                if not found:
                    # 3. Совсем не нашли — устанавливаем как есть
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
            "steps": self.steps_spin.value(),
            "cfg": self.cfg_spin.value(),
            "width": width,
            "height": height,
            "seed": int(self.seed_edit.text()) if self.seed_edit.text().isdigit() else -1,
            "strength": self.strength_spin.value(),
            "init_image_path": self.init_image_edit.text() if self.init_image_edit.text() else ""
        }
        return params
