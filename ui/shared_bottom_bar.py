from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTextEdit,
                             QPushButton, QProgressBar, QLabel, QGroupBox,
                             QRadioButton, QButtonGroup)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer


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
        
        # Поле промпта
        self.prompt_edit = QTextEdit()
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
        
        # Радиокнопки режима (теперь кликабельные)
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup()
        self.ollama_radio = QRadioButton("Ollama")
        self.ollama_radio.setChecked(True)
        self.diffusers_radio = QRadioButton("Diffusers")
        self.mode_group.addButton(self.ollama_radio)
        self.mode_group.addButton(self.diffusers_radio)
        mode_layout.addWidget(self.ollama_radio)
        mode_layout.addWidget(self.diffusers_radio)
        right_layout.addLayout(mode_layout)
        
        # Индикатор ресурса (новый)
        self.resource_label = QLabel("🟢 Свободно")
        self.resource_label.setFixedWidth(120)
        self.resource_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.resource_label.setStyleSheet("font-size: 11px; color: green;")
        right_layout.addWidget(self.resource_label)
        
        # Индикаторы (таймер + RAM + CPU) — В СТРОКУ
        indicators_layout = QHBoxLayout()
        indicators_layout.setSpacing(8)
        
        self.timer_label = QLabel("⏱ 00:00")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.timer_label)
        
        self.ram_label = QLabel("RAM: --")
        self.ram_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.ram_label)
        
        self.cpu_label = QLabel("CPU: --")
        self.cpu_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        indicators_layout.addWidget(self.cpu_label)
        
        right_layout.addLayout(indicators_layout)
        
        # Кнопка запуска/остановки
        # Единая кнопка с тремя состояниями: Генерация / Остановить / Завершение...
        self.action_btn = QPushButton("▶ Генерация")
        self.action_btn.setMinimumHeight(60)
        self.action_btn.clicked.connect(self._on_action_clicked)
        self._action_state = "ready"  # ready, running, stopping
        right_layout.addWidget(self.action_btn)
        
        main_layout.addWidget(right_group, 1)
        
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
        self._update_resources()
    
    # ─── Публичные методы ───
    
    def get_prompt(self):
        return self.prompt_edit.toPlainText().strip()
    
    def set_prompt(self, text):
        self.prompt_edit.setPlainText(text)
    
    def set_status(self, text, color=None):
        self.status_label.setText(text)
        if color:
            self.status_label.setStyleSheet(f"color: {color};")
        else:
            self.status_label.setStyleSheet("")
    
    def set_progress(self, current, total):
        self.progress_bar.setRange(0, max(total, 0))
        self.progress_bar.setValue(current)
    
    def start_timer(self):
        """Запускает таймер только если ещё не запущен"""
        if not self._is_running:
            import time
            self._start_time = time.time()
            self._is_running = True
            self._timer.start()
    
    def stop_timer(self):
        """Останавливает таймер"""
        self._is_running = False
        self._timer.stop()
    
    def set_running_state(self, running):
        """Устанавливает состояние генерации"""
        if running:
            self.start_timer()
            self._action_state = "running"
            self.action_btn.setText("⏹ Остановить")
            self.action_btn.setEnabled(True)
            self.prompt_edit.setEnabled(False)
        else:
            self.stop_timer()
            self._action_state = "ready"
            self.action_btn.setText("▶ Генерация")
            self.action_btn.setEnabled(True)
            self.prompt_edit.setEnabled(True)

    def set_stopping_state(self):
        """Устанавливает состояние завершения (после остановки)"""
        self._action_state = "stopping"
        self.action_btn.setText("Завершение...")
        self.action_btn.setEnabled(False)
    
    def set_resource_state(self, busy: bool, owner: str = None):
        """Устанавливает состояние ресурса"""
        if busy:
            self.resource_label.setText(f"🔴 {owner}")
            self.resource_label.setStyleSheet("font-size: 11px; color: red;")
            # Не блокируем кнопку, если она в состоянии stopping
            if self._action_state != "stopping":
                self.action_btn.setEnabled(False)
        else:
            self.resource_label.setText("🟢 Свободно")
            self.resource_label.setStyleSheet("font-size: 11px; color: green;")
            # Разблокируем только если не в состоянии stopping
            if self._action_state != "stopping":
                self.action_btn.setEnabled(True)
    
    # ─── Внутренние методы ───
    
    def _on_text_changed(self):
        self.prompt_changed.emit(self.prompt_edit.toPlainText())
    
    def _on_action_clicked(self):
        """Обработка клика по единой кнопке действия"""
        if self._action_state == "ready":
            # Запуск генерации
            text = self.get_prompt()
            if text:
                self.prompt_submitted.emit(text)
        elif self._action_state == "running":
            # Остановка генерации
            self.generation_stopped.emit()
        # Состояние "stopping" — кнопка неактивна, клик игнорируется

    
    def _update_timer(self):
        """Обновляет отображение таймера"""
        if self._is_running and self._start_time:
            import time
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            self.timer_label.setText(f"⏱ {mins:02d}:{secs:02d}")
    
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
                    self._on_action_clicked()
                    return True
        return super().eventFilter(obj, event)
