#!/usr/bin/env python3
"""
core/models_registry.py — реестр моделей v3.0 (статус вычисляется).

Внутренняя структура (v3):
{
  "version": 3,
  "models": {
    "<model_id>": {
      "display_name": "Dreamshaper XL Turbo",
      "type": "diffusers",
      "packaging": "hf_cache",
      "source": {"kind": "discovered", "ref": "Lykon/dreamshaper-xl-v2-turbo"},
      "paths": {"installed": "/path/to/models--Lykon--dreamshaper-xl-v2-turbo"},
      "meta": {"size_gb": 6.5, "min_ram_gb": 16, "description": "..."},
      "validation": {"last_method": "fast", "last_result": "valid", "last_at": "..."},
      "added_at": "2026-09-05T12:00:00",
      "updated_at": "2026-09-05T14:30:00"
    }
  }
}

Публичный контракт (сохранён для совместимости):
  load_registry(config) -> {display_name: {path, full_name, type}}
  get_model_path_by_name(config, display_name) -> str
  list_available_models(config) -> {"ollama": [...], "diffusers": [...]}
  list_installed_ollama_models(config) -> [str]
  remove_model_from_registry(config, full_name) -> bool

Новые методы (для менеджера v3):
  reconcile_registry(config) -> dict  # сверка с диском, вычисление статусов
  list_all_models(config) -> list     # все модели с полной информацией
  get_model_status(model_id, config) -> str
  register_from_path(path, model_type, config) -> str
"""

import os
import json
from datetime import datetime
from utils.config import Config

# Маппинг известных моделей → короткие имена
KNOWN_MODELS = {
    "stable-diffusion-xl-base-1.0": "SDXL Base 1.0",
    "stable-diffusion-xl-refiner-1.0": "SDXL Refiner 1.0",
    "dreamshaper-xl-v2-turbo": "Dreamshaper XL Turbo",
    "juggernaut-xl-v9": "Juggernaut XL v9",
}


def _beautify_name(raw_name: str) -> str:
    """Преобразует техническое имя модели в читаемое."""
    if raw_name in KNOWN_MODELS:
        return KNOWN_MODELS[raw_name]
    return raw_name.replace("-", " ").replace("_", " ").title()


def _now_iso() -> str:
    """Текущее время в ISO формате."""
    return datetime.now().isoformat(timespec='seconds')


# ---------------------------------------------------------------------------
# Внутренние функции (v3)
# ---------------------------------------------------------------------------

def _load_registry_v3(config: Config) -> dict:
    """Читает реестр v3 из JSON. Возвращает {"version": 3, "models": {...}}.
    Если файл не существует или в старом формате — создаёт пустой.
    """
    from core.paths_manager import PathsManager
    pm = PathsManager()
    registry_path = config.get_models_registry_path()

    if not os.path.exists(registry_path):
        return {"version": 3, "models": {}}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": 3, "models": {}}

    # Проверка версии
    if not isinstance(data, dict) or data.get("version") != 3:
        # Старый формат или битый — создаём пустой
        return {"version": 3, "models": {}}

    if "models" not in data or not isinstance(data["models"], dict):
        return {"version": 3, "models": {}}

    return data


def _save_registry_v3(config: Config, registry_data: dict):
    """Сохраняет реестр v3 в JSON."""
    registry_path = config.get_models_registry_path()
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    try:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ModelsRegistry] Не удалось сохранить реестр: {e}")


def _scan_models_folder_v3(models_path: str) -> dict:
    """Сканирует папку моделей и возвращает dict для реестра v3.
    Находит HF cache, single-file, распакованные папки.
    НЕ проверяет .incomplete (это делает reconcile).
    """
    models = {}
    if not models_path or not os.path.exists(models_path):
        return models

    for item in os.listdir(models_path):
        item_path = os.path.join(models_path, item)

        # 1. HF cache формат: models--stabilityai--stable-diffusion-xl-base-1.0
        if os.path.isdir(item_path) and item.startswith("models--"):
            full_name = item[len("models--"):].replace("--", "/")
            raw_name = full_name.split("/")[-1]
            display_name = _beautify_name(raw_name)
            model_id = full_name.replace("/", "_").lower()

            models[model_id] = {
                "display_name": display_name,
                "type": "diffusers",
                "packaging": "hf_cache",
                "source": {"kind": "discovered", "ref": full_name},
                "paths": {"installed": item_path},
                "meta": {},
                "validation": {},
                "added_at": _now_iso(),
                "updated_at": _now_iso()
            }

        # 2. Single-file модели (.safetensors, .ckpt)
        elif os.path.isfile(item_path):
            if item.endswith('.safetensors') or item.endswith('.ckpt'):
                raw_name = os.path.splitext(item)[0]
                display_name = _beautify_name(raw_name)
                model_id = f"file_{raw_name.lower().replace(' ', '_')}"

                models[model_id] = {
                    "display_name": display_name,
                    "type": "diffusers",
                    "packaging": "file",
                    "source": {"kind": "discovered", "ref": item},
                    "paths": {"installed": item_path},
                    "meta": {},
                    "validation": {},
                    "added_at": _now_iso(),
                    "updated_at": _now_iso()
                }

        # 3. Распакованные модели (папки с model_index.json)
        elif os.path.isdir(item_path) and not item.startswith("models--"):
            if os.path.exists(os.path.join(item_path, "model_index.json")):
                display_name = _beautify_name(item)
                model_id = f"folder_{item.lower().replace(' ', '_')}"

                models[model_id] = {
                    "display_name": display_name,
                    "type": "diffusers",
                    "packaging": "folder",
                    "source": {"kind": "discovered", "ref": item},
                    "paths": {"installed": item_path},
                    "meta": {},
                    "validation": {},
                    "added_at": _now_iso(),
                    "updated_at": _now_iso()
                }

    return models


