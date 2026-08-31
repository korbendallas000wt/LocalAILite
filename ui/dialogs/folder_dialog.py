"""
Обёртка над QFileDialog с поддержкой режима "выбор папки кликом".

Режимы:
- mode="navigate" — стандартное поведение (двойной клик = вход в папку)
- mode="select" — вход в папку = выбор, диалог закрывается

Используется для выбора чатов (Ollama), где навигация не нужна.
Для Diffusers (чекпоинты) и настройки путей — режим "navigate".
"""
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtCore import QTimer
from pathlib import Path


class FolderDialog:
    @staticmethod
    def get_folder(
        parent,
        start_dir: str | Path,
        title: str = "Выберите папку",
        mode: str = "navigate"
    ) -> str | None:
        """
        Выбрать папку с опциональным перехватом входа.

        Args:
            parent: родительский виджет
            start_dir: начальная директория
            title: заголовок диалога
            mode: "navigate" (стандарт) или "select" (вход в папку = выбор)

        Returns:
            Путь к выбранной папке или None
        """
        dialog = QFileDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setDirectory(str(start_dir))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)

        # Путь, выбранный через сигнал (для режима "select")
        selected_path = [None]

        if mode == "select":
            start_dir_resolved = str(Path(start_dir).resolve())

            def on_directory_entered(directory):
                """Вход в папку = выбор и закрытие диалога"""
                # Игнорируем стартовую директорию
                if str(Path(directory).resolve()) == start_dir_resolved:
                    return
                # Сохраняем путь и закрываем диалог (отложенно)
                selected_path[0] = directory
                QTimer.singleShot(0, dialog.accept)

            dialog.directoryEntered.connect(on_directory_entered)

        if dialog.exec():
            # Если путь был сохранён через сигнал, возвращаем его
            if selected_path[0]:
                return selected_path[0]
            # Иначе стандартный выбор (для режима "navigate")
            selected = dialog.selectedFiles()
            return selected[0] if selected else None
        return None
