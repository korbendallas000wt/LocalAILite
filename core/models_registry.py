"""
Реестр моделей Diffusers (v2.0).
Управляет соответствием "короткое имя ↔ полная информация о модели".
Автоматически сканирует папку моделей при старте.

Формат реестра:
{
    "SDXL Base 1.0": {
        "path": "/path/to/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/{hash}",
        "full_name": "stabilityai/stable-diffusion-xl-base-1.0",
        "type": "hf_cache"
    }
}

Типы: hf_cache | file | folder
"""
import os
import json
from utils.config import Config

# Маппинг известных моделей → короткие имена
KNOWN_MODELS = {
    "stable-diffusion-xl-base-1.0": "SDXL Base 1.0",
    "stable-diffusion-xl-refiner-1.0": "SDXL Refiner 1.0",
    "dreamshaper-xl-v2-turbo": "Dreamshaper XL Turbo",
    "juggernaut-xl-v9": "Juggernaut XL v9",
}


def _beautify_name(raw_name: str) -> str:
    """Преобразует техническое имя модели в читаемое.
    Сначала проверяет KNOWN_MODELS, потом дефолтное преобразование.
    """
    if raw_name in KNOWN_MODELS:
        return KNOWN_MODELS[raw_name]
    # Заменяем дефисы и подчёркивания на пробелы, делаем title case
    return raw_name.replace("-", " ").replace("_", " ").title()


def scan_models_folder(models_path: str) -> dict:
    """Сканирует папку моделей и возвращает реестр v2.0.
    Returns:
        {short_name: {"path": str, "full_name": str, "type": str}}
    """
    models = {}
    if not models_path or not os.path.exists(models_path):
        return models

    for item in os.listdir(models_path):
        item_path = os.path.join(models_path, item)

        # 1. HF cache формат: models--stabilityai--stable-diffusion-xl-base-1.0
        if os.path.isdir(item_path) and item.startswith("models--"):
            # models--stabilityai--stable-diffusion-xl-base-1.0 → stabilityai/stable-diffusion-xl-base-1.0
            full_name = item[len("models--"):].replace("--", "/")
            raw_name = full_name.split("/")[-1]
            display_name = _beautify_name(raw_name)

            # Ищем snapshots/{hash}/ — там лежит model_index.json
            snapshots_dir = os.path.join(item_path, "snapshots")
            model_path = item_path  # fallback — корень HF cache
            if os.path.isdir(snapshots_dir):
                snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                                   if os.path.isdir(os.path.join(snapshots_dir, d))]
                if snapshot_hashes:
                    model_path = os.path.join(snapshots_dir, snapshot_hashes[0])

            models[display_name] = {
                "path": model_path,
                "full_name": full_name,
                "type": "hf_cache"
            }

        # 2. Single-file модели (.safetensors, .ckpt)
        elif os.path.isfile(item_path):
            if item.endswith('.safetensors') or item.endswith('.ckpt'):
                raw_name = os.path.splitext(item)[0]
                display_name = _beautify_name(raw_name)
                models[display_name] = {
                    "path": item_path,
                    "full_name": item,
                    "type": "file"
                }

        # 3. Распакованные модели (папки с model_index.json)
        elif os.path.isdir(item_path) and not item.startswith("models--"):
            if os.path.exists(os.path.join(item_path, "model_index.json")):
                display_name = _beautify_name(item)
                models[display_name] = {
                    "path": item_path,
                    "full_name": item,
                    "type": "folder"
                }

    # Разрешаем конфликты имён
    models = _resolve_name_conflicts(models)
    return models


def _resolve_name_conflicts(models: dict) -> dict:
    """Если несколько моделей дают одинаковое имя, добавляет суффикс (2), (3)."""
    name_count = {}
    resolved = {}
    for display_name, info in models.items():
        if display_name in name_count:
            name_count[display_name] += 1
            new_name = f"{display_name} ({name_count[display_name]})"
            resolved[new_name] = info
        else:
            name_count[display_name] = 1
            resolved[display_name] = info
    return resolved


def load_registry(config: Config) -> dict:
    """Загружает реестр из файла. Если файл не существует, устарел
    или в старом формате — пересоздаёт.
    Использует PathsManager для получения эффективного пути
    (пустой путь → дефолт).
    """
    from core.paths_manager import PathsManager
    pm = PathsManager()
    registry_path = config.get_models_registry_path()
    models_path = pm.get_path(config, "sdxl_models")
    need_rescan = False

    if not os.path.exists(registry_path):
        need_rescan = True
    else:
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
            # Пустой реестр — всегда пересоздаём (возможно, путь был неправильный)
            if not registry:
                need_rescan = True
            # Проверяем формат: значения должны быть dict с ключом "path"
            elif not isinstance(next(iter(registry.values())), dict):
                need_rescan = True  # Старый формат (строки вместо dict)
            elif not _is_registry_up_to_date(registry, models_path):
                need_rescan = True
        except Exception:
            need_rescan = True

    if need_rescan:
        registry = scan_models_folder(models_path)
        save_registry(config, registry)

    return registry


def save_registry(config: Config, registry: dict):
    """Сохраняет реестр в файл."""
    registry_path = config.get_models_registry_path()
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    try:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ModelsRegistry] Не удалось сохранить реестр: {e}")


def _is_registry_up_to_date(registry: dict, models_path: str) -> bool:
    """Проверяет, актуален ли реестр.
    Условия:
    1. Все пути из реестра существуют
    2. Все пути находятся ВНУТРИ текущего models_path
       (если пользователь сменил папку моделей — реестр неактуален)
    """
    if not models_path:
        return False
    models_path_norm = os.path.normpath(models_path)
    for info in registry.values():
        path = info.get("path", "") if isinstance(info, dict) else info
        if not path or not os.path.exists(path):
            return False
        # Проверяем, что путь находится внутри models_path
        path_norm = os.path.normpath(path)
        if not path_norm.startswith(models_path_norm + os.sep) and path_norm != models_path_norm:
            return False
    return True


def get_model_path_by_name(config: Config, display_name: str) -> str:
    """Возвращает путь к модели по короткому имени.
    Если не найдена — возвращает пустую строку.
    """
    registry = load_registry(config)
    info = registry.get(display_name)
    if isinstance(info, dict):
        return info.get("path", "")
    return ""


def get_model_info_by_name(config: Config, display_name: str) -> dict:
    """Возвращает полную информацию о модели по короткому имени.
    Returns:
        {"path": str, "full_name": str, "type": str} или пустой dict
    """
    registry = load_registry(config)
    info = registry.get(display_name)
    if isinstance(info, dict):
        return info
    return {}
