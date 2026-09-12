"""Шпаргалка по пресетам и генерации (core/preset_cheatsheet.py).

Загружает образовательный справочник из `core/info/preset_cheatsheet.json`
и предоставляет функции доступа к его разделам.

Назначение:
- Таблица соответствий семплеров A1111/Forge → наши планировщики
- Толковый словарь параметров (что это, на что влияет, рекомендации)
- Базовые рекомендации для архитектур моделей (SDXL, турбо)
- Общие советы для новичков

Диалог справки (Этап 5.5) отображает эти данные как справочный материал.
Модуль НЕ интерактивный — пользователь читает и сам вводит значения
в диалог пресетов.

Будущее (задел): структура `parameter_glossary` готова отдавать объяснения
для каждого поля отдельно — когда добавим чекбокс "Показывать подсказки"
со значками "?" рядом с полями, UI будет брать объяснения из того же JSON
(поле `what_is` для тултипа значка "?").
"""
import json
from pathlib import Path

# Путь к JSON-файлу шпаргалки (относительно этого модуля: core/../core/info/)
_CHEATSHEET_PATH = Path(__file__).parent / "info" / "preset_cheatsheet.json"

# Кэш загруженного справочника (ленивая загрузка, один раз за сессию)
_cache = None


def load_cheatsheet() -> dict:
    """Загружает справочник из JSON и кэширует в памяти модуля.

    Возвращает словарь со всеми разделами. При ошибке (файл не найден,
    невалидный JSON) возвращает пустой словарь и пишет предупреждение —
    приложение не должно падать из-за отсутствия справочника.
    """
    global _cache
    if _cache is not None:
        return _cache

    try:
        with open(_CHEATSHEET_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except FileNotFoundError:
        print(f"[WARN] Файл шпаргалки не найден: {_CHEATSHEET_PATH}")
        _cache = {}
    except json.JSONDecodeError as e:
        print(f"[WARN] Ошибка парсинга шпаргалки: {e}")
        _cache = {}

    return _cache


def get_sampler_mapping() -> dict:
    """Возвращает таблицу соответствий семплеров (раздел `sampler_mapping`).

    Формат: {"description": "...", "entries": [{"a1111_name": ..., "our_scheduler": ..., ...}, ...]}
    """
    return load_cheatsheet().get("sampler_mapping", {})


def get_parameter_glossary() -> dict:
    """Возвращает толковый словарь параметров (раздел `parameter_glossary`).

    Формат: {"scheduler": {"title": ..., "what_is": ..., "affects": ..., ...}, ...}
    """
    return load_cheatsheet().get("parameter_glossary", {})


def get_parameter_info(param_name: str) -> dict:
    """Возвращает объяснение конкретного параметра или пустой словарь.

    Используется (в будущем) для тултипов значков "?" рядом с полями.
    """
    return get_parameter_glossary().get(param_name, {})


def get_model_architectures() -> dict:
    """Возвращает рекомендации по архитектурам (раздел `model_architectures`)."""
    return load_cheatsheet().get("model_architectures", {})


def get_general_tips() -> list:
    """Возвращает список общих советов (раздел `general_tips`)."""
    return load_cheatsheet().get("general_tips", [])
