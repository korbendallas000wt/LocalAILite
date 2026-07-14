from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

class HistorySaveDialog(QDialog):
    """Диалог сохранения истории генерации"""
    
    # Сигналы
    save_with_previews = pyqtSignal()      # Да + чекбокс
    save_without_previews = pyqtSignal()   # Да без чекбокса
    delete_history = pyqtSignal()          # Нет
    
    def __init__(self, is_stopped=False, parent=None):
        super().__init__(parent)
        self.is_stopped = is_stopped
        self._timeout = 60  # секунд
        
        self.setWindowTitle("Сохранить историю генерации?")
        self.setFixedSize(450, 200)
        
        layout = QVBoxLayout(self)
        
        # Заголовок
        if is_stopped:
            title = "Генерация остановлена. Сохранить историю?"
        else:
            title = "Генерация завершена. Сохранить историю?"
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Чекбокс
        self.preview_check = QCheckBox("Создать превью всех шагов")
        self.preview_check.setChecked(True)
        self.preview_check.setToolTip(
            "Декодировать все .pt файлы в PNG.\n"
            "Это займёт несколько минут, но позволит просматривать историю."
        )
        layout.addWidget(self.preview_check)
        
        # Таймер
        self.timer_label = QLabel(f"Автоматическое сохранение через: {self._timeout} сек")
        self.timer_label.setStyleSheet("color: gray; font-size: 12px;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timer_label)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        self.yes_btn = QPushButton("Да")
        self.yes_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.yes_btn.clicked.connect(self._on_yes)
        buttons_layout.addWidget(self.yes_btn)
        
        self.no_btn = QPushButton("Нет (удалить)")
        self.no_btn.setStyleSheet("padding: 8px;")
        self.no_btn.clicked.connect(self._on_no)
        buttons_layout.addWidget(self.no_btn)
        
        layout.addLayout(buttons_layout)
        
        # Таймер обратного отсчёта
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)
    
    def _on_timer(self):
        """Обновление таймера"""
        self._timeout -= 1
        if self._timeout <= 0:
            # Время вышло — автоматическое сохранение
            self._timer.stop()
            if self.preview_check.isChecked():
                self.save_with_previews.emit()
            else:
                self.save_without_previews.emit()
            self.accept()
        else:
            self.timer_label.setText(f"Автоматическое сохранение через: {self._timeout} сек")
    
    def _on_yes(self):
        """Кнопка Да"""
        self._timer.stop()
        if self.preview_check.isChecked():
            self.save_with_previews.emit()
        else:
            self.save_without_previews.emit()
        self.accept()
    
    def _on_no(self):
        """Кнопка Нет"""
        self._timer.stop()
        self.delete_history.emit()
        self.accept()
