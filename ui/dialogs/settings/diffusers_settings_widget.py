from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                              QCheckBox, QLabel)
from PyQt6.QtCore import Qt

class DiffusersSettingsWidget(QWidget):
    """Виджет настроек Diffusers для меню"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Device (CPU/GPU)
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setToolTip(
            "Устройство для генерации. CPU — медленно, но работает без видеокарты. "
            "CUDA — быстро, но требует NVIDIA GPU с драйвером."
        )
        form.addRow("Устройство:", self.device_combo)

        # Safety Checker
        self.safety_check = QCheckBox("Отключить цензуру (NSFW filter)")
        self.safety_check.setToolTip(
            "Safety Checker блокирует изображения с NSFW-контентом. "
            "Отключение позволяет генерировать любые изображения, но может привести к артефактам."
        )
        form.addRow("", self.safety_check)

        layout.addLayout(form)
        layout.addStretch()

        # Загружаем настройки
        self.load_settings()

    def load_settings(self):
        """Загружает настройки из конфига в UI"""
        self.device_combo.setCurrentText(self.config.get("sdxl/device", "cuda"))
        self.safety_check.setChecked(self.config.get("sdxl/no_safety_checker", "false") == "true")

    def save_settings(self):
        """Сохраняет настройки из UI в конфиг"""
        self.config.set("sdxl/device", self.device_combo.currentText())
        self.config.set("sdxl/no_safety_checker", str(self.safety_check.isChecked()).lower())
