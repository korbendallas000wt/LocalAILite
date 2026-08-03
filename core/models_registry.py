"""
Реестр моделей Diffusers.
Управляет соответствием "красивое имя ↔ путь к модели".
Автоматически сканирует папку моделей при старте.
"""
import os
import json
from utils.config import Config


def scan_models_folder(models_path: str) -> dict:
    """
    Сканирует папку моделей и возвращает словарь {display_name: path}.
    
    Формат имён:
    - HF cache: models--stabilityai--sdxl-base-1.0 → stabilityai/sdxl-base-1.0
    - Single-file: dreamshaper_xl_v7.safetensors → Dreamshaper Xl V7
    - Folder: sdxl-local → Sdxl Local
    """
    models = {}
    if not models_path or not os.path.exists(models_path):
        return models
    
    for item in os.listdir(models_path):
        item_path = os.path.join(models_path, item)
        
        # 1. HF cache формат
        if os.path.isdir(item_path) and item.startswith("models--"):
            # models--stabilityai--sdxl-base-1.0 → sdxl-base-1.0 (только имя модели)
            full_name = item[len("models--"):].replace("--", "/")
            display_name = full_name.split("/")[-1]
            # Ищем snapshots/{hash}/ — там лежит model_index.json
            snapshots_dir = os.path.join(item_path, "snapshots")
            if os.path.isdir(snapshots_dir):
                snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                                   if os.path.isdir(os.path.join(snapshots_dir, d))]
                if snapshot_hashes:
                    # Берём первый (обычно он один) snapshot
                    snapshot_path = os.path.join(snapshots_dir, snapshot_hashes[0])
                    models[display_name] = snapshot_path
                else:
                    # Fallback — корень HF cache
                    models[display_name] = item_path
            else:
                # Fallback — корень HF cache
                models[display_name] = item_path
        
        # 2. Single-file модели
        elif os.path.isfile(item_path):
            if item.endswith('.safetensors') or item.endswith('.ckpt'):
                name = os.path.splitext(item)[0]
                display_name = name.replace('_', ' ').replace('-', ' ').title()
                models[display_name] = item_path
        
        # 3. Распакованные модели (папки с model_index.json)
        elif os.path.isdir(item_path) and not item.startswith("models--"):
            if os.path.exists(os.path.join(item_path, "model_index.json")):
                display_name = item.replace('_', ' ').replace('-', ' ').title()
                models[display_name] = item_path
    
    # Разрешаем конфликты имён
    models = _resolve_name_conflicts(models)
    
    return models


def _resolve_name_conflicts(models: dict) -> dict:
    """Если несколько моделей дают одинаковое имя, добавляет суффикс (2), (3) и т.д."""
    name_count = {}
    resolved = {}
    
    for display_name, path in models.items():
        if display_name in name_count:
            name_count[display_name] += 1
            new_name = f"{display_name} ({name_count[display_name]})"
            resolved[new_name] = path
        else:
            name_count[display_name] = 1
            resolved[display_name] = path
    
    return resolved


def load_registry(config: Config) -> dict:
    """
    Загружает реестр из файла. Если файл не существует или устарел — пересоздаёт.
    """
    registry_path = config.get_models_registry_path()
    models_path = config.get_sdxl_models_path()
    
    need_rescan = False
    
    if not os.path.exists(registry_path):
        need_rescan = True
    else:
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
            if not _is_registry_up_to_date(registry, models_path):
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
    """Проверяет, актуален ли реестр (все пути существуют)."""
    for path in registry.values():
        if not os.path.exists(path):
            return False
    return True


def get_model_path_by_name(config: Config, display_name: str) -> str:
    """
    Возвращает путь к модели по красивому имени.
    Если не найдена — возвращает пустую строку.
    """
    registry = load_registry(config)
    return registry.get(display_name, "")
