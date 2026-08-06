import sys
from PyQt6.QtWidgets import QApplication, QStyleFactory, QMessageBox
from ui.main_window import MainWindow
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
    
    # Проверяем пути при старте (только установленные компоненты)
    validator = PathValidator()
    result = validator.validate_installed(config)
    
    window = MainWindow()
    
    # Если пути не настроены, показываем диалог настроек
    if not result["all_valid"]:
        dialog = SettingsDialog(config, window)
        dialog.tabs.setCurrentIndex(0)  # Открываем на вкладке "Общие"
        
        if not dialog.exec():
            # Cancel — показываем предупреждение
            QMessageBox.warning(
                window,
                "Настройка путей",
                "Настройка путей не завершена.\n"
                "Некоторые функции будут недоступны..."
            )
    
    window.show()
    sys.exit(app.exec())
