# /home/lin/Scripts/OLLAMA/core/markdown_parser.py

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QTextCursor
import re
import base64


class MarkdownParser:
    def __init__(self):
        pass

    def _get_colors(self):
        """Берёт актуальные системные цвета при каждом вызове.
        Только роли палитры — никаких 8-значных hex с альфой:
        Qt-парсер CSS их не понимает и может отбросить стиль целиком.
        """
        palette = QApplication.palette()
        return {
            'text': palette.color(QPalette.ColorRole.WindowText).name(),
            'base': palette.color(QPalette.ColorRole.Base).name(),
            'alt_base': palette.color(QPalette.ColorRole.AlternateBase).name(),
            'link': palette.color(QPalette.ColorRole.Link).name(),
            'highlight': palette.color(QPalette.ColorRole.Highlight).name(),
            'dim': palette.color(QPalette.ColorRole.PlaceholderText).name(),
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
        border = f'border:1px solid {colors["dim"]};' if not is_open \
            else f'border:2px dashed {colors["dim"]};'

        bg = colors['alt_base']
        text_dim = colors['dim']
        code_color = '#9370DB'  # medium purple — читается и на светлой, и на тёмной теме

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
                f'border-bottom:1px solid {colors["dim"]};'
                f'font-family:sans-serif;">{header_content}</td></tr>'
            )

        # --- Footer (кнопка копирования внизу) ---
        footer_row = ''
        if code_block_index >= 0 and not is_open:
            encoded = base64.b64encode(code_text.encode('utf-8')).decode('ascii')
            footer_row = (
                f'<tr><td style="padding:4px 8px;'
                f'border-top:1px solid {colors["dim"]};'
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

    @staticmethod
    def _split_table_row(s):
        """Делит строку таблицы на ячейки: '| a | b |' -> ['a', 'b']"""
        s = s.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return [cell.strip() for cell in s.split('|')]

    @classmethod
    def _is_table_sep(cls, s):
        """Разделительная строка таблицы: только |, -, :, пробелы."""
        s = s.strip()
        if '-' not in s or not re.match(r'^[\s|:\-]+$', s):
            return False
        cells = cls._split_table_row(s)
        return len(cells) > 0 and all(re.match(r'^:?-+:?$', cell) for cell in cells)

    def _render_table(self, header, aligns, rows, colors):
        """Рендерит таблицу в HTML (рамки и фон — из системной палитры)."""
        dim = colors['dim']
        border = f'border:1px solid {dim};'
        out = [f'<table cellpadding="0" cellspacing="0" style="{border}'
               f'border-collapse:collapse;width:100%;margin:8px 0;">',
               '<tr>']
        for idx, cell in enumerate(header):
            al = aligns[idx] if idx < len(aligns) else 'left'
            out.append(
                f'<td style="{border}padding:6px 8px;'
                f'background:{colors["alt_base"]};text-align:{al};">'
                f'<b>{self._format_inline(cell, colors)}</b></td>')
        out.append('</tr>')
        for row in rows:
            out.append('<tr>')
            for idx, cell in enumerate(row):
                al = aligns[idx] if idx < len(aligns) else 'left'
                out.append(
                    f'<td style="{border}padding:6px 8px;text-align:{al};">'
                    f'{self._format_inline(cell, colors)}</td>')
            out.append('</tr>')
        out.append('</table>')
        return ''.join(out)

    def render_user_message(self, text):
        """Сообщение пользователя: смещено вправо (как в LLM-чатах),
        без подписи, шрифт мельче. Только системная палитра."""
        colors = self._get_colors()
        escaped = self._escape_html(text)
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0;">'
            f'<tr>'
            f'<td width="30%"></td>'
            f'<td style="background:{colors["alt_base"]};'
            f'border-right:3px solid {colors["highlight"]};'
            f'padding:6px 10px;font-size:0.9em;color:{colors["text"]};">'
            f'<div style="white-space:pre-wrap;">{escaped}</div>'
            f'</td>'
            f'</tr>'
            f'</table>'
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
        # Стек отступов маркированных уровней: вложенность определяется
        # относительным отступом (GFM), работает с любым шагом (2/3/4).
        # Глубина ограничена: вырожденные петли модели не должны вешать
        # QTextBrowser. Каждый уровень — свой символ маркера.
        # Единый стек вложенности: общий для маркированных и
        # нумерованных, чтобы смешанные списки видели глубину друг друга.
        nest_stack = []
        # Счётчик нумерованных на каждом уровне (None — уровень маркированный)
        num_at_level = []
        MAX_LIST_DEPTH = 6
        BULLET_MARKERS = ['◦', '‣', '–', '*', '**', '***']
        # Нумерованные: стек отступов + счётчик на каждый уровень.
        # Нумерация всегда автоинкремент в своём уровне: номера моделей
        # ненадёжны, а вложенный список начинает свою нумерацию с 1.
        ol_stack = []
        ol_counters = []

        def close_lists():
            # Списки рендерятся абзацами, открытых тегов нет —
            # закрывать нечего. Стек сбрасывается ТОЛЬКО в reset_numbering().
            pass

        def reset_numbering():
            nest_stack.clear()
            num_at_level.clear()

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Блок кода (2-5 символов ` или ~)
            code_fence_match = re.match(r'^([`~]{2,5})(\w*)\s*$', stripped)
            if code_fence_match:
                if not in_code_block:
                    flush_paragraph()
                    # Код часто живёт ВНУТРИ пунктов списка (шаги с командами) —
                    # стек НЕ сбрасываем, список продолжается после кода.
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
                reset_numbering()
                html_parts.append(
                    f'<hr style="border:none;'
                    f'border-top:1px solid {colors["dim"]};'
                    f'margin:12px 0;">')
                i += 1
                continue

            # Заголовки
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                flush_paragraph()
                close_lists()
                reset_numbering()
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
                reset_numbering()
                html_parts.append(
                    f'<blockquote style="border-left:3px solid '
                    f'{colors["dim"]};margin:8px 0;padding:4px 12px;'
                    f'color:{colors["dim"]};">'
                    f'{self._format_inline(line[2:], colors)}</blockquote>')
                i += 1
                continue

            # Таблица GFM: строка с '|' + разделительная строка следом
            if ('|' in line and i + 1 < len(lines)
                    and self._is_table_sep(lines[i + 1])):
                flush_paragraph()
                close_lists()
                reset_numbering()
                header = self._split_table_row(line)
                aligns = []
                for tok in self._split_table_row(lines[i + 1]):
                    if tok.startswith(':') and tok.endswith(':') and len(tok) >= 3:
                        aligns.append('center')
                    elif tok.endswith(':'):
                        aligns.append('right')
                    else:
                        aligns.append('left')
                i += 2
                rows = []
                while i < len(lines) and '|' in lines[i] and lines[i].strip():
                    rows.append(self._split_table_row(lines[i]))
                    i += 1
                html_parts.append(self._render_table(header, aligns, rows, colors))
                continue

            # Маркированный список (-, *, •) с вложенностью по отступу;
            # каждый уровень — свой символ маркера
            m = re.match(r'^([ \t]*)[-*•]\s+(.+)$', line)
            if m:
                indent = len(m.group(1).replace('\t', '  '))
                flush_paragraph()
                # Выход из более глубоких уровней
                while nest_stack and indent < nest_stack[-1]:
                    nest_stack.pop()
                    num_at_level.pop()
                # Вход на более глубокий уровень (не глубже MAX_LIST_DEPTH)
                if (not nest_stack or indent > nest_stack[-1]) and \
                        len(nest_stack) < MAX_LIST_DEPTH:
                    nest_stack.append(indent)
                    num_at_level.append(None)
                level = len(nest_stack) - 1
                html_parts.append(
                    f'<p style="margin:0.25em 0 0.25em '
                    f'{20 + level * 20}px;">'
                    f'{BULLET_MARKERS[level]}&nbsp;'
                    f'{self._format_inline(m.group(2), colors)}</p>')
                i += 1
                continue

            # Нумерованный список с вложенностью по отступу
            m = re.match(r'^([ \t]*)(\d+)\.\s+(.+)$', line)
            if m:
                indent = len(m.group(1).replace('\t', '  '))
                flush_paragraph()
                # Выход из более глубоких уровней
                while nest_stack and indent < nest_stack[-1]:
                    nest_stack.pop()
                    num_at_level.pop()
                # Вход на более глубокий уровень (не глубже MAX_LIST_DEPTH)
                if (not nest_stack or indent > nest_stack[-1]) and \
                        len(nest_stack) < MAX_LIST_DEPTH:
                    nest_stack.append(indent)
                    num_at_level.append(0)
                elif num_at_level and num_at_level[-1] is None:
                    # Тот же отступ, но уровень был маркированным
                    num_at_level[-1] = 0
                level = len(nest_stack) - 1
                if num_at_level and num_at_level[-1] is not None:
                    num_at_level[-1] += 1
                    num = num_at_level[-1]
                else:
                    num = 1
                html_parts.append(
                    f'<p style="margin:0.4em 0 0.4em '
                    f'{20 + level * 20}px;">'
                    f'{num}.&nbsp;'
                    f'{self._format_inline(m.group(3), colors)}</p>')
                i += 1
                continue

            # Пустая строка
            if not stripped:
                flush_paragraph()
                i += 1
                continue

            # Обычный текст
            close_lists()
            reset_numbering()
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
            f'border-left:3px solid {colors["dim"]};'
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
                f'<a href="#copy:{msg_index}" style="color:{colors["dim"]};'
                f'text-decoration:none;font-size:10px;padding:0 4px;'
                f'opacity:0.7;"> · 📋 копия</a>'
            )

        return (
            f'<div style="font-size:11px;color:{colors["dim"]};'
            f'margin-top:6px;padding:4px 8px;'
            f'border-top:1px solid {colors["dim"]};">'
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
