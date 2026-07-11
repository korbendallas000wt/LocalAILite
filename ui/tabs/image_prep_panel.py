"""
Правая панель настроек для вкладки Visual editor.
Выбор пресета разрешения и режима обрезки.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QLabel, QComboBox, QRadioButton, QPushButton
)
from PyQt6.QtCore import pyqtSignal


class ImagePrepPanel(QWidget):
    """Правая панель с настройками обработки изображения"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        """Инициализация UI компонентов"""
        layout = QVBoxLayout(self)
        
        # === Первая строка: кнопка выбора файла ===
        self.open_btn = QPushButton("📁 Выбрать картинку")
        self.open_btn.setToolTip("Выберите изображение для подготовки")
        layout.addWidget(self.open_btn)
        
        # === Группа Подготовка ===
        prep_group = QGroupBox("Подготовка")
        prep_layout = QVBoxLayout()
        
        # Пресет разрешения
        preset_form = QFormLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "1024×1024 (квадрат)",
            "1152×896 (альбом 4:3)",
            "896×1152 (портрет 4:3)",
            "1216×832 (альбом 3:2)",
            "832×1216 (портрет 3:2)",
            "1344×768 (альбом 16:9)",
            "768×1344 (портрет 16:9)",
            "1536×640 (широкий)",
            "640×1536 (узкий)"
        ])
        self.preset_combo.setToolTip(
            "Выберите целевое разрешение для генерации.\n"
            "SDXL оптимизирована под эти размеры."
        )
        preset_form.addRow("Разрешение:", self.preset_combo)
        prep_layout.addLayout(preset_form)
        
        # Режим обрезки
        self.crop_center_radio = QRadioButton("Center crop (вырезать центр)")
        self.crop_center_radio.setChecked(True)
        self.crop_center_radio.setToolTip(
            "Вырезает центральную часть изображения.\n"
            "Сохраняет пропорции, без искажений.\n"
            "Может обрезать края."
        )
        prep_layout.addWidget(self.crop_center_radio)
        
        self.crop_letterbox_radio = QRadioButton("Letterbox (добавить поля)")
        self.crop_letterbox_radio.setToolTip(
            "Добавляет чёрные поля сверху/снизу или по бокам.\n"
            "Сохраняет пропорции, ничего не обрезает."
        )
        prep_layout.addWidget(self.crop_letterbox_radio)
        
        self.crop_stretch_radio = QRadioButton("Stretch (растянуть)")
        self.crop_stretch_radio.setToolTip(
            "Растягивает изображение до целевого размера.\n"
            "Может исказить пропорции."
        )
        prep_layout.addWidget(self.crop_stretch_radio)
        
        prep_group.setLayout(prep_layout)
        layout.addWidget(prep_group)
        
        # === Кнопки обработки и сохранения ===
        buttons_layout = QVBoxLayout()
        
        self.process_btn = QPushButton("🔄 Обработать")
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip(
            "Обработать изображение с выбранными параметрами.\n"
            "Результат будет показан в превью."
        )
        self.process_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        buttons_layout.addWidget(self.process_btn)
        
        self.save_btn = QPushButton("💾 Сохранить")
        self.save_btn.setEnabled(False)
        self.save_btn.setToolTip("Сохранить обработанное изображение")
        self.save_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        buttons_layout.addWidget(self.save_btn)
        
        layout.addLayout(buttons_layout)
        layout.addStretch()
    
    def get_crop_mode(self) -> str:
        """Возвращает выбранный режим обрезки"""
        if self.crop_center_radio.isChecked():
            return "center"
        elif self.crop_letterbox_radio.isChecked():
            return "letterbox"
        else:
            return "stretch"
    
    def get_target_size(self) -> tuple[int, int]:
        """Возвращает целевой размер (width, height) из пресета"""
        from core.image_processor import parse_preset
        preset_text = self.preset_combo.currentText()
        return parse_preset(preset_text)
