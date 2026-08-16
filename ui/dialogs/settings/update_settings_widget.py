"""
ui/dialogs/settings/update_settings_widget.py — вкладка "Обновления" в настройках.

Показывает текущую/доступную версию, CHANGELOG последней версии,
прогресс обновления и кнопки управления.
"""
import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt
from core.updater import Updater


class UpdateSettingsWidget(QWidget):
    """Виджет вкладки Обновления."""

    def __init__(self, config, resource_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.resource_manager = resource_manager
        self.updater = Updater(self)
        self._update_done = False

        self._build_ui()
        self._connect_signals()

        # Первичная проверка при открытии вкладки
        self._set_status("Проверка обновлений...")
        self.updater.check_for_updates()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Версии ---
        version_layout = QHBoxLayout()
        self.lbl_current = QLabel("Текущая версия: —")
        self.lbl_available = QLabel("Доступная версия: —")
        version_layout.addWidget(self.lbl_current)
        version_layout.addWidget(self.lbl_available)
        version_layout.addStretch()
        layout.addLayout(version_layout)

        # --- CHANGELOG ---
        lbl_changelog = QLabel("Что нового:")
        layout.addWidget(lbl_changelog)

        self.txt_changelog = QTextEdit()
        self.txt_changelog.setReadOnly(True)
        self.txt_changelog.setPlaceholderText("Информация о версии появится после проверки обновлений...")
        layout.addWidget(self.txt_changelog, 1)

        # --- Прогресс ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        # --- Кнопки ---
        btn_layout = QHBoxLayout()
        self.btn_update = QPushButton("🔄 Обновить")
        self.btn_cancel = QPushButton("✖ Отменить")
        self.btn_restart = QPushButton("🔁 Перезагрузить")

        self.btn_update.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_restart.setEnabled(False)
        self.btn_restart.setVisible(False)

        btn_layout.addWidget(self.btn_update)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_restart)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        # Сигналы проверки версий
        self.updater.update_available.connect(self._on_update_available)
        self.updater.update_not_found.connect(self._on_update_not_found)
        self.updater.check_failed.connect(self._on_check_failed)
        self.updater.changelog_loaded.connect(self._on_changelog_loaded)

        # Сигналы процесса обновления
        self.updater.update_progress.connect(self._on_update_progress)
        self.updater.update_finished.connect(self._on_update_finished)

        # Кнопки
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_restart.clicked.connect(self._on_restart_clicked)

    # === Обработчики проверки версий ===

    def _on_update_available(self, current, remote):
        self.lbl_current.setText(f"Текущая версия: {current}")
        self.lbl_available.setText(f"Доступная версия: {remote} 🎉")
        self.btn_update.setEnabled(True)
        self._set_status("Доступно обновление!")

    def _on_update_not_found(self, current):
        self.lbl_current.setText(f"Текущая версия: {current}")
        self.lbl_available.setText("Доступная версия: актуально ✅")
        self.btn_update.setEnabled(False)
        self._set_status("У вас последняя версия.")

    def _on_check_failed(self, error):
        self._set_status(f"⚠ Ошибка проверки: {error}")
        self.btn_update.setEnabled(False)

    def _on_changelog_loaded(self, changelog_text):
        self.txt_changelog.setPlainText(changelog_text)

    # === Обработчики процесса обновления ===

    def _on_update_clicked(self):
        # Проверка: не идёт ли генерация
        if self.resource_manager and hasattr(self.resource_manager, 'is_resource_busy'):
            if self.resource_manager.is_resource_busy():
                self._set_status("⚠ Дождитесь завершения генерации.")
                return

        self.btn_update.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_restart.setVisible(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._set_status("Начинаем обновление...")
        self.updater.start_update()

    def _on_cancel_clicked(self):
        self.updater.cancel_update()
        self.btn_cancel.setEnabled(False)
        self._set_status("Отмена обновления...")

    def _on_update_progress(self, stage, percent):
        self.progress_bar.setValue(percent)
        self._set_status(stage)

    def _on_update_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.btn_cancel.setEnabled(False)

        if success:
            self._update_done = True
            self.btn_update.setEnabled(False)
            self.btn_restart.setVisible(True)
            self.btn_restart.setEnabled(True)
            self._set_status(f"✅ {message}")
        else:
            self.btn_update.setEnabled(True)
            self._set_status(f"⚠ {message}")

    def _on_restart_clicked(self):
        """Перезапуск приложения через os.execv."""
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # === Утилиты ===

    def _set_status(self, text):
        self.lbl_status.setText(text)

    def save_settings(self):
        """Заглушка для совместимости с SettingsDialog."""
        pass