def reconcile_registry(config: Config) -> dict:
    """Сверка реестра с диском. Вызывается при открытии менеджера.

    Для каждой модели в реестре:
    - Проверяет существование paths.installed
    - Если путь исчез → validation.last_result = "missing"
    - Если путь есть → запускает быструю валидацию (validate_model_fast)
    - Обновляет validation.last_result и validation.last_at

    Сканирует папку моделей и добавляет найденные модели (source.kind = "discovered").

    Возвращает актуальный реестр v3.
    """
    from core.paths_manager import PathsManager
    from core.model_validator import validate_model_fast, validate_ollama_model

    pm = PathsManager()
    registry_data = _load_registry_v3(config)
    models_path = pm.get_path(config, "sdxl_models")
    ollama_models_path = pm.get_path(config, "ollama_models")

    # 1. Проверяем существующие модели в реестре
    for model_id, model_info in list(registry_data["models"].items()):
        installed_path = model_info.get("paths", {}).get("installed", "")

        if not installed_path or not os.path.exists(installed_path):
            # Путь исчез
            model_info["validation"] = {
                "last_method": "none",
                "last_result": "missing",
                "last_at": _now_iso()
            }
            model_info["updated_at"] = _now_iso()
            continue

        # Путь есть — быстрая валидация
        model_type = model_info.get("type")
        if model_type == "diffusers":
            result = validate_model_fast(installed_path)
        elif model_type == "ollama":
            # Для Ollama installed_path — это имя модели (например, "qwen2.5:3b")
            result = validate_ollama_model(installed_path, ollama_models_path)
        else:
            result = validate_model_fast(installed_path)

        model_info["validation"] = {
            "last_method": "fast",
            "last_result": "valid" if result.valid else "invalid",
            "last_at": _now_iso(),
            "errors": result.errors if not result.valid else []
        }
        model_info["updated_at"] = _now_iso()

    # 2. Сканируем папку моделей и добавляем найденные
    if models_path and os.path.exists(models_path):
        discovered = _scan_models_folder_v3(models_path)
        for model_id, model_info in discovered.items():
            if model_id not in registry_data["models"]:
                # Новая модель — добавляем и сразу валидируем
                installed_path = model_info["paths"]["installed"]
                result = validate_model_fast(installed_path)
                model_info["validation"] = {
                    "last_method": "fast",
                    "last_result": "valid" if result.valid else "invalid",
                    "last_at": _now_iso()
                }
                registry_data["models"][model_id] = model_info

    # 3. Сохраняем обновлённый реестр
    _save_registry_v3(config, registry_data)

    return registry_data


# ---------------------------------------------------------------------------
# Публичные функции (сохранённый контракт)
# ---------------------------------------------------------------------------

