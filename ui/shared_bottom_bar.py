from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTextEdit,
                             QPushButton, QProgressBar, QLabel)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer


class SharedBottomBar(QWidget):
    """Общая нижняя панель с полем ввода промпта, прогрессбаром и статусом"""

    prompt_submitted = pyqtSignal(str)
    prompt_changed = pyqtSignal(str)
    generation_stopped = pyqtSignal()
    blocked_action = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # === Бегущая строка статуса ===
        self.status_label = QLabel("Готово")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.status_label.setWordWrap(False)
        self.status_label.setMinimumHeight(20)
        self.status_label.setMaximumHeight(24)
        main_layout.addWidget(self.status_label)

        # === Верхний ряд: Прогрессбар + правый контейнер ===
        progress_row = QWidget()
        progress_row.setMinimumHeight(10)  # Высота = высоте кнопок
        progress_row_layout = QHBoxLayout(progress_row)
        progress_row_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m")  # Показываем "15/30" вместо "50%"
        progress_row_layout.addWidget(self.progress_bar, 3)  # stretch=3

        right_container = QWidget()
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.end_label = QLabel("")
        self.end_label.setFixedWidth(80)
        self.end_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.end_label.setStyleSheet("font-size: 11px; color: red;")
        right_layout.addWidget(self.end_label)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFixedWidth(50)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.timer_label.setStyleSheet("font-size: 11px; color: green;")
        right_layout.addWidget(self.timer_label)
        
        # Индикаторы ресурсов
        self.ram_label = QLabel("RAM: --")
        self.ram_label.setFixedWidth(90)
        self.ram_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ram_label.setStyleSheet("font-size: 11px; color: blue;")
        right_layout.addWidget(self.ram_label)
        
        self.cpu_label = QLabel("CPU: --")
        self.cpu_label.setFixedWidth(70)
        self.cpu_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cpu_label.setStyleSheet("font-size: 11px; color: purple;")
        right_layout.addWidget(self.cpu_label)

        progress_row_layout.addWidget(right_container, 1)  # stretch=1

        main_layout.addWidget(progress_row)

        # === Нижняя часть: Поле ввода и кнопки ===
        bottom_layout = QHBoxLayout()

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText(
            "Введите промпт... (Enter - запустить, Shift+Enter - новая строка)"
        )
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setMinimumHeight(60)
        self.prompt_edit.installEventFilter(self)
        self.prompt_edit.textChanged.connect(self._on_text_changed)
        bottom_layout.addWidget(self.prompt_edit, 3)  # stretch=3

        self.run_btn = QPushButton("Запустить")
        self.run_btn.setMinimumHeight(60)
        self.run_btn.clicked.connect(self._on_run_clicked)
        bottom_layout.addWidget(self.run_btn, 1)  # stretch=1

        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setMinimumHeight(60)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        bottom_layout.addWidget(self.stop_btn, 1)  # stretch=1

        main_layout.addLayout(bottom_layout)

        # === Таймер ===
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_timer)
        self._start_time = None
        self._is_running = False
        
        # === Таймер ресурсов (обновление каждые 2 сек) ===
        self._resources_timer = QTimer()
        self._resources_timer.setInterval(2000)
        self._resources_timer.timeout.connect(self._update_resources)
        self._resources_timer.start()
        self._update_resources()  # Сразу показать

    # ─── Публичные методы ───

    def get_prompt(self):
        return self.prompt_edit.toPlainText().strip()

    def set_prompt(self, text):
        self.prompt_edit.setPlainText(text)

    def set_status(self, text, color=None):
        if color:
            self.status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        else:
            self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.status_label.setText(text)

    def set_progress(self, current, total):
        self.progress_bar.setRange(0, max(total, 0))
        self.progress_bar.setValue(current)

    def set_end_label(self, text):
        self.end_label.setText(text)

    def start_timer(self):
        import time
        self._start_time = time.time()
        self._is_running = True
        self._timer.start()

    def stop_timer(self):
        self._is_running = False
        self._timer.stop()

    def set_running_state(self, running):
        self.run_btn.setVisible(not running)
        self.stop_btn.setVisible(running)
        self.prompt_edit.setEnabled(not running)

    # ─── Внутренние методы ───

    def _on_text_changed(self):
        self.prompt_changed.emit(self.prompt_edit.toPlainText())

    def _on_run_clicked(self):
        text = self.get_prompt()
        if text:
            self.prompt_submitted.emit(text)

    def _on_stop_clicked(self):
        self.generation_stopped.emit()

    def _update_timer(self):
        if self._is_running and self._start_time:
            import time
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            self.timer_label.setText(f"{mins:02d}:{secs:02d}")
    
    def _update_resources(self):
        """Обновляет индикаторы RAM и CPU"""
        try:
            import psutil
            # RAM
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            self.ram_label.setText(f"RAM: {used_gb:.1f}/{total_gb:.0f}G")
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_label.setText(f"CPU: {cpu_percent:.0f}%")
            
            # Цвета по нагрузке
            if cpu_percent > 80:
                self.cpu_label.setStyleSheet("font-size: 11px; color: red;")
            elif cpu_percent > 50:
                self.cpu_label.setStyleSheet("font-size: 11px; color: orange;")
            else:
                self.cpu_label.setStyleSheet("font-size: 11px; color: purple;")
        except ImportError:
            self.ram_label.setText("RAM: N/A")
            self.cpu_label.setText("CPU: N/A")
        except Exception as e:
            self.ram_label.setText(f"RAM: err")
            self.cpu_label.setText(f"CPU: err")

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.prompt_edit and event.type() == QEvent.Type.KeyPress:
            from PyQt6.QtCore import Qt
            key_event = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._on_run_clicked()
                    return True
        return super().eventFilter(obj, event)
