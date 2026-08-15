"""
Вкладка Visual editor для подготовки изображений.
Слева — превью, справа — настройки (ImagePrepPanel).
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFileDialog, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QMessageBox, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from ui.tabs.image_prep_panel import ImagePrepPanel
import os
import numpy as np
import subprocess


class GalleryNavigator(QWidget):
    """Навигатор галереи: 4 кнопки + счётчик"""
    
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Кнопка "В начало"
        self.first_btn = QPushButton()
        self.first_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.first_btn.setToolTip("Первое изображение")
        self.first_btn.setFixedSize(32, 32)
        layout.addWidget(self.first_btn)
        
        # Кнопка "Назад"
        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.prev_btn.setToolTip("Предыдущее изображение")
        self.prev_btn.setFixedSize(32, 32)
        layout.addWidget(self.prev_btn)
        
        # Счётчик "1/10"
        self.counter_label = QLabel("0/0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_label.setMinimumWidth(60)
        layout.addWidget(self.counter_label)
        
        # Кнопка "Вперёд"
        self.next_btn = QPushButton()
        self.next_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaSeekForward))
        self.next_btn.setToolTip("Следующее изображение")
        self.next_btn.setFixedSize(32, 32)
        layout.addWidget(self.next_btn)
        
        # Кнопка "В конец"
        self.last_btn = QPushButton()
        self.last_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaSkipForward))
        self.last_btn.setToolTip("Последнее изображение")
        self.last_btn.setFixedSize(32, 32)
        layout.addWidget(self.last_btn)


class ImagePrepTab(QWidget):
    """Вкладка Visual editor с состоянием для SharedBottomBar"""

    # Универсальный сигнал для MainWindow
    state_changed = pyqtSignal(dict)

    def __init__(self, config, resource_manager):
        super().__init__()
        self.config = config
        self.resource_manager = resource_manager
        self.current_image = None      # PIL.Image исходника
        self.processed_image = None    # PIL.Image после обработки
        self.original_path = ""        # Путь к исходнику

        # Состояние для SharedBottomBar
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
            "is_running": False
        }

        layout = QHBoxLayout(self)

        # === Левая часть: превью изображения + навигатор ===
        left_layout = QVBoxLayout()
        self.image_view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.image_view.setScene(self.scene)
        left_layout.addWidget(self.image_view, 1)

        # Навигатор галереи
        self.gallery_navigator = GalleryNavigator()
        left_layout.addWidget(self.gallery_navigator)

        layout.addLayout(left_layout, 3)

        # === Правая часть: настройки ===
        self.settings_panel = ImagePrepPanel()
        layout.addWidget(self.settings_panel, 1)

        # === Подключение сигналов панели ===
        self.settings_panel.open_btn.clicked.connect(self._on_open_clicked)
        self.settings_panel.process_btn.clicked.connect(self._on_process_requested)
        self.settings_panel.save_btn.clicked.connect(self._on_save_clicked)

        # Восстанавливаем настройки из конфига
        self._restore_settings()

    def _restore_settings(self):
        """Восстанавливает последние настройки из конфига"""
        preset_index = int(self.config.get("image_prep/preset", 0))
        if 0 <= preset_index < self.settings_panel.preset_combo.count():
            self.settings_panel.preset_combo.setCurrentIndex(preset_index)

        crop_mode = self.config.get("image_prep/crop_mode", "center")
        if crop_mode == "letterbox":
            self.settings_panel.crop_letterbox_radio.setChecked(True)
        elif crop_mode == "stretch":
            self.settings_panel.crop_stretch_radio.setChecked(True)
        else:
            self.settings_panel.crop_center_radio.setChecked(True)

    def _on_open_clicked(self):
        """Открывает диалог выбора файла"""
        from PyQt6.QtWidgets import QFileDialog
        last_path = self.config.get("image_prep/last_path", "")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение",
            last_path,
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.tiff);;Все файлы (*)"
        )
        if file_path:
            self.config.set("image_prep/last_path", os.path.dirname(file_path))
            self._load_image(file_path)

    def _load_image(self, file_path):
        """Загружает изображение и показывает превью"""
        from core.image_processor import load_image, get_image_info
        try:
            self.current_image = load_image(file_path)
            self.original_path = file_path
            info = get_image_info(self.current_image, file_path)

            # Показываем превью
            self._update_preview(self.current_image)

            # Активируем кнопку обработки
            self.settings_panel.process_btn.setEnabled(True)
            self.settings_panel.save_btn.setEnabled(False)
            self.processed_image = None

            # Обновляем статус
            self._set_status(
                f"Загружено: {os.path.basename(file_path)} ({info['width']}×{info['height']}, {info['format']})",
            "#DAA520"
        )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить изображение:\n{e}")

    def _on_process_requested(self):
        """Обрабатывает изображение с выбранными параметрами"""
        if self.current_image is None:
            return

        from core.image_processor import process_image
        # Получаем параметры
        target_width, target_height = self.settings_panel.get_target_size()
        crop_mode = self.settings_panel.get_crop_mode()

        try:
            self.processed_image = process_image(
                self.current_image, target_width, target_height, crop_mode
            )
            # Показываем результат
            self._update_preview(self.processed_image)

            # Активируем сохранение
            self.settings_panel.save_btn.setEnabled(True)

            # Сохраняем настройки
            self.config.set("image_prep/preset", self.settings_panel.preset_combo.currentIndex())
            self.config.set("image_prep/crop_mode", crop_mode)

            self._set_status(
                f"Обработано: {self.processed_image.width}×{self.processed_image.height}",
            "#DAA520"
        )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обработать изображение:\n{e}")

    def _on_save_clicked(self):
        """Сохраняет обработанное изображение"""
        if self.processed_image is None:
            return

        from core.image_processor import save_processed_image
        output_dir = self.config.get_init_images_dir()

        try:
            saved_path = save_processed_image(
                self.processed_image, output_dir, self.original_path
            )
            self._set_status(f"Сохранено: {os.path.basename(saved_path)}", "green")
            QMessageBox.information(self, "Готово", f"Изображение сохранено:\n{saved_path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")

    def _update_preview(self, image):
        """Конвертирует PIL.Image в QPixmap и показывает в QGraphicsView"""
        # PIL → numpy → QImage → QPixmap
        image_np = np.array(image)
        height, width, channels = image_np.shape
        bytes_per_line = channels * width
        q_image = QImage(image_np.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        self.scene.clear()
        item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(item)
        self.image_view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)

    # === Методы для совместимости с MainWindow ===
    def get_bar_state(self) -> dict:
        return self._bar_state.copy()

    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())

    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())


    def _set_status(self, message: str, color: str = "#DAA520"):
        """Устанавливает статус с цветом"""
        self._bar_state["status"] = message
        self._bar_state["status_color"] = color
        self.state_changed.emit(self._bar_state.copy())
    def unload(self):
        """Выгрузка модуля (для ResourceManager)"""
        pass
