"""Диалог справки по пресетам и генерации.

Этап 5.5: справочный материал для осознанной настройки пресетов.

Открывается из диалога пресетов (кнопка "?"). Отображает:
- Толковый словарь параметров (что это, на что влияет, рекомендации)
- Таблицу соответствий семплеров A1111/Forge → наши планировщики
- Рекомендации по архитектурам моделей (SDXL, турбо)
- Общие советы для новичков

Диалог НЕ интерактивный — пользователь читает и сам вводит значения
в диалог пресетов. Это справочный материал, а не автоматизация.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTextBrowser,
                             QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt
from core.preset_cheatsheet import (get_sampler_mapping, get_parameter_glossary,
                                    get_model_architectures, get_general_tips)


class PresetCheatsheetDialog(QDialog):
    """Модальный диалог справки по пресетам и генерации."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шпаргалка по пресетам и генерации")
        self.setMinimumSize(700, 600)
        self.resize(800, 650)

        layout = QVBoxLayout(self)

        # Браузер для отображения справочного материала
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)  # Справочник без внешних ссылок
        self.browser.setHtml(self._build_html())
        layout.addWidget(self.browser)

        # Кнопка закрытия
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _build_html(self) -> str:
        """Генерирует HTML-контент справочника из данных шпаргалки."""
        html_parts = []

        # Заголовок
        html_parts.append("""
        <html>
        <head>
        <style>
            body { font-family: sans-serif; line-height: 1.5; }
            h1 { border-bottom: 2px solid; padding-bottom: 6px; }
            h2 { margin-top: 20px; border-bottom: 1px solid; padding-bottom: 4px; }
            .param-block { border: 1px solid; padding: 10px; margin-bottom: 12px; }
            .param-title { font-weight: bold; margin-bottom: 6px; }
            .field-label { font-weight: bold; }
            .recommendation { margin-left: 12px; margin-bottom: 4px; }
            table { border-collapse: collapse; width: 100%; margin-top: 8px; }
            th { font-weight: bold; border: 1px solid; padding: 6px; text-align: left; }
            td { border: 1px solid; padding: 6px; }
            .tip { border: 1px solid; padding: 6px 10px; margin-bottom: 8px; }
            .notes { font-style: italic; margin-top: 4px; }
            ul { margin-top: 4px; }
            li { margin-bottom: 6px; }
        </style>
        </head>
        <body>
        """)

        html_parts.append("<h1>📖 Шпаргалка по пресетам и генерации</h1>")
        html_parts.append("""
        <p>Этот справочник поможет вам осознанно настроить пресет модели.
        Прочитайте объяснения параметров и введите подходящие значения в диалог пресетов.</p>
        """)

        # === Раздел 1: Толковый словарь параметров ===
        html_parts.append("<h2>1. Толковый словарь параметров</h2>")
        glossary = get_parameter_glossary()
        for param_name, info in glossary.items():
            html_parts.append(self._render_parameter(param_name, info))

        # === Раздел 2: Таблица соответствий семплеров ===
        html_parts.append("<h2>2. Соответствие семплеров (A1111/Forge → LocalAILite)</h2>")
        html_parts.append(self._render_sampler_mapping())

        # === Раздел 3: Рекомендации по архитектурам ===
        html_parts.append("<h2>3. Рекомендации по архитектурам моделей</h2>")
        html_parts.append(self._render_architectures())

        # === Раздел 4: Общие советы ===
        html_parts.append("<h2>4. Общие советы</h2>")
        html_parts.append(self._render_general_tips())

        html_parts.append("</body></html>")
        return "\n".join(html_parts)

    def _render_parameter(self, param_name: str, info: dict) -> str:
        """Отрисовывает блок одного параметра из толкового словаря."""
        parts = []
        parts.append('<div class="param-block">')

        # Заголовок параметра
        title = info.get("title", param_name)
        parts.append(f'<div class="param-title">{title}</div>')

        # Что это
        what_is = info.get("what_is", "")
        if what_is:
            parts.append(f'<p><span class="field-label">Что это:</span> {what_is}</p>')

        # На что влияет
        affects = info.get("affects", "")
        if affects:
            parts.append(f'<p><span class="field-label">На что влияет:</span> {affects}</p>')

        # Ограничения
        limitations = info.get("limitations", "")
        if limitations:
            parts.append(f'<p><span class="field-label">Ограничения:</span> {limitations}</p>')

        # Когда использовать
        when_to_use = info.get("when_to_use", "")
        if when_to_use:
            parts.append(f'<p><span class="field-label">Когда использовать:</span> {when_to_use}</p>')

        # Рекомендации (словарь)
        recommendations = info.get("recommendations", {})
        if recommendations:
            parts.append('<p><span class="field-label">Рекомендации:</span></p>')
            for key, value in recommendations.items():
                parts.append(f'<div class="recommendation"><b>{key}:</b> {value}</div>')

        # Значения (словарь для timestep_spacing, seed)
        values = info.get("values", {})
        if values:
            parts.append('<p><span class="field-label">Значения:</span></p>')
            for key, value in values.items():
                parts.append(f'<div class="recommendation"><b>{key}:</b> {value}</div>')

        # Примеры негативных промптов
        common_examples = info.get("common_examples", {})
        if common_examples:
            parts.append('<p><span class="field-label">Типичные примеры:</span></p>')
            for key, value in common_examples.items():
                parts.append(f'<div class="recommendation"><b>{key}:</b> {value}</div>')

        # Советы
        tips = info.get("tips", "")
        if tips:
            parts.append(f'<div class="tip">💡 {tips}</div>')

        # См. также
        see_also = info.get("see_also", [])
        if see_also:
            glossary = get_parameter_glossary()
            related_titles = []
            for related in see_also:
                if related in glossary:
                    related_titles.append(glossary[related].get("title", related))
            if related_titles:
                parts.append(f'<p class="notes">См. также: {", ".join(related_titles)}</p>')

        parts.append('</div>')
        return "\n".join(parts)

    def _render_sampler_mapping(self) -> str:
        """Отрисовывает таблицу соответствий семплеров."""
        mapping = get_sampler_mapping()
        entries = mapping.get("entries", [])
        if not entries:
            return "<p>Таблица соответствий недоступна.</p>"

        description = mapping.get("description", "")
        parts = []
        if description:
            parts.append(f"<p>{description}</p>")

        parts.append('<table>')
        parts.append('<tr><th>A1111/Forge</th><th>Наш планировщик</th><th>Timestep Spacing</th><th>Karras</th><th>Заметки</th></tr>')

        for entry in entries:
            a1111 = entry.get("a1111_name", "")
            scheduler = entry.get("our_scheduler", "")
            spacing = entry.get("our_timestep_spacing", "")
            karras = "✓" if entry.get("use_karras_sigmas", False) else "—"
            notes = entry.get("notes", "")
            parts.append(f'<tr><td>{a1111}</td><td>{scheduler}</td><td>{spacing}</td><td>{karras}</td><td>{notes}</td></tr>')

        parts.append('</table>')
        return "\n".join(parts)

    def _render_architectures(self) -> str:
        """Отрисовывает рекомендации по архитектурам моделей."""
        archs = get_model_architectures()
        entries = archs.get("entries", [])
        if not entries:
            return "<p>Рекомендации по архитектурам недоступны.</p>"

        parts = []
        for entry in entries:
            name = entry.get("name", "")
            examples = entry.get("examples", "")
            notes = entry.get("notes", "")
            recs = entry.get("base_recommendations", {})

            parts.append('<div class="param-block">')
            parts.append(f'<div class="param-title">{name}</div>')
            if examples:
                parts.append(f'<p><span class="field-label">Примеры:</span> {examples}</p>')

            if recs:
                parts.append('<p><span class="field-label">Базовые рекомендации:</span></p>')
                for key, value in recs.items():
                    parts.append(f'<div class="recommendation"><b>{key}:</b> {value}</div>')

            if notes:
                parts.append(f'<p class="notes">{notes}</p>')

            parts.append('</div>')

        return "\n".join(parts)

    def _render_general_tips(self) -> str:
        """Отрисовывает общие советы."""
        tips = get_general_tips()
        if not tips:
            return "<p>Общие советы недоступны.</p>"

        parts = ["<ul>"]
        for tip in tips:
            parts.append(f"<li>{tip}</li>")
        parts.append("</ul>")
        return "\n".join(parts)
