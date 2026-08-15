from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextBrowser, QApplication, QMenu)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor
from core.markdown_parser import MarkdownParser

class ChatWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Единый QTextBrowser для всей истории + стриминга
        self.chat_browser = QTextBrowser()
        self.chat_browser.anchorClicked.connect(self._on_anchor_clicked)
        self._message_responses = []  # Храним тексты ответов для копирования
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_browser.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.chat_browser, 1)
        
        # Парсер и буферы
        self.parser = MarkdownParser()
        self._history_html = []          # Список отрендеренных сообщений [(role, html), ...]
        self._current_buffer = ""        # Буфер текущего ответа (plain markdown)
        self._current_role = None        # "user" или "assistant"
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._render_current)
    
    def append_user_message(self, text):
        """Добавляет сообщение пользователя в историю"""
        html = self.parser.render_user_message(text)
        self._history_html.append(("user", html))
        self._rerender_all()
    
    def start_assistant_message(self):
        """Начинает стриминг нового ответа"""
        self._current_buffer = ""
        self._current_role = "assistant"
    
    def append_token(self, token):
        """Добавляет токен в буфер текущего ответа"""
        self._current_buffer += token
        if not self._update_timer.isActive():
            self._update_timer.start(200)
    
    def _render_current(self):
        """Рендерит текущий буфер и обновляет браузер"""
        if not self._current_buffer:
            return
        current_html = self.parser.render_assistant_message(self._current_buffer)
        self._rerender_all(current_html_override=current_html)
    
    def finalize_response(self, stats_dict):
        self._update_timer.stop()
        msg_index = len(self._message_responses)
        self._message_responses.append(self._current_buffer)
        
        html = self.parser.render_assistant_message(self._current_buffer, msg_index)
        if stats_dict and (stats_dict.get('completion_tokens', 0) > 0
                           or stats_dict.get('duration_sec', 0) > 0):
            html += self.parser.render_stats(stats_dict, self._current_buffer, msg_index)
        
        self._history_html.append(("assistant", html))
        self._current_buffer = ""
        self._current_role = None
        self._rerender_all()
    
    def _on_anchor_clicked(self, url):
        """Обработка клика по якорю (копирование)"""
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
                import base64
                code_text = base64.b64decode(encoded).decode('utf-8')
                QApplication.clipboard().setText(code_text)
            except Exception:
                pass
    
    def _rerender_all(self, current_html_override=None):
        """Перерисовывает весь чат: история + текущий ответ"""
        parts = []
        for role, html in self._history_html:
            parts.append(html)
        
        if current_html_override:
            parts.append(current_html_override)
        elif self._current_buffer:
            parts.append(self.parser.render_assistant_message(self._current_buffer))
        
        full_html = self.parser.wrap_document('\n'.join(parts))
        self.chat_browser.setHtml(full_html)
        
        # Скролл вниз
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def _show_context_menu(self, pos):
        """Контекстное меню с копированием кода"""
        menu = QMenu(self)
        cursor = self.chat_browser.cursorForPosition(pos)
        
        # Проверяем, находится ли курсор в блоке кода
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
    
    def clear_chat(self):
        self.chat_browser.clear()
        self._history_html = []
        self._current_buffer = ""
        self._current_role = None
        self._message_responses = []
        self._update_timer.stop()
