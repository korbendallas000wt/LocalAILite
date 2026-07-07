import sys
from PyQt6.QtWidgets import QApplication, QStyleFactory, QMessageBox
from ui.main_window import MainWindow
from ui.dialogs.paths_dialog import PathsDialog
from ui.dialogs.settings.settings_dialog import SettingsDialog
from utils.config import Config
from core.path_validator import PathValidator

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Применение системного стиля (если доступен)
    system_styles = ["Breeze", "Adwaita", "Fusion"]
    for style_name in system_styles:
        if style_name in QStyleFactory.keys():
            app.setStyle(QStyleFactory.create(style_name))
            break
    
    # Создаём конфиг
    config = Config()
    
    # Проверяем пути при старте
    validator = PathValidator()
    result = validator.validate_all(config)
    
    window = MainWindow()
    
    # Если пути не настроены, показываем диалог настроек
    if not result["all_valid"]:
        dialog = SettingsDialog(config, window)
        dialog.tabs.setCurrentIndex(0)  # Открываем на вкладке "Общие"
        if not dialog.exec():
            QMessageBox.warning(
                window,
                "Настройка путей",
                "Настройка путей отменена.\n"
                "Некоторые функции будут недоступны.\n\n"
                "Вы можете настроить пути позже через меню Настройки → Настройки..."
            )
    
    window.show()
    sys.exit(app.exec())
