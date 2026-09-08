import sys
from PyQt6.QtCore import Qt
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
    
    # Глобальная страховка: все диалоги приложения ненативные
    # (совместимость с Qt < 6.5 + страховка от KDE-сегфолтов)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    
    # Фикс роли PlaceholderText для тёмных тем (баг на Убунту):
    # системная палитра отдаёт чёрный PlaceholderText при светлом Text —
    # плейсхолдеры полей и приглушённый текст (статистика, кнопки «копия»)
    # становятся нечитаемыми на тёмном фоне. Пересчитываем из цвета Text
    # с прозрачностью ~55%: читаемо и приглушённо, в любой теме.
    from PyQt6.QtGui import QColor, QPalette
    _pal = app.palette()
    _text_color = QColor(_pal.color(QPalette.ColorRole.Text))
    _text_color.setAlpha(140)
    for _group in (QPalette.ColorGroup.Active,
                   QPalette.ColorGroup.Inactive,
                   QPalette.ColorGroup.Disabled):
        _pal.setColor(_group, QPalette.ColorRole.PlaceholderText, _text_color)
    app.setPalette(_pal)
    
    # Создаём конфиг
    config = Config()
    
    # Проверяем пути при старте (только установленные компоненты)
    validator = PathValidator()
    result = validator.validate_installed(config)
    
    # Создаём папку для чатов (если её нет)
    import os
    chats_dir = config.get_chats_dir()
    os.makedirs(chats_dir, exist_ok=True)

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
