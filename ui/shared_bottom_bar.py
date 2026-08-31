from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTextEdit,
                              QPushButton, QProgressBar, QLabel, QGroupBox, QApplication)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QTextCursor, QPalette, QColor


class PlainTextEdit(QTextEdit):
    """QTextEdit, который всегда вставляет plain text (без форматирования)"""

    def insertFromMimeData(self, source):
        """Переопределяем вставку: берём только текст, без форматирования"""
        if source.hasText():
            # Вставляем как plain text, сохраняя курсор
            cursor = self.textCursor()
            cursor.insertText(source.text())
        else:
            super().insertFromMimeData(source)


class SharedBottomBar(QWidget):
    """Общая нижняя панель с двумя блоками: левый (промпт) и правый (управление)"""

    prompt_submitted = pyqtSignal(str)
    prompt_changed = pyqtSignal(str)
    generation_stopped = pyqtSignal()
    blocked_action = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(5)

        # === ЛЕВЫЙ БЛОК: статус + прогресс + промпт ===
        left_group = QGroupBox()
        left_layout = QVBoxLayout(left_group)
        left_layout.setSpacing(5)

        # Статус
        self.status_label = QLabel("Готово")
        self.status_label.setWordWrap(False)
        left_layout.addWidget(self.status_label)

        # Прогрессбар
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m")
        left_layout.addWidget(self.progress_bar)

        # Поле промпта (Plain text only)
        self.prompt_edit = PlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "Введите промпт... (Enter - запустить, Shift+Enter - новая строка)"
        )
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setMinimumHeight(60)
        self.prompt_edit.installEventFilter(self)
        self.prompt_edit.textChanged.connect(self._on_text_changed)
        left_layout.addWidget(self.prompt_edit)

        main_layout.addWidget(left_group, 3)

        # === ПРАВЫЙ БЛОК: режим + индикаторы + кнопка ===
        right_group = QGroupBox()
        right_layout = QVBoxLayout(right_group)
        right_layout.setSpacing(5)

        # Строка 1: Индикатор режима
        self.mode_label = QLabel("㊘ Ресурсы свободны")
        self.mode_label.setStyleSheet("font-size: 12px; color: green; font-weight: bold;")
        right_layout.addWidget(self.mode_label)

        # Строка 2: Индикаторы (таймер + RAM + CPU) — В СТРОКУ
        indicators_layout = QHBoxLayout()
        indicators_layout.setSpacing(8)

        self.timer_label = QLabel("⏱ 00:00")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.timer_label)

        self.ram_label = QLabel("🖫 RAM: --")
        self.ram_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.ram_label)

        self.cpu_label = QLabel("🗲 CPU: --")
        self.cpu_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.cpu_label)

        right_layout.addLayout(indicators_layout)

        # Строка 3: Кнопка действия
        self.action_btn = QPushButton("▶ Генерация")
        self.action_btn.setMinimumHeight(60)
        self.action_btn.clicked.connect(self._on_action_clicked)
        self._action_state = "ready"  # ready, running, stopping
        right_layout.addWidget(self.action_btn)

        main_layout.addWidget(right_group, 1)

        # === Таймер ресурсов (обновление каждые 2 сек) ===
        self._resources_timer = QTimer()
        self._resources_timer.setInterval(2000)
        self._resources_timer.timeout.connect(self._update_resources)
        self._resources_timer.start()
        self._update_resources()

    # ─── Публичные методы ───
    def get_prompt(self):
        return self.prompt_edit.toPlainText().strip()

    def set_prompt(self, text):
        """Устанавливает промпт, не сбрасывая курсор если текст не изменился"""
        if self.prompt_edit.toPlainText() != text:
            self.prompt_edit.setPlainText(text)

    def set_status(self, text, color=None):
        self.status_label.setText(text)
        if color:
            self.status_label.setStyleSheet(f"color: {color};")
        else:
            self.status_label.setStyleSheet("")

    def set_progress(self, current, total, colorize=False):
        self.progress_bar.setRange(0, max(total, 0))
        self.progress_bar.setValue(current)

        # Подкраска на пределах — через палитру, чтобы не ломать нативный скин
        if colorize and total > 0:
            percent = current / total
            if percent >= 0.9:
                color = QColor("#d9534f")  # красный — критично
            elif percent >= 0.7:
                color = QColor("#f0ad4e")  # оранжевый — внимание
            else:
                color = QColor("#5cb85c")  # зелёный — норма
            pal = self.progress_bar.palette()
            pal.setColor(QPalette.ColorRole.Highlight, color)
            self.progress_bar.setPalette(pal)
        else:
            self.progress_bar.setPalette(QApplication.palette())

    def set_timer_display(self, seconds: int):
        """Устанавливает отображение таймера (в секундах)"""
        mins, secs = divmod(seconds, 60)
        self.timer_label.setText(f"⏱ {mins:02d}:{secs:02d}")

    def set_mode(self, mode: str, model_name: str = ""):
        """Устанавливает индикатор режима с именем модели."""
        if mode == "free":
            self.mode_label.setText("㊘ Ресурсы свободны")
            self.mode_label.setStyleSheet("font-size: 12px; color: green; font-weight: bold;")
        elif mode == "ollama":
            label = "㊘ Генерация Ollama"
            if model_name:
                label += f" · {model_name}"
            self.mode_label.setText(label)
            self.mode_label.setStyleSheet("font-size: 12px; color: orange; font-weight: bold;")
        elif mode == "diffusers":
            label = "㊘ Генерация Diffusers"
            if model_name:
                label += f" · {model_name}"
            self.mode_label.setText(label)
            self.mode_label.setStyleSheet("font-size: 12px; color: orange; font-weight: bold;")
        else:
            self.mode_label.setText(str(mode))
            self.mode_label.setStyleSheet("font-size: 12px; color: gray; font-weight: bold;")

    def set_running_state(self, running):
        """Устанавливает состояние генерации"""
        if self._action_state == "stopping":
            return
        if running:
            self._action_state = "running"
            self.action_btn.setText("⏹ Остановить")
            self.action_btn.setEnabled(True)
        else:
            self._action_state = "ready"
            self.action_btn.setText("▶ Генерация")
            self.action_btn.setEnabled(True)

    def set_stopping_state(self):
        """Устанавливает состояние завершения (после остановки)"""
        self._action_state = "stopping"
        self.action_btn.setText("Завершение...")
        self.action_btn.setEnabled(False)

    def reset_action_state(self):
        """Сбрасывает состояние кнопки в ready"""
        self._action_state = "ready"
        self.action_btn.setText("▶ Генерация")
        self.action_btn.setEnabled(True)

    # ─── Внутренние методы ───
    def _on_text_changed(self):
        self.prompt_changed.emit(self.prompt_edit.toPlainText())

    def _on_action_clicked(self):
        """Обработка клика по единой кнопке действия"""
        if self._action_state == "ready":
            text = self.get_prompt()
            if text:
                self.prompt_submitted.emit(text)
        elif self._action_state == "running":
            self.generation_stopped.emit()

    def _update_resources(self):
        """Обновляет индикаторы RAM и CPU"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            self.ram_label.setText(f"🖫 RAM: {used_gb:.1f}/{total_gb:.0f}G")
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_label.setText(f"🗲 CPU: {cpu_percent:.0f}%")
        except ImportError:
            self.ram_label.setText("RAM: N/A")
            self.cpu_label.setText("CPU: N/A")
        except Exception:
            self.ram_label.setText("RAM: err")
            self.cpu_label.setText("CPU: err")

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.prompt_edit and event.type() == QEvent.Type.KeyPress:
            from PyQt6.QtCore import Qt
            key_event = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    if self._action_state == "running":
                        return True
                    self._on_action_clicked()
                    return True
        return super().eventFilter(obj, event)
