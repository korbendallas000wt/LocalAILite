from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                              QPushButton, QFileDialog, QGraphicsView,
                              QGraphicsScene, QGraphicsPixmapItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from ui.tabs.diffusers_settings_panel import DiffusersSettingsPanel
from ui.dialogs.history_save_dialog import HistorySaveDialog
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
        self._was_stopped = False  # Флаг остановки генерации
        self._history_dialog_shown = False  # Флаг показа диалога сохранения истории
        self._last_step_on_stop = None  # Последний шаг при остановке
        
        # Буфер бегущей строки статуса
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
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
        self._set_status(
            f"💾 Чекпоинт загружен. Нажмите Запустить для продолжения "
            f"с шага {current_step}/{total_steps}",
            "#DAA520"
        )
    
    def get_bar_state(self) -> dict:
        return self._bar_state.copy()
    
    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())
    
    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())

    def _set_status(self, message: str, color: str = "#DAA520"):
        """Устанавливает статус с цветом.
        Цвета: gray=логи, #DAA520=статус, orange=предупреждение, red=ошибка, green=успех
        """
        self._bar_state["status"] = message
        self._bar_state["status_color"] = color
        self.state_changed.emit(self._bar_state.copy())
    def handle_prompt(self, prompt):
        """Запуск генерации"""
        negative_prompt = self.settings_panel.negative_prompt.toPlainText()
        params = self.settings_panel.get_params()
        self.settings_panel.save_settings()
        
        # Сбрасываем флаги
        self._history_dialog_shown = False
        self.update_bar_state("prompt", prompt)
        
        if not self.resource_manager.acquire_resource("diffusers"):
            self._set_status("⚠ Ресурс занят другой моделью", "orange")
            self.update_bar_state("is_running", False)
            return
        
        self.update_bar_state("is_running", True)
        self._set_status("Загрузка модели...", "#DAA520")
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
        """Логи процесса — серым цветом"""
        try:
            json.loads(line)
            return
        except (json.JSONDecodeError, ValueError):
            pass
        display = line if len(line) <= 80 else line[:77] + "..."
        self._set_status(display, "gray")
    
    def stop_generation(self):
        """Остановка генерации"""
        if self.worker:
            self._was_stopped = True
            
            # Находим последний шаг для single decode
            history_dir = self.worker.get_history_dir()
            if history_dir and os.path.exists(history_dir):
                pt_files = sorted([f for f in os.listdir(history_dir) if f.endswith('.pt')])
                if pt_files:
                    last_step_file = pt_files[-1]
                    try:
                        self._last_step_on_stop = int(last_step_file.replace('step_', '').replace('.pt', ''))
                    except ValueError:
                        self._last_step_on_stop = None
            
        # Переключаем кнопку в состояние "Завершение..."
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.set_stopping_state()
            self.worker.stop()
    
    def unload(self):
        """Выгрузка модуля — НЕ останавливает активную генерацию.
        Генерация продолжается в фоне, даже если вкладка неактивна.
        """
        # Намеренно не останавливаем worker — генерация идёт в QProcess
        # и не зависит от видимости вкладки
        pass
    
    def _on_step_updated(self, step, total, image_path):
        """Обновление прогресса и превью"""
        if os.path.exists(image_path):
            self._update_preview(image_path)
        
        self.update_bar_state("progress_current", step)
        self.update_bar_state("progress_total", total)
        self.step_updated.emit(step, total, image_path)
    
    def _on_generation_finished(self, final_path, seed):
        """Генерация завершена"""
        # Сбрасываем состояние генерации
        self.update_bar_state("is_running", False)
        # Освобождаем ресурс (КРИТИЧНО!)
        self.resource_manager.release_resource()
        
        # Определяем, была ли это остановка
        is_stopped = self._was_stopped
        self._was_stopped = False
        
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
        
        # При остановке — спрашиваем о сохранении чекпоинта
        if is_stopped and checkpoint_exists():
            reply = QMessageBox.question(
                self,
                "Сохранить прогресс?",
                "Сохранить прогресс генерации для продолжения позже?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                archive_checkpoint()
                self._set_status("💾 Чекпоинт сохранён", "green")
            else:
                delete_checkpoint()
                self._set_status("Генерация остановлена", "orange")
        
        # Показываем диалог сохранения истории (только один раз)
        if not self._history_dialog_shown:
            self._history_dialog_shown = True
            single_step = self._last_step_on_stop if is_stopped else None
            self._last_step_on_stop = None  # Сбрасываем
            self._show_history_save_dialog(is_stopped=is_stopped, single_step=single_step)
    
    def _on_error(self, error_msg):
        """Ошибка генерации"""
        # Освобождаем ресурс (КРИТИЧНО!)
        self.resource_manager.release_resource()
        
        self._resume_from_archive = False
        self._archive_checkpoint_file = None
        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")
        self.generation_error.emit(error_msg)
    
    def _on_status_message(self, message):
        """Статусы приложения — золотым цветом"""
        self._set_status(message, "#DAA520")
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
    
    
    def _show_history_save_dialog(self, is_stopped=False, single_step=None):
        """Показывает диалог сохранения истории"""
        history_dir = self.worker.get_history_dir() if self.worker else None
        
        if not history_dir or not os.path.exists(history_dir):
            self.update_bar_state("is_running", False)
            self.update_bar_state("status", "Готово")
            self.update_bar_state("progress_current", 0)
            self.generation_finished.emit()
            return
        
        dialog = HistorySaveDialog(is_stopped=is_stopped, parent=self)
        dialog.save_with_previews.connect(
            lambda: self._on_save_history(history_dir, create_previews=True, single_step=single_step)
        )
        dialog.save_without_previews.connect(
            lambda: self._on_save_history(history_dir, create_previews=False)
        )
        dialog.delete_history.connect(
            lambda: self._on_delete_history(history_dir)
        )
        dialog.exec()
    
    def _on_save_history(self, history_dir: str, create_previews: bool, single_step=None):
        """Обработка сохранения истории"""
        if create_previews:
            # Пока просто сообщаем, что превью будут созданы позже
            # В будущем здесь можно добавить вызов утилиты decode_history.py
            self._set_status("История сохранена (превью создаются отдельно)", "green")
        else:
            self.update_bar_state("is_running", False)
            self._set_status("История сохранена (без превью)", "green")
        
        self.update_bar_state("progress_current", 0)
        self.generation_finished.emit()
    
    def _on_delete_history(self, history_dir: str):
        """Обработка удаления истории"""
        try:
            history_manager.delete_history(history_dir)
            self.update_bar_state("is_running", False)
            self._set_status("История удалена", "green")
            self.update_bar_state("progress_current", 0)
            self.generation_finished.emit()
        except Exception as e:
            self._set_status(f"Ошибка удаления: {e}", "red")
    
