from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextBrowser, QApplication, QMenu)
from PyQt6.QtCore import Qt, QTimer
import base64
from core.markdown_parser import MarkdownParser


class ChatWidget(QWidget):
    """Append-only просмотрщик готовых сообщений.

    Никакого стриминга и перерисовок во время генерации: каждое сообщение
    добавляется один раз как готовый HTML-блок. Окно свободно для прокрутки,
    копирования и прочих действий пользователя в любой момент.
    """

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chat_browser = QTextBrowser()
        self.chat_browser.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_browser.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.chat_browser, 1)

        self.parser = MarkdownParser()
        self._history_html = []        # [(role, html), ...] — готовые блоки
        self._message_responses = []   # сырые тексты ответов для копирования

    # ─── Публичное API (append-only) ─────────────────────────────

    def append_user_message(self, text):
        """Добавляет сообщение пользователя (рендер один раз)."""
        html = self.parser.render_user_message(text)
        self._history_html.append(("user", html))
        self._rerender()

    def append_assistant_message(self, markdown_text, stats_dict=None):
        """Добавляет готовый ответ ассистента (рендер один раз).

        markdown_text: сырой markdown ответа
        stats_dict:    статистика генерации (опционально)
        """
        if not markdown_text:
            return
        msg_index = len(self._message_responses)
        self._message_responses.append(markdown_text)

        html = self.parser.render_assistant_message(markdown_text, msg_index)
        if stats_dict and (stats_dict.get('completion_tokens', 0) > 0
                           or stats_dict.get('duration_sec', 0) > 0):
            html += self.parser.render_stats(stats_dict, markdown_text, msg_index)

        self._history_html.append(("assistant", html))
        self._rerender()

    def clear_chat(self):
        """Очистка чата."""
        self.chat_browser.clear()
        self._history_html = []
        self._message_responses = []

    # ─── Внутренние методы ───────────────────────────────────────

    def _rerender(self):
        """Перерисовывает чат. Вызывается только при добавлении сообщения."""
        sb = self.chat_browser.verticalScrollBar()
        # Пользователь у нижнего края? Тогда автоскроллим, иначе не дёргаем.
        was_at_bottom = sb.value() >= sb.maximum() - 30

        parts = [html for _role, html in self._history_html]
        full_html = self.parser.wrap_document('\n'.join(parts))
        self.chat_browser.setHtml(full_html)

        if was_at_bottom:
            # Отложенный скролл: Qt должен успеть сделать layout,
            # чтобы maximum() был актуален для нового документа.
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        """Скроллит чат в самый низ."""
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_anchor_clicked(self, url):
        """Обработка клика по якорю (копирование)."""
        anchor = url.toString()

        # Копирование ответа по индексу
        if anchor.startswith('#copy:'):
            try:
                msg_index = int(anchor.split(':')[1])
                if 0 <= msg_index < len(self._message_responses):
                    QApplication.clipboard().setText(self._message_responses[msg_index])
            except (ValueError, IndexError):
                pass

        # Копирование блока кода (текст в base64)
        elif anchor.startswith('#copycode:'):
            try:
                encoded = anchor.split(':', 1)[1]
                code_text = base64.b64decode(encoded).decode('utf-8')
                QApplication.clipboard().setText(code_text)
            except Exception:
                pass

    def _show_context_menu(self, pos):
        """Контекстное меню с копированием кода."""
        menu = QMenu(self)
        cursor = self.chat_browser.cursorForPosition(pos)
        code_text = self.parser.get_code_at_cursor(cursor)

        if code_text is not None:
            copy_code = menu.addAction("Копировать код")
            menu.addSeparator()
            copy_all = menu.addAction("Копировать всё")

            action = menu.exec(self.chat_browser.mapToGlobal(pos))
            if action == copy_code:
                QApplication.clipboard().setText(code_text)
            elif action == copy_all:
                self.chat_browser.selectAll()
                self.chat_browser.copy()
                self.chat_browser.textCursor().clearSelection()
        else:
            menu.addAction("Копировать", self.chat_browser.copy)
            menu.addSeparator()
            menu.addAction("Копировать всё", lambda: (
                self.chat_browser.selectAll(),
                self.chat_browser.copy(),
                self.chat_browser.textCursor().clearSelection()
            ))
            menu.exec(self.chat_browser.mapToGlobal(pos))