def load_registry(config: Config) -> dict:
    """Загружает реестр. КОНТРАКТ СОХРАНЁН.

    Returns:
        {display_name: {"path": str, "full_name": str, "type": str}}
        для совместимости с diffusers_settings_panel.py
    """
    # Сверяем с диском
    registry_data = reconcile_registry(config)

    # Конвертируем в старый формат
    result = {}
    for model_id, model_info in registry_data["models"].items():
        if model_info.get("type") != "diffusers":
            continue  # Только Diffusers для старого API

        display_name = model_info.get("display_name", model_id)
        installed_path = model_info.get("paths", {}).get("installed", "")
        full_name = model_info.get("source", {}).get("ref", "")
        packaging = model_info.get("packaging", "hf_cache")

        # Для hf_cache path ведёт на корень models--*,
        # но старый контракт ожидал snapshots/{hash}.
        # Поднимаем до snapshots/{hash} для совместимости.
        snapshot_path = installed_path
        if packaging == "hf_cache" and os.path.isdir(installed_path):
            snapshots_dir = os.path.join(installed_path, "snapshots")
            if os.path.isdir(snapshots_dir):
                snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                                   if os.path.isdir(os.path.join(snapshots_dir, d))]
                if snapshot_hashes:
                    snapshot_path = os.path.join(snapshots_dir, snapshot_hashes[0])

        result[display_name] = {
            "path": snapshot_path,
            "full_name": full_name,
            "type": packaging
        }

    return result


def get_model_path_by_name(config: Config, display_name: str) -> str:
    """Возвращает путь к модели по короткому имени. КОНТРАКТ СОХРАНЁН.

    Для hf_cache возвращает snapshots/{hash} (путь для from_pretrained),
    как в реестре v2.0. Делегирует в load_registry.
    """
    registry = load_registry(config)
    info = registry.get(display_name)
    if isinstance(info, dict):
        return info.get("path", "")
    return ""


def list_available_models(config: Config) -> dict:
    """Читает реестр доступных моделей из available_models.json.
    Если файл не существует — возвращает дефолтный список.
    """
    import copy

    AVAILABLE_MODELS_DEFAULTS = {
        "ollama": [
            {"name": "qwen2.5:3b", "source": "qwen2.5:3b", "size_gb": 2.1,
             "min_ram_gb": 8, "tag": "chat",
             "description": "Быстрая модель для чата, хорошее соотношение скорость/качество"},
            {"name": "llama3.1:8b", "source": "llama3.1:8b", "size_gb": 4.7,
             "min_ram_gb": 16, "tag": "chat",
             "description": "Универсальная модель от Meta, хорошее качество ответов"},
            {"name": "mistral:7b", "source": "mistral:7b", "size_gb": 4.1,
             "min_ram_gb": 16, "tag": "chat",
             "description": "Сбалансированная модель от Mistral AI"}
        ],
        "diffusers": [
            {"name": "SDXL Base 1.0", "source": "stabilityai/stable-diffusion-xl-base-1.0",
             "size_gb": 6.9, "min_ram_gb": 16, "tag": "image_gen", "packaging": "hf_cache",
             "description": "Базовая модель SDXL для генерации изображений 1024×1024"},
            {"name": "Dreamshaper XL Turbo", "source": "Lykon/dreamshaper-xl-v2-turbo",
             "size_gb": 6.5, "min_ram_gb": 16, "tag": "image_gen", "packaging": "hf_cache",
             "description": "Быстрая версия SDXL для ускоренной генерации"},
            {"name": "Juggernaut XL v9", "source": "RunDiffusion/Juggernaut-XL-v9",
             "size_gb": 6.8, "min_ram_gb": 16, "tag": "image_gen", "packaging": "hf_cache",
             "description": "Высококачественная модель для фотореалистичных изображений"}
        ]
    }

    registry_path = os.path.join(
        os.path.dirname(config.get_models_registry_path()),
        "available_models.json"
    )

    if os.path.exists(registry_path):
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ollama": data.get("ollama", []), "diffusers": data.get("diffusers", [])}
        except Exception:
            pass

    return copy.deepcopy(AVAILABLE_MODELS_DEFAULTS)


def list_installed_ollama_models(config: Config) -> list:
    """Возвращает список установленных Ollama моделей (теги вида 'model:tag').
    Сканирует папку manifests/ напрямую, не требует запущенного сервера.
    """
    from core.paths_manager import PathsManager
    pm = PathsManager()
    models_path = pm.get_path(config, "ollama_models")

    models = []
    if not models_path or not os.path.exists(models_path):
        return models

    library_path = os.path.join(models_path, "manifests", "registry.ollama.ai", "library")
    if not os.path.isdir(library_path):
        return models

    for model_name in os.listdir(library_path):
        model_path = os.path.join(library_path, model_name)
        if not os.path.isdir(model_path):
            continue
        for tag in os.listdir(model_path):
            tag_path = os.path.join(model_path, tag)
            if os.path.isfile(tag_path):
                models.append(f"{model_name}:{tag}")

    return models


def remove_model_from_registry(config: Config, full_name: str) -> bool:
    """Удаляет запись модели из реестра по full_name. КОНТРАКТ СОХРАНЁН."""
    registry_data = _load_registry_v3(config)

    model_id_to_remove = None
    for model_id, model_info in registry_data["models"].items():
        if model_info.get("source", {}).get("ref") == full_name:
            model_id_to_remove = model_id
            break

    if not model_id_to_remove:
        return False

    del registry_data["models"][model_id_to_remove]
    _save_registry_v3(config, registry_data)
    return True


