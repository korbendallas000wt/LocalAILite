from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QApplication, QMenu
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
import base64
from core.markdown_parser import MarkdownParser

class ChatWidget(QWidget):
    # Сигналы для управления ветвлением
    trim_requested = pyqtSignal(int)       # user_msg_index
    branch_requested = pyqtSignal(int)     # user_msg_index
    load_chat_requested = pyqtSignal(int)      # номер чата для загрузки
    # Сигналы для вложений
    open_file_requested = pyqtSignal(int, int)   # user_msg_index, file_idx
    remove_file_requested = pyqtSignal(int, int) # user_msg_index, file_idx

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chat_browser = QTextBrowser()
        self.chat_browser.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chat_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_browser.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.chat_browser, 1)

        self.parser = MarkdownParser()
        self._history_html = []
        self._message_responses = []
        self.auto_scroll_enabled = True

    def set_auto_scroll(self, enabled: bool):
        self.auto_scroll_enabled = enabled

    def append_user_message(self, text, user_msg_index=-1, branches_count=0, alternatives=None, attachments=None):
        html = self.parser.render_user_message(text, user_msg_index, branches_count, alternatives, attachments)
        self._history_html.append(("user", html))
        self._rerender()

    def append_assistant_message(self, markdown_text, stats_dict=None):
        if not markdown_text:
            return
        msg_index = len(self._message_responses)
        self._message_responses.append(markdown_text)

        html = self.parser.render_assistant_message(markdown_text, msg_index)
        # Всегда рендерим блок статистики/копирования, даже если stats пустой или нулевой.
        # Это гарантирует наличие кнопки "📋 копия" для загруженных чатов.
        html += self.parser.render_stats(stats_dict or {}, markdown_text, msg_index)

        self._history_html.append(("assistant", html))
        self._rerender()

    def clear_chat(self):
        self.chat_browser.clear()
        self._history_html = []
        self._message_responses = []

    def load_chat(self, messages: list, branches_dict=None, alternatives_func=None, current_chat_number=None):
        """Очищает чат и загружает историю из списка сообщений"""
        self.clear_chat()
        if branches_dict is None:
            branches_dict = {}
        for msg in messages:
            if msg["role"] == "user":
                user_idx = msg.get("user_msg_index", -1)
                branches_count = current_chat_number if current_chat_number else 0
                alternatives = alternatives_func(user_idx) if alternatives_func else None
                attachments = msg.get("attachments", None)
                self.append_user_message(msg["content"], user_idx, branches_count, alternatives, attachments)
            elif msg["role"] == "assistant":
                self.append_assistant_message(msg["content"], msg.get("stats"))

    def remove_last_message(self):
        """Удаляет последний блок (или пару) из истории."""
        if not self._history_html:
            return
        
        if self._history_html[-1][0] == "assistant" and len(self._history_html) >= 2 and self._history_html[-2][0] == "user":
            self._history_html.pop()
            self._history_html.pop()
            if self._message_responses:
                self._message_responses.pop()
        elif self._history_html[-1][0] == "user":
            self._history_html.pop()
            
        self._rerender()

    def _rerender(self):
        sb = self.chat_browser.verticalScrollBar()
        was_at_bottom = sb.value() >= sb.maximum() - 30

        parts = [html for _role, html in self._history_html]
        full_html = self.parser.wrap_document('\n'.join(parts))
        self.chat_browser.setHtml(full_html)

        if self.auto_scroll_enabled or was_at_bottom:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_anchor_clicked(self, url):
        anchor = url.toString()
        sb = self.chat_browser.verticalScrollBar()
        scroll_pos = sb.value()

        if anchor.startswith('#copy:'):
            try:
                msg_index = int(anchor.split(':')[1])
                if 0 <= msg_index < len(self._message_responses):
                    QApplication.clipboard().setText(self._message_responses[msg_index])
            except (ValueError, IndexError):
                pass
        elif anchor.startswith('#copycode:'):
            try:
                encoded = anchor.split(':', 1)[1]
                code_text = base64.b64decode(encoded).decode('utf-8')
                QApplication.clipboard().setText(code_text)
            except Exception:
                pass
        elif anchor.startswith('#trim:'):
            try:
                user_idx = int(anchor.split(':')[1])
                self.trim_requested.emit(user_idx)
            except ValueError:
                pass
        elif anchor.startswith('#branch:'):
            try:
                user_idx = int(anchor.split(':')[1])
                self.branch_requested.emit(user_idx)
            except ValueError:
                pass
        elif anchor.startswith('#loadchat:'):
            try:
                chat_num = int(anchor.split(':')[1])
                self.load_chat_requested.emit(chat_num)
            except ValueError:
                pass
        elif anchor.startswith('#openfile:'):
            try:
                parts = anchor.split(':')
                user_idx = int(parts[1])
                file_idx = int(parts[2])
                self.open_file_requested.emit(user_idx, file_idx)
            except (ValueError, IndexError):
                pass
        elif anchor.startswith('#removefile:'):
            try:
                parts = anchor.split(':')
                user_idx = int(parts[1])
                file_idx = int(parts[2])
                self.remove_file_requested.emit(user_idx, file_idx)
            except (ValueError, IndexError):
                pass
        
        QTimer.singleShot(0, lambda: sb.setValue(scroll_pos))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        cursor = self.chat_browser.cursorForPosition(pos)
        code_text = self.parser.get_code_at_cursor(cursor)

        if code_text is not None:
            copy_code = menu.addAction("Копировать код")
            menu.addSeparator()
            copy_all = menu.addAction("Копировать всё")

            action = menu.exec(self.chat_browser.mapToGlobal(pos))
            if action:
                self._copy_safe(action == copy_code, code_text)
        else:
            menu.addAction("Копировать", self.chat_browser.copy)
            menu.addSeparator()
            menu.addAction("Копировать всё", lambda: self._copy_safe(False, ""))
            menu.exec(self.chat_browser.mapToGlobal(pos))

    def _copy_safe(self, is_code, code_text):
        sb = self.chat_browser.verticalScrollBar()
        scroll_pos = sb.value()
        
        if is_code:
            QApplication.clipboard().setText(code_text)
        else:
            QApplication.clipboard().setText(self.chat_browser.toPlainText())
            
        QTimer.singleShot(0, lambda: sb.setValue(scroll_pos))
