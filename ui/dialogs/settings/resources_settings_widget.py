from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QSpinBox,
                              QDoubleSpinBox, QLabel, QGroupBox)
from PyQt6.QtCore import Qt

class ResourcesSettingsWidget(QWidget):
    """Виджет настроек ресурсов (RAM, CPU)"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)
        
        # === Память ===
        memory_group = QGroupBox("Память (RAM)")
        memory_layout = QFormLayout()
        
        self.max_ram_spin = QSpinBox()
        self.max_ram_spin.setRange(50, 95)
        self.max_ram_spin.setValue(int(self.config.get("resources/max_ram_percent", 80)))
        self.max_ram_spin.setSuffix(" %")
        self.max_ram_spin.setToolTip(
            "Максимальный процент RAM, который может использовать приложение. "
            "Остальное оставляем для системы."
        )
        memory_layout.addRow("Максимум RAM:", self.max_ram_spin)
        
        # Информация о доступной памяти
        import psutil
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        self.memory_info = QLabel(
            f"Всего: {total_gb:.1f} GB | Доступно: {available_gb:.1f} GB"
        )
        self.memory_info.setStyleSheet("color: gray; font-size: 11px;")
        memory_layout.addRow("", self.memory_info)
        
        memory_group.setLayout(memory_layout)
        layout.addWidget(memory_group)
        
        # === Процессор ===
        cpu_group = QGroupBox("Процессор (CPU)")
        cpu_layout = QFormLayout()
        
        self.cpu_cores_spin = QSpinBox()
        self.cpu_cores_spin.setRange(1, 4)  # У тебя 4 ядра
        self.cpu_cores_spin.setValue(int(self.config.get("resources/cpu_cores", 3)))
        self.cpu_cores_spin.setToolTip(
            "Количество ядер CPU для приложения. "
            "Оставляем 1-2 ядра свободными для системы."
        )
        cpu_layout.addRow("Ядер CPU:", self.cpu_cores_spin)
        
        self.cpu_priority_spin = QSpinBox()
        self.cpu_priority_spin.setRange(-20, 19)
        self.cpu_priority_spin.setValue(int(self.config.get("resources/cpu_priority", 0)))
        self.cpu_priority_spin.setToolTip(
            "Приоритет процесса (nice). "
            "0 = нормальный, 10 = низкий (система отзывчивее), -10 = высокий."
        )
        cpu_layout.addRow("Приоритет (nice):", self.cpu_priority_spin)
        
        # Информация о CPU
        import os
        cpu_count = os.cpu_count() or 4
        self.cpu_info = QLabel(f"Всего ядер: {cpu_count}")
        self.cpu_info.setStyleSheet("color: gray; font-size: 11px;")
        cpu_layout.addRow("", self.cpu_info)
        
        cpu_group.setLayout(cpu_layout)
        layout.addWidget(cpu_group)
        
        layout.addStretch()
    
    def load_settings(self):
        """Загружает настройки из конфига в UI"""
        self.max_ram_spin.setValue(int(self.config.get("resources/max_ram_percent", 80)))
        self.cpu_cores_spin.setValue(int(self.config.get("resources/cpu_cores", 3)))
        self.cpu_priority_spin.setValue(int(self.config.get("resources/cpu_priority", 0)))
    
    def save_settings(self):
        """Сохраняет настройки из UI в конфиг"""
        self.config.set("resources/max_ram_percent", self.max_ram_spin.value())
        self.config.set("resources/cpu_cores", self.cpu_cores_spin.value())
        self.config.set("resources/cpu_priority", self.cpu_priority_spin.value())
