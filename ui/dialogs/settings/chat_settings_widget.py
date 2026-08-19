from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLineEdit, QPushButton, QFileDialog, QLabel
from PyQt6.QtCore import pyqtSignal


class ChatSettingsWidget(QWidget):
    all_valid = pyqtSignal()
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Формат сохранения чатов:"))
        
        self.json_check = QCheckBox("Хранить в JSON (для RAG и поиска)")
        self.json_check.setChecked(self.config.get("chat_save_json", True))
        layout.addWidget(self.json_check)
        
        self.txt_check = QCheckBox("Хранить в TXT (для чтения и архива)")
        self.txt_check.setChecked(self.config.get("chat_save_txt", True))
        layout.addWidget(self.txt_check)
        
        layout.addSpacing(10)
        
        self.auto_scroll_check = QCheckBox("Автопрокрутка к новому сообщению")
        self.auto_scroll_check.setChecked(self.config.get("chat_auto_scroll", True))
        layout.addWidget(self.auto_scroll_check)
        
        layout.addSpacing(10)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Папка:"))
        self.chats_dir_edit = QLineEdit()
        self.chats_dir_edit.setText(self.config.get("chats_dir", "data/ollama/chats"))
        self.chats_dir_edit.setReadOnly(True)
        path_layout.addWidget(self.chats_dir_edit, 1)
        
        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.clicked.connect(self._browse_dir)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)
        
        layout.addStretch()
        
    def _browse_dir(self):
        current_dir = self.chats_dir_edit.text()
        dir_path = QFileDialog.getExistingDirectory(self, "Выберите папку для чатов", current_dir)
        if dir_path:
            self.chats_dir_edit.setText(dir_path)
            
    def save_settings(self):
        self.config.set("chat_save_json", self.json_check.isChecked())
        self.config.set("chat_save_txt", self.txt_check.isChecked())
        self.config.set("chat_auto_scroll", self.auto_scroll_check.isChecked())
        self.config.set("chats_dir", self.chats_dir_edit.text())
