from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                              QPushButton, QFileDialog, QGraphicsView,
                              QGraphicsScene, QGraphicsPixmapItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap
from ui.tabs.diffusers_settings_panel import DiffusersSettingsPanel
from ui.dialogs.history_save_dialog import HistorySaveDialog
from core.diffusers_worker import DiffusersWorker
from core import history_manager
from core.checkpoint_manager import load_step_metadata
import os
import json
import subprocess
import time

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
        self._resume_from_history = False
        self._history_dir_for_resume = None
        self._step_file_for_resume = None
        self._start_step_for_resume = 0
        self._was_stopped = False  # Флаг остановки генерации
        self._history_dialog_shown = False  # Флаг показа диалога сохранения истории
        self._last_step_on_stop = None  # Последний шаг при остановке

        import time
        self._generation_timer = QTimer()
        self._generation_timer.setInterval(1000)
        self._generation_timer.timeout.connect(self._update_generation_time)
        self._generation_start_time = None
        
        # Буфер бегущей строки статуса
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
        "elapsed_seconds": 0,
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
        self.settings_panel.checkpoint_selected.connect(self._on_checkpoint_selected)
        self.settings_panel.init_image_selected.connect(self._on_init_image_selected)
        self.settings_panel.mode_changed.connect(self._on_mode_changed)
        self._on_mode_changed("create")
                    
    def _on_steps_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())
    
    def _on_checkpoint_selected(self, history_dir: str, step_filename: str):
        """Обработка выбора папки истории и конкретного шага"""
        # Загружаем метаданные конкретного шага (содержат ВСЕ параметры генерации)
        step_json_file = step_filename.replace(".pt", ".json")
        step_meta = load_step_metadata(history_dir, step_json_file)
        if not step_meta:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить {step_json_file}")
            return
        
        # Нормализуем метаданные для set_params_from_checkpoint
        normalized = {
            "prompt": step_meta.get("prompt", ""),
            "negative_prompt": step_meta.get("negative_prompt", ""),
            "model": step_meta.get("model", ""),
            "scheduler": step_meta.get("scheduler", ""),
            "total_steps": step_meta.get("steps", 0),
            "cfg": step_meta.get("cfg", 0),
            "seed": step_meta.get("seed", -1),
            "width": step_meta.get("width", 1024),
            "height": step_meta.get("height", 1024)
        }
        
        # Заполняем поля настроек
        self.settings_panel.set_params_from_checkpoint(normalized)
        
        # Сохраняем информацию для resume
        self._resume_from_history = True
        self._history_dir_for_resume = history_dir
        self._step_file_for_resume = step_filename
        self._start_step_for_resume = step_meta.get("step", 0)
        
        # Обновляем состояние UI
        total_steps = step_meta.get("steps", 0)
        current_step = step_meta.get("step", 0)
        self._bar_state["prompt"] = step_meta.get("prompt", "")
        self._bar_state["progress_current"] = current_step
        self._bar_state["progress_total"] = total_steps
        
        self._set_status(
            f"💾 История загружена. Нажмите Запустить для продолжения "
            f"с шага {current_step}/{total_steps}",
            "#DAA520"
        )

    def _on_init_image_selected(self, filename: str):
        """Обработка выбора init-картинки"""
        self._set_status(f"🖼 Выбрана картинка: {filename}", "#DAA520")
    
    def _on_mode_changed(self, mode: str):
        """Обработка смены режима"""
        if mode == "create":
            # Strength, Чекпоинт, Картинка — серые
            self.settings_panel.set_field_enabled("strength", False)
            self.settings_panel.set_field_enabled("checkpoint", False)
            self.settings_panel.set_field_enabled("init_image", False)
            self._set_status("Режим: Создание с нуля", "green")
        
        elif mode == "resume":
            # Strength, Картинка — серые; Чекпоинт — активен
            self.settings_panel.set_field_enabled("strength", False)
            self.settings_panel.set_field_enabled("checkpoint", True)
            self.settings_panel.set_field_enabled("init_image", False)
            self._set_status("Режим: Продолжение из чекпоинта", "#DAA520")
        
        elif mode == "edit":
            # Чекпоинт — серый; Strength, Картинка — активны
            self.settings_panel.set_field_enabled("strength", True)
            self.settings_panel.set_field_enabled("checkpoint", False)
            self.settings_panel.set_field_enabled("init_image", True)
            self._set_status("Режим: Изменение картинки (img2img)", "#DAA520")
    
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
    def _update_generation_time(self):
        """Обновляет elapsed_seconds каждую секунду"""
        if self._generation_start_time:
            elapsed = int(time.time() - self._generation_start_time)
            self.update_bar_state("elapsed_seconds", elapsed)

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
        self.update_bar_state("is_running", True)
        self._generation_start_time = time.time()
        self._generation_timer.start()
        self._set_status("Загрузка модели...", "#DAA520")
        self.update_bar_state("progress_total", params["steps"])
        
        resume = False
        history_dir = None
        step_file = None
        start_step = 0
        
        if self._resume_from_history:
            resume = True
            history_dir = self._history_dir_for_resume
            step_file = self._step_file_for_resume
            start_step = self._start_step_for_resume
            # При resume — НЕ сбрасываем progress_current
            self.update_bar_state("progress_current", start_step)
            # Сбрасываем флаги
            self._resume_from_history = False
            self._history_dir_for_resume = None
            self._step_file_for_resume = None
            self._start_step_for_resume = 0
        else:
            # При обычной генерации — сбрасываем progress_current
            self.update_bar_state("progress_current", 0)
        
        self._start_generation(prompt, negative_prompt, params,
                               resume=resume, history_dir=history_dir,
                               step_file=step_file, start_step=start_step)
    
    def _start_generation(self, prompt, negative_prompt, params,
                          resume=False, history_dir=None, step_file=None, start_step=0):
        """Запускает генерацию (новую или продолжение)"""
        self.worker = DiffusersWorker(self.config)
        self.worker.step_updated.connect(self._on_step_updated)
        self.worker.generation_finished.connect(self._on_generation_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.status_message.connect(self._on_status_message)
        self.worker.log_line.connect(self._on_log_line)
        
        self.worker.start(prompt, negative_prompt, params,
                          resume=resume, history_dir=history_dir,
                          step_file=step_file, start_step=start_step)
        
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
        self._generation_timer.stop()
        self._generation_start_time = None
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
        if self.worker:
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
        # Останавливаем таймер
        self._generation_timer.stop()
        self._generation_start_time = None
        
        # Сбрасываем состояние генерации
        self.update_bar_state("is_running", False)
        
        # Определяем, была ли это остановка
        is_stopped = self._was_stopped
        self._was_stopped = False
        
        if final_path and os.path.exists(final_path):
            self._update_preview(final_path)
        
        
                
        # Обновляем список чекпоинтов
                
        # При остановке — спрашиваем о сохранении чекпоинта
                
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
        
        self._resume_from_history = False
        self._history_dir_for_resume = None
        self._step_file_for_resume = None
        self._start_step_for_resume = 0
        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")
        self.generation_error.emit(error_msg)
    
    def _on_status_message(self, message):
        """Статусы приложения — золотым цветом"""
        self._set_status(message, "#DAA520")
        self.status_message.emit(message)
    
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
            self.resource_manager.release_resource()
            from ui.main_window import MainWindow
            main_window = self.window()
            if isinstance(main_window, MainWindow):
                main_window.shared_bar.reset_action_state()
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
    
        # Освобождаем ресурс и сбрасываем кнопку
        self.resource_manager.release_resource()
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def _on_delete_history(self, history_dir: str):
        """Обработка удаления истории"""
        try:
            history_manager.delete_history(history_dir)
            self.update_bar_state("is_running", False)
            self._set_status("История удалена", "green")
            self.update_bar_state("progress_current", 0)
            # Освобождаем ресурс
            self.resource_manager.release_resource()
            
            # Сбрасываем кнопку в ready
            from ui.main_window import MainWindow
            main_window = self.window()
            if isinstance(main_window, MainWindow):
                main_window.shared_bar.reset_action_state()
            
            self.generation_finished.emit()
        except Exception as e:
            self._set_status(f"Ошибка удаления: {e}", "red")
            # Освобождаем ресурс даже при ошибке
            self.resource_manager.release_resource()
    
