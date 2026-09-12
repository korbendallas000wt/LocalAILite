"""
Пресеты моделей: дефолтные параметры генерации для каждого типа модели.

Пресет хранится в реестре моделей (поле `default_preset` записи модели).
Если пресет не задан или содержит не все поля — недостающие дополняются
встроенными дефолтами для типа модели.

Структура пресета Диффузерс (покрывает все параметры панели настроек):
    scheduler, timestep_spacing, steps, cfg, width, height,
    seed, negative_prompt, strength

Структура пресета Олламы (параметры чата, привязанные к модели):
    temperature, top_p, max_tokens, timeout (-1 = глобальный)

Примечания:
- Стрим Олламы — глобальный, не входит в пресет (техническая настройка).
- Системный промпт Олламы — не входит в пресет (будет библиотека промптов).
- Таймаут Олламы: -1 = использовать глобальный из конфига;
  позже добавится автоподсказка по размеру модели.
"""

# Встроенные дефолты для Диффузерс
# Покрывают все параметры панели настроек диффузеров
DEFAULT_PRESET_DIFFUSERS = {
    "scheduler": "EulerDiscreteScheduler",
    "timestep_spacing": "leading",
    "steps": 30,
    "cfg": 7.5,
    "width": 1024,
    "height": 1024,
    "seed": -1,
    "negative_prompt": "",
    "strength": 0.75,
}

# Встроенные дефолты для Олламы
# Параметры чата, которые разумно привязать к модели
DEFAULT_PRESET_OLLAMA = {
    "temperature": 0.8,
    "top_p": 0.9,
    "max_tokens": 2048,
    "timeout": -1,         # -1 = не менять (оставить текущий)
    "system_prompt": "",   # "" = не менять (оставить текущий); работа без системного промпта — нонсенс,
                           # пустой пресет явно означает "не трогать текущий промпт"
}


def get_builtin_default(model_type: str) -> dict:
    """Возвращает встроенные дефолты для типа модели (копия, чтобы не менять оригинал).

    Args:
        model_type: "diffusers" или "ollama"

    Returns:
        dict с дефолтными параметрами; пустой словарь для неизвестного типа.
    """
    if model_type == "diffusers":
        return dict(DEFAULT_PRESET_DIFFUSERS)
    elif model_type == "ollama":
        return dict(DEFAULT_PRESET_OLLAMA)
    return {}


def get_effective_preset(config, model_id: str) -> dict:
    """Возвращает эффективный пресет модели: сохранённый из реестра, дополненный дефолтами.

    Приоритет:
    1. Встроенные дефолты для типа модели (база)
    2. Сохранённый пресет из реестра дополняет/переопределяет базу

    Это защищает от неполных пресетов: если пользователь сохранил только
    часть полей, остальные возьмутся из дефолтов.

    Args:
        config: объект Config
        model_id: идентификатор модели в реестре

    Returns:
        dict с параметрами пресета; пустой словарь если модель не найдена.
    """
    from core.models_registry import get_model_entry

    model = get_model_entry(config, model_id)
    if not model:
        return {}

    model_type = model.get("type", "")

    # База: встроенные дефолты для типа модели
    effective = get_builtin_default(model_type)

    # Сохранённый пресет дополняет базу
    saved = model.get("default_preset", {})
    if saved and isinstance(saved, dict):
        effective.update(saved)

    return effective


def save_preset(config, model_id: str, preset: dict) -> bool:
    """Сохраняет пресет модели в реестр.

    Обёртка над models_registry.set_model_preset для единообразия интерфейса.

    Args:
        config: объект Config
        model_id: идентификатор модели в реестре
        preset: словарь параметров пресета

    Returns:
        True при успехе, False если модель не найдена.
    """
    from core.models_registry import set_model_preset
    return set_model_preset(config, model_id, preset)
