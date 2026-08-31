from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


class ChatControlPanel(QWidget):
    """Панель управления чатом: 5 кнопок под ChatWidget"""

    # Сигналы
    new_chat_clicked = pyqtSignal()
    undo_last_clicked = pyqtSignal()
    attach_file_clicked = pyqtSignal()
    rename_chat_clicked = pyqtSignal()
    delete_chat_clicked = pyqtSignal()

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
        self.rename_btn = QPushButton("✏ Переименовать")
        self.rename_btn.clicked.connect(self.rename_chat_clicked.emit)
        layout.addWidget(self.rename_btn)

        # Кнопка "Удалить чат"
        self.delete_btn = QPushButton("❌ Удалить чат")
        self.delete_btn.clicked.connect(self.delete_chat_clicked.emit)
        self.delete_btn.setEnabled(False)  # Неактивна, пока нет чата
        layout.addWidget(self.delete_btn)

    def set_undo_enabled(self, enabled: bool):
        """Включает/выключает кнопку Отменить"""
        self.undo_btn.setEnabled(enabled)

    def set_delete_enabled(self, enabled: bool):
        """Включает/выключает кнопку Удалить чат"""
        self.delete_btn.setEnabled(enabled)

    def set_rename_enabled(self, enabled: bool):
        """Включает/выключает кнопку Переименовать"""
        self.rename_btn.setEnabled(enabled)
