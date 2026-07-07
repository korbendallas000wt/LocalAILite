from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox
from PyQt6.QtCore import Qt
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

        # Вкладка Diffusers
        self.diffusers_widget = DiffusersSettingsWidget(config)
        self.tabs.addTab(self.diffusers_widget, "🎨 Diffusers")
        
        # Вкладка Ресурсы
        self.resources_widget = ResourcesSettingsWidget(config)
        self.tabs.addTab(self.resources_widget, "⚙️ Ресурсы")

        # Будущие вкладки:
        # self.ollama_widget = OllamaSettingsWidget(config)
        # self.tabs.addTab(self.ollama_widget, "💬 Ollama")

        layout.addWidget(self.tabs, 1)

        # Кнопки OK/Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        """Сохраняет все настройки и закрывает диалог"""
        self.paths_widget.save_settings()
        self.diffusers_widget.save_settings()
        self.resources_widget.save_settings()
        # self.ollama_widget.save_settings()  # будущее
        self.accept()
