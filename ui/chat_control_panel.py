from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


class ChatControlPanel(QWidget):
    """Панель управления чатом: 4 кнопки под ChatWidget"""
    
    # Сигналы
    new_chat_clicked = pyqtSignal()
    undo_last_clicked = pyqtSignal()
    attach_file_clicked = pyqtSignal()
    export_chat_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Кнопка "Новый чат"
        self.new_chat_btn = QPushButton("+ Новый чат")
        self.new_chat_btn.clicked.connect(self.new_chat_clicked.emit)
        layout.addWidget(self.new_chat_btn)
        
        # Кнопка "Отменить"
        self.undo_btn = QPushButton("↶ Отменить")
        self.undo_btn.clicked.connect(self.undo_last_clicked.emit)
        self.undo_btn.setEnabled(False)  # Неактивна, пока нет истории
        layout.addWidget(self.undo_btn)
        
        # Кнопка "Загрузить файл"
        self.attach_btn = QPushButton("📎 Файл")
        self.attach_btn.clicked.connect(self.attach_file_clicked.emit)
        layout.addWidget(self.attach_btn)
        
        # Кнопка "Сохранить чат"
        self.export_btn = QPushButton("💾 Сохранить")
        self.export_btn.clicked.connect(self.export_chat_clicked.emit)
        layout.addWidget(self.export_btn)
    
    def set_undo_enabled(self, enabled: bool):
        """Включает/выключает кнопку Отменить"""
        self.undo_btn.setEnabled(enabled)