# ---------------------------------------------------------------------------
# Новые методы (для менеджера v3)
# ---------------------------------------------------------------------------

def list_all_models(config: Config) -> list:
    """Возвращает все модели с полной информацией для нового менеджера.

    Returns:
        [{"model_id": str, "display_name": str, "type": str, "status": str, ...}, ...]
    """
    registry_data = reconcile_registry(config)
    result = []

    for model_id, model_info in registry_data["models"].items():
        validation = model_info.get("validation", {})
        last_result = validation.get("last_result", "unknown")

        # Вычисляем статус
        installed_path = model_info.get("paths", {}).get("installed", "")
        if not installed_path:
            status = "download"  # Нет пути — можно скачать
        elif last_result == "missing":
            status = "download"  # Путь исчез
        elif last_result == "invalid":
            status = "invalid"
        elif last_result == "valid":
            # Проверяем, в рабочей ли папке
            from core.paths_manager import PathsManager
            pm = PathsManager()
            models_path = pm.get_path(config, "sdxl_models")
            if models_path and installed_path.startswith(models_path):
                status = "installed"
            else:
                status = "valid"  # Валидна, но не в рабочей папке
        else:
            status = "downloaded"  # Есть на диске, но не проверена

        result.append({
            "model_id": model_id,
            "display_name": model_info.get("display_name", model_id),
            "type": model_info.get("type"),
            "packaging": model_info.get("packaging"),
            "status": status,
            "source": model_info.get("source", {}),
            "paths": model_info.get("paths", {}),
            "meta": model_info.get("meta", {}),
            "validation": validation,
            "added_at": model_info.get("added_at"),
            "updated_at": model_info.get("updated_at")
        })

    return result


def get_model_status(model_id: str, config: Config) -> str:
    """Вычисляет статус модели по model_id.

    Returns: "download" | "downloaded" | "valid" | "installed" | "invalid"
    """
    registry_data = reconcile_registry(config)
    model_info = registry_data["models"].get(model_id)

    if not model_info:
        return "download"

    validation = model_info.get("validation", {})
    last_result = validation.get("last_result", "unknown")
    installed_path = model_info.get("paths", {}).get("installed", "")

    if not installed_path:
        return "download"
    if last_result == "missing":
        return "download"
    if last_result == "invalid":
        return "invalid"
    if last_result == "valid":
        from core.paths_manager import PathsManager
        pm = PathsManager()
        models_path = pm.get_path(config, "sdxl_models")
        if models_path and installed_path.startswith(models_path):
            return "installed"
        return "valid"

    return "downloaded"


def register_from_path(path: str, model_type: str, config: Config) -> str:
    """Явная регистрация модели с диска.

    Args:
        path: Путь к модели (папка HF cache, single-file, или распакованная папка)
        model_type: "diffusers" или "ollama"
        config: Конфигурация

    Returns:
        model_id зарегистрированной модели или пустая строка при ошибке
    """
    from core.model_validator import validate_model_fast

    if not os.path.exists(path):
        return ""

    # Определяем packaging и full_name
    if os.path.isfile(path):
        packaging = "file"
        full_name = os.path.basename(path)
        raw_name = os.path.splitext(full_name)[0]
    elif os.path.isdir(path):
        if os.path.basename(path).startswith("models--"):
            packaging = "hf_cache"
            full_name = os.path.basename(path)[len("models--"):].replace("--", "/")
            raw_name = full_name.split("/")[-1]
        elif os.path.exists(os.path.join(path, "model_index.json")):
            packaging = "folder"
            full_name = os.path.basename(path)
            raw_name = full_name
        else:
            return ""
    else:
        return ""

    display_name = _beautify_name(raw_name)
    model_id = full_name.replace("/", "_").replace(" ", "_").lower()

    # Быстрая валидация
    result = validate_model_fast(path)

    registry_data = _load_registry_v3(config)
    registry_data["models"][model_id] = {
        "display_name": display_name,
        "type": model_type,
        "packaging": packaging,
        "source": {"kind": "local_path", "ref": path},
        "paths": {"installed": path},
        "meta": {},
        "validation": {
            "last_method": "fast",
            "last_result": "valid" if result.valid else "invalid",
            "last_at": _now_iso()
        },
        "added_at": _now_iso(),
        "updated_at": _now_iso()
    }

    _save_registry_v3(config, registry_data)
    return model_id
