from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QPushButton, QFileDialog, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from ui.tabs.diffusers_settings_panel import DiffusersSettingsPanel
from core.diffusers_worker import DiffusersWorker
from core import history_manager
from core.checkpoint_manager import (
    archive_checkpoint, checkpoint_exists, delete_checkpoint, load_archived_metadata
)
import os
import json
import subprocess

class DiffusersTab(QWidget):
    """Вкладка Diffusers с состоянием для SharedBottomBar"""
    
    # Сигналы для внутреннего использования
    generation_started = pyqtSignal()
    generation_finished = pyqtSignal()
    generation_error = pyqtSignal(str)
    step_updated = pyqtSignal(int, int, str)
    status_message = pyqtSignal(str)
    
    # Универсальный сигнал для MainWindow
    state_changed = pyqtSignal(dict)
    
    def __init__(self, config, resource_manager):
        super().__init__()
        self.config = config
        self.resource_manager = resource_manager
        self.worker = None
        self._resume_from_archive = False
        self._archive_checkpoint_file = None
        
        # Буфер бегущей строки статуса
        self._status_buffer = ""
        self._status_buffer_max_length = 150
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "is_running": False
        }
        
        layout = QHBoxLayout(self)
        
        # Левая часть: превью изображения
        left_layout = QVBoxLayout()
        self.image_view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.image_view.setScene(self.scene)
        self.image_view.viewport().setContentsMargins(10, 10, 10, 10)
        self.image_view.setBackgroundBrush(Qt.GlobalColor.darkGray)
        left_layout.addWidget(self.image_view, 1)
        
        self.open_folder_btn = QPushButton("📂 Открыть папку")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        left_layout.addWidget(self.open_folder_btn)
        
        layout.addLayout(left_layout, 3)
        
        # Правая часть: настройки
        self.settings_panel = DiffusersSettingsPanel(self.config)
        layout.addWidget(self.settings_panel, 1)
        
        self.settings_panel.steps_spin.valueChanged.connect(self._on_steps_changed)
        self.settings_panel.load_checkpoint_btn.clicked.connect(self._on_load_checkpoint)
        self.settings_panel.load_checkpoints_list()
        
    
    def _on_steps_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())
    
    def _on_load_checkpoint(self):
        """Загружает метаданные выбранного архивного чекпоинта"""
        filename = self.settings_panel.get_selected_checkpoint()
        if not filename:
            QMessageBox.information(
                self, "Чекпоинт",
                "Выберите чекпоинт из списка"
            )
            return
        
        json_data = load_archived_metadata(filename)
        if not json_data:
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить чекпоинт")
            return
        
        self.settings_panel.set_params_from_checkpoint(json_data)
        self._resume_from_archive = True
        self._archive_checkpoint_file = filename
        
        current_step = json_data.get("current_step", 0)
        total_steps = json_data.get("total_steps", 0)
        
        self._bar_state["prompt"] = json_data.get("prompt", "")
        self._bar_state["progress_current"] = current_step
        self._bar_state["progress_total"] = total_steps
        self._bar_state["status"] = (
            f"💾 Чекпоинт загружен. Нажмите Запустить для продолжения "
            f"с шага {current_step}/{total_steps}"
        )
        self.state_changed.emit(self._bar_state.copy())
    
    def get_bar_state(self) -> dict:
        return self._bar_state.copy()
    
    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())
    
    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())
    
    def _append_to_status_buffer(self, message: str):
        """Добавляет сообщение в буфер бегущей строки (новые слева)"""
        if self._status_buffer:
            self._status_buffer = f"{message} · {self._status_buffer}"
        else:
            self._status_buffer = message
        
        # Обрезаем до максимальной длины
        if len(self._status_buffer) > self._status_buffer_max_length:
            self._status_buffer = self._status_buffer[:self._status_buffer_max_length]
        
        # Обновляем статус
        self.update_bar_state("status", self._status_buffer)
    
    def handle_prompt(self, prompt):
        """Запуск генерации"""
        negative_prompt = self.settings_panel.negative_prompt.toPlainText()
        params = self.settings_panel.get_params()
        
        self.settings_panel.save_settings()
        
        # Сбрасываем буфер бегущей строки
        self._status_buffer = ""
        
        self.update_bar_state("prompt", prompt)
        if not self.resource_manager.acquire_resource("diffusers"):
            self.update_bar_state("status", "⚠ Ресурс занят другой моделью", "red")
            self.update_bar_state("is_running", False)
            return
        self.update_bar_state("is_running", True)
        self.update_bar_state("status", "Загрузка модели...")
        self.update_bar_state("progress_total", params["steps"])
        self.update_bar_state("progress_current", 0)
        
        resume = False
        checkpoint_file = None
        
        if self._resume_from_archive:
            resume = True
            checkpoint_file = self._archive_checkpoint_file
            self._resume_from_archive = False
            self._archive_checkpoint_file = None
        else:
            # Проверяем наличие активного чекпоинта
            checkpoint_info = self._check_checkpoint()
            if checkpoint_info:
                msg = (
                    f"Найден чекпоинт от предыдущей генерации:\n\n"
                    f"Промпт: {checkpoint_info['prompt'][:60]}{'...' if len(checkpoint_info['prompt']) > 60 else ''}\n"
                    f"Модель: {checkpoint_info['model']}\n"
                    f"Прогресс: {checkpoint_info['current_step']}/{checkpoint_info['total_steps']} шагов\n"
                    f"Размер: {checkpoint_info['width']}×{checkpoint_info['height']}\n"
                    f"Seed: {checkpoint_info['seed']}\n\n"
                    f"Продолжить генерацию или начать заново?"
                )
                reply = QMessageBox.question(
                    self,
                    "Найден чекпоинт",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                resume = (reply == QMessageBox.StandardButton.Yes)
        
        self._start_generation(prompt, negative_prompt, params,
                               resume=resume, checkpoint_file=checkpoint_file)
    
    def _start_generation(self, prompt, negative_prompt, params,
                          resume=False, checkpoint_file=None):
        """Запускает генерацию (новую или продолжение)"""
        self.worker = DiffusersWorker(self.config)
        self.worker.step_updated.connect(self._on_step_updated)
        self.worker.generation_finished.connect(self._on_generation_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.status_message.connect(self._on_status_message)
        self.worker.log_line.connect(self._on_log_line)
        
        self.worker.start(prompt, negative_prompt, params,
                          resume=resume, checkpoint_file=checkpoint_file)
        
        self.generation_started.emit()
    
    def _on_log_line(self, line: str):
        """Добавляет plain text строку в бегущую строку статуса.
        JSON-строки игнорируются — их обрабатывает _on_status_message()"""
        # Проверяем, является ли строка JSON
        try:
            json.loads(line)
            # Это JSON — не добавляем в буфер
            return
        except (json.JSONDecodeError, ValueError):
            # Это plain text — добавляем в буфер
            pass
        
        self._append_to_status_buffer(line)
    
    def stop_generation(self):
        """Остановка генерации"""
        if self.worker:
            self.worker.stop()
            self._resume_from_archive = False
            self._archive_checkpoint_file = None
            
            # Спрашиваем пользователя о сохранении чекпоинта
            if checkpoint_exists():
                reply = QMessageBox.question(
                    self,
                    "Сохранить прогресс?",
                    "Сохранить прогресс генерации для продолжения позже?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    archive_checkpoint()
                    self.update_bar_state("status", "💾 Чекпоинт сохранён")
                else:
                    delete_checkpoint()
                    self.update_bar_state("status", "Генерация остановлена")
            else:
                self.update_bar_state("status", "Генерация остановлена")
    
    def unload(self):
        """Выгрузка модели"""
        if self.worker:
            self.worker.stop()
            self.worker = None
    
    def _on_step_updated(self, step, total, image_path):
        """Обновление прогресса и превью"""
        if os.path.exists(image_path):
            self._update_preview(image_path)
        
        self.update_bar_state("progress_current", step)
        self.update_bar_state("progress_total", total)
        
        self.step_updated.emit(step, total, image_path)
    
    def _on_generation_finished(self, final_path, seed):
        """Генерация завершена"""
        if final_path and os.path.exists(final_path):
            self._update_preview(final_path)
        
        self._resume_from_archive = False
        
        # Если был resume из архива — удаляем исходный архивный чекпоинт
        if self._archive_checkpoint_file:
            try:
                checkpoint_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "checkpoints"
                )
                json_path = os.path.join(checkpoint_dir, self._archive_checkpoint_file)
                pt_path = json_path.replace('.json', '.pt')
                
                if os.path.exists(json_path):
                    os.remove(json_path)
                if os.path.exists(pt_path):
                    os.remove(pt_path)
            except Exception:
                pass
            self._archive_checkpoint_file = None
        
        # Обновляем список чекпоинтов
        self.settings_panel.load_checkpoints_list()
        
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", "Готово")
        self.update_bar_state("progress_current", 0)
        
        self.generation_finished.emit()
    
    def _on_error(self, error_msg):
        """Ошибка генерации"""
        self._resume_from_archive = False
        self._archive_checkpoint_file = None
        
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", f"Ошибка: {error_msg}")
        
        self.generation_error.emit(error_msg)
    
    def _on_status_message(self, message):
        """Добавляет статусное сообщение в бегущую строку"""
        self._append_to_status_buffer(message)
        
        # Эмитим сигнал для совместимости
        self.status_message.emit(message)
    
    def _check_checkpoint(self):
        """Проверяет наличие активного чекпоинта"""
        checkpoint_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "checkpoints"
        )
        json_path = os.path.join(checkpoint_dir, "checkpoint.json")
        pt_path = os.path.join(checkpoint_dir, "checkpoint.pt")
        
        if not os.path.exists(json_path) or not os.path.exists(pt_path):
            return None
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "prompt": data.get("prompt", ""),
                "model": os.path.basename(data.get("model", "")),
                "current_step": data.get("current_step", 0),
                "total_steps": data.get("total_steps", 0),
                "seed": data.get("seed", -1),
                "width": data.get("width", 0),
                "height": data.get("height", 0)
            }
        except Exception:
            return None
    
    def _update_preview(self, image_path):
        """Загружает изображение в QGraphicsView"""
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.scene.clear()
            item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(item)
            self.image_view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
    
    def _open_output_folder(self):
        """Открывает папку с сохранёнными изображениями"""
        output_dir = self.config.get_sdxl_output_dir()
        if os.path.exists(output_dir):
            subprocess.run(['xdg-open', output_dir])
