from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox, QMessageBox
from PyQt6.QtCore import Qt, QTimer
from ui.dialogs.settings.paths_settings_widget import PathsSettingsWidget
from ui.dialogs.settings.diffusers_settings_widget import DiffusersSettingsWidget
from ui.dialogs.settings.resources_settings_widget import ResourcesSettingsWidget

class SettingsDialog(QDialog):
    """Главный диалог настроек приложения"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки")
        self.setMinimumSize(500, 500)
        layout = QVBoxLayout(self)

        # Вкладки
        self.tabs = QTabWidget()

        # Вкладка Общие (пути)
        self.paths_widget = PathsSettingsWidget(config)
        self.tabs.addTab(self.paths_widget, "📁 Общие")
        
        # Подключаем сигнал all_valid для автозакрытия
        self.paths_widget.all_valid.connect(self._on_all_valid)

        # Вкладка Diffusers
        self.diffusers_widget = DiffusersSettingsWidget(config)
        self.tabs.addTab(self.diffusers_widget, "🎨 Diffusers")

        # Вкладка Ресурсы
        self.resources_widget = ResourcesSettingsWidget(config)
        self.tabs.addTab(self.resources_widget, "⚙️ Ресурсы")

        layout.addWidget(self.tabs, 1)

        # Кнопки OK/Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self._auto_close_timer = None

    def _on_all_valid(self):
        """Все поля валидны — автозакрытие через 1 сек"""
        if self._auto_close_timer:
            self._auto_close_timer.stop()
        self._auto_close_timer = QTimer()
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._auto_accept)
        self._auto_close_timer.start(1000)

    def _auto_accept(self):
        """Автоматическое закрытие диалога"""
        self._on_accept()

    def _on_accept(self):
        """Сохраняет все настройки и закрывает диалог"""
        # Проверяем, есть ли проблемы
        from core.path_validator import PathValidator
        validator = PathValidator()
        venv_valid = validator.validate_venv(self.paths_widget.venv_edit.text())["valid"]
        models_valid = validator.validate_models_path(self.paths_widget.models_edit.text())["valid"]
        output_valid = validator.validate_output_dir(self.paths_widget.output_edit.text())["valid"]
        ollama_valid = validator.validate_ollama_url(self.paths_widget.ollama_edit.text())["valid"]
        
        if not (venv_valid and models_valid and output_valid and ollama_valid):
            # Есть проблемы — показываем предупреждение
            QMessageBox.warning(
                self,
                "Настройка путей",
                "Настройка путей не завершена.\n"
                "Некоторые функции будут недоступны..."
            )
        
        # Сохраняем настройки
        self.paths_widget.save_settings()
        self.diffusers_widget.save_settings()
        self.resources_widget.save_settings()
        
        self.accept()
