# /home/lin/Scripts/OLLAMA/core/markdown_parser.py

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QTextCursor
import re
import base64


class MarkdownParser:
    def __init__(self):
        pass

    def _get_colors(self):
        """Берёт актуальные системные цвета при каждом вызове"""
        palette = QApplication.palette()
        return {
            'text': palette.color(QPalette.ColorRole.WindowText).name(),
            'base': palette.color(QPalette.ColorRole.Base).name(),
            'alt_base': palette.color(QPalette.ColorRole.AlternateBase).name(),
            'link': palette.color(QPalette.ColorRole.Link).name(),
            'highlight': palette.color(QPalette.ColorRole.Highlight).name(),
        }

    def _escape_html(self, text):
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))

    def _format_inline(self, text, colors):
        """Обработка инлайн-элементов"""
        text = self._escape_html(text)
        # Инлайн-код
        text = re.sub(
            r'`([^`]+)`',
            lambda m: f'<code style="background:{colors["alt_base"]};padding:2px 5px;'
                      f'font-family:Consolas,monospace;">{m.group(1)}</code>',
            text
        )
        # Жирный + курсив
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
        # Жирный
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Курсив
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        # Ссылки
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{m.group(2)}" style="color:{colors["link"]};">{m.group(1)}</a>',
            text
        )
        return text

    def _render_code_block(self, code_text, lang, colors, is_open=False,
                           msg_index=-1, code_block_index=-1):
        """Рендерит блок кода: серый фон у ячейки с кодом, тонкая рамка, фиолетовый монохромный код"""

        # Экранируем код без подсветки
        escaped_code = self._escape_html(code_text)

        # Тонкая рамка цветом текста
        border = f'border:1px solid {colors["text"]};' if not is_open \
            else f'border:2px dashed {colors["text"]};'

        bg = colors['alt_base']
        text_dim = f'{colors["text"]}99'
        code_color = '#9370DB'  # medium purple

        # --- Header (язык + кнопка копирования) ---
        header_row = ''
        if lang or code_block_index >= 0:
            header_cells = []
            if lang:
                header_cells.append(
                    f'<span style="font-size:10px;color:{text_dim};'
                    f'font-family:sans-serif;">{self._escape_html(lang)}</span>'
                )
            if code_block_index >= 0:
                encoded = base64.b64encode(code_text.encode('utf-8')).decode('ascii')
                header_cells.append(
                    f'<a href="#copycode:{encoded}" style="font-size:10px;'
                    f'color:{text_dim};text-decoration:none;float:right;">📋</a>'
                )
            header_content = ' &nbsp;·&nbsp; '.join(header_cells)
            header_row = (
                f'<tr><td style="padding:4px 8px;'
                f'border-bottom:1px solid {colors["text"]};'
                f'font-family:sans-serif;">{header_content}</td></tr>'
            )

        # --- Footer (кнопка копирования внизу) ---
        footer_row = ''
        if code_block_index >= 0 and not is_open:
            encoded = base64.b64encode(code_text.encode('utf-8')).decode('ascii')
            footer_row = (
                f'<tr><td style="padding:4px 8px;'
                f'border-top:1px solid {colors["text"]};'
                f'font-family:sans-serif;text-align:left;">'
                f'<a href="#copycode:{encoded}" style="font-size:10px;'
                f'color:{text_dim};text-decoration:none;">Копировать код 📋</a>'
                f'</td></tr>'
            )

        # --- Таблица-обёртка (фон у ячейки с кодом) ---
        return (
            f'<table cellpadding="0" cellspacing="0" '
            f'style="{border}'
            f'margin:8px 0;border-collapse:collapse;width:100%;">'
            f'{header_row}'
            f'<tr><td style="padding:10px;background:{bg};">'
            f'<pre style="margin:0;font-family:Consolas,&quot;Courier New&quot;,monospace;'
            f'font-size:13px;color:{code_color};'
            f'white-space:pre-wrap;word-wrap:break-word;'
            f'line-height:1.4;">{escaped_code}</pre>'
            f'</td></tr>'
            f'{footer_row}'
            f'</table>'
        )

    def render_user_message(self, text):
        colors = self._get_colors()
        escaped = self._escape_html(text)
        return (
            f'<div style="background:{colors["highlight"]}20;'
            f'border-left:3px solid {colors["highlight"]};'
            f'padding:8px 12px;margin:10px 0;">'
            f'<div style="font-weight:bold;color:{colors["link"]};'
            f'margin-bottom:4px;">Вы:</div>'
            f'<div style="white-space:pre-wrap;">{escaped}</div>'
            f'</div>'
        )

    def render_assistant_message(self, markdown_text, msg_index=-1):
        """Парсит Markdown в HTML"""
        colors = self._get_colors()
        lines = markdown_text.split('\n')
        html_parts = []
        i = 0
        paragraph_buffer = []
        code_block_counter = 0

        def flush_paragraph():
            if paragraph_buffer:
                text = ' '.join(paragraph_buffer)
                html_parts.append(
                    f'<p style="margin:0.5em 0;">'
                    f'{self._format_inline(text, colors)}</p>')
                paragraph_buffer.clear()

        in_code_block = False
        code_buffer = []
        code_lang = ""
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            if in_ol:
                html_parts.append('</ol>')
                in_ol = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Блок кода (2-5 символов ` или ~)
            code_fence_match = re.match(r'^([`~]{2,5})(\w*)\s*$', stripped)
            if code_fence_match:
                if not in_code_block:
                    flush_paragraph()
                    close_lists()
                    in_code_block = True
                    code_lang = code_fence_match.group(2)
                    code_buffer = []
                else:
                    in_code_block = False
                    code_text = '\n'.join(code_buffer)
                    html_parts.append(self._render_code_block(
                        code_text, code_lang, colors,
                        is_open=False, msg_index=msg_index,
                        code_block_index=code_block_counter))
                    code_block_counter += 1
                i += 1
                continue

            if in_code_block:
                code_buffer.append(line)
                i += 1
                continue

            # Горизонтальная линия
            if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
                flush_paragraph()
                close_lists()
                html_parts.append(
                    f'<hr style="border:none;'
                    f'border-top:1px solid {colors["text"]}40;'
                    f'margin:12px 0;">')
                i += 1
                continue

            # Заголовки
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                flush_paragraph()
                close_lists()
                level = len(m.group(1))
                html_parts.append(
                    f'<h{level} style="color:{colors["link"]};'
                    f'margin:0.8em 0 0.4em 0;">'
                    f'{self._format_inline(m.group(2), colors)}</h{level}>')
                i += 1
                continue

            # Цитата
            if line.startswith('> '):
                flush_paragraph()
                close_lists()
                html_parts.append(
                    f'<blockquote style="border-left:3px solid '
                    f'{colors["text"]}40;margin:8px 0;padding:4px 12px;'
                    f'color:{colors["text"]}cc;">'
                    f'{self._format_inline(line[2:], colors)}</blockquote>')
                i += 1
                continue

            # Маркированный список
            m = re.match(r'^[\s]*[-*]\s+(.+)$', line)
            if m:
                flush_paragraph()
                if in_ol:
                    html_parts.append('</ol>')
                    in_ol = False
                if not in_ul:
                    html_parts.append(
                        '<ul style="margin:0.5em 0;padding-left:25px;">')
                    in_ul = True
                html_parts.append(
                    f'<li>{self._format_inline(m.group(1), colors)}</li>')
                i += 1
                continue

            # Нумерованный список
            m = re.match(r'^[\s]*(\d+)\.\s+(.+)$', line)
            if m:
                flush_paragraph()
                if in_ul:
                    html_parts.append('</ul>')
                    in_ul = False
                if not in_ol:
                    html_parts.append(
                        '<ol style="margin:0.5em 0;padding-left:25px;">')
                    in_ol = True
                html_parts.append(
                    f'<li>{self._format_inline(m.group(2), colors)}</li>')
                i += 1
                continue

            # Пустая строка
            if not stripped:
                flush_paragraph()
                close_lists()
                i += 1
                continue

            # Обычный текст
            paragraph_buffer.append(stripped)
            i += 1

        # Незакрытый блок кода
        if in_code_block:
            code_text = '\n'.join(code_buffer)
            html_parts.append(self._render_code_block(
                code_text, code_lang, colors,
                is_open=True, msg_index=msg_index,
                code_block_index=code_block_counter))

        flush_paragraph()
        close_lists()

        wrapper_style = (
            f'color:{colors["text"]};'
            f'padding:8px 12px;'
            f'margin:10px 0;'
            f'border-left:3px solid {colors["text"]}40;'
        )
        return f'<div style="{wrapper_style}">{"".join(html_parts)}</div>'

    def render_stats(self, stats, response_text="", msg_index=-1):
        colors = self._get_colors()
        dur = stats.get('duration_sec', 0)
        pt = stats.get('prompt_tokens', 0)
        ct = stats.get('completion_tokens', 0)
        tps = stats.get('tokens_per_sec', 0)
        dur_str = f'{dur:.1f}с' if dur > 0 else '—'
        tps_str = f'{tps:.0f}' if tps > 0 else '—'

        copy_btn = ''
        if response_text and msg_index >= 0:
            copy_btn = (
                f'<a href="#copy:{msg_index}" style="color:{colors["text"]}99;'
                f'text-decoration:none;font-size:10px;padding:0 4px;'
                f'opacity:0.7;"> · 📋 копия</a>'
            )

        return (
            f'<div style="font-size:11px;color:{colors["text"]}99;'
            f'margin-top:6px;padding:4px 8px;'
            f'border-top:1px solid {colors["text"]}20;">'
            f'⏱ {dur_str} · 📥 {pt} ток · 📤 {ct} ток · ⚡ {tps_str} ток/с'
            f'{copy_btn}'
            f'</div>'
        )

    def wrap_document(self, body_html):
        colors = self._get_colors()
        return (
            f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
            f'<style>'
            f'body {{ font-family: sans-serif; line-height: 1.6; '
            f'color: {colors["text"]}; background: transparent; '
            f'margin: 0; padding: 5px; }}'
            f'a {{ color: {colors["link"]}; }}'
            f'</style></head><body>{body_html}</body></html>'
        )

    def get_code_at_cursor(self, cursor: QTextCursor):
        """Возвращает текст блока кода, если курсор внутри него"""
        block = cursor.block()
        font_family = block.charFormat().font().family()
        if font_family not in ('Consolas', 'Courier New', 'Monospace', 'Courier'):
            return None

        code_lines = [block.text()]

        check_block = block.previous()
        while check_block.isValid():
            if check_block.charFormat().font().family() in \
               ('Consolas', 'Courier New', 'Monospace', 'Courier'):
                code_lines.insert(0, check_block.text())
            else:
                break
            check_block = check_block.previous()

        check_block = block.next()
        while check_block.isValid():
            if check_block.charFormat().font().family() in \
               ('Consolas', 'Courier New', 'Monospace', 'Courier'):
                code_lines.append(check_block.text())
            else:
                break
            check_block = check_block.next()

        return '\n'.join(code_lines) if code_lines else None
