"""
Менеджер чекпоинтов для Resume генерации.
Сохраняет состояние генерации (latents, scheduler, generator) и метаданные.

Примечание: torch импортируется лениво внутри функций, которые работают с PT-файлами.
Функции, работающие только с JSON (load_archived_metadata, list_archived_checkpoints,
archive_checkpoint и т.д.), не требуют torch и могут вызываться из UI.
"""
import os
import json
from datetime import datetime

# Путь к папке чекпоинтов: data/checkpoints/ относительно корня проекта
CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "checkpoints"
)


def save_checkpoint(latents, scheduler, generator, params, current_step, remaining_timesteps, actual_seed=None, last_preview_path=""):
    """
    Сохраняет чекпоинт генерации.
    
    Args:
        latents: torch.Tensor - текущее состояние латентов
        scheduler: scheduler объект - для сохранения внутреннего состояния
        generator: torch.Generator - для восстановления детерминированности
        params: dict - параметры генерации (prompt, model, seed, etc.)
        current_step: int - текущий шаг (сколько шагов уже сделано)
        remaining_timesteps: list - оставшиеся timesteps для продолжения
        actual_seed: int - реальный seed (если был сгенерирован случайный)
    """
    import torch  # ленивый импорт — нужен только здесь
    
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    
    # JSON с метаданными (читаемый формат)
    json_data = {
        "prompt": params["prompt"],
        "negative_prompt": params.get("negative_prompt", ""),
        "model": params["model"],
        "scheduler": params["scheduler"],
        "seed": actual_seed if actual_seed is not None else params["seed"],
        "total_steps": params["total_steps"],
        "current_step": current_step,
        "width": params["width"],
        "height": params["height"],
        "cfg": params["cfg"],
        "device": params["device"],
        "remaining_timesteps": [
            t.item() if torch.is_tensor(t) else t
            for t in remaining_timesteps
        ],
        "preview_every": params.get("preview_every", 0),
        "preview_start": params.get("preview_start", 1),
        "last_preview_path": last_preview_path
    }
    
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # PT с torch-объектами (бинарный формат)
    torch_data = {
        "latents": latents.cpu(),
        "scheduler_state": scheduler.__dict__.copy(),
        "generator_state": generator.get_state()
    }
    
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    torch.save(torch_data, pt_path)


def load_checkpoint():
    """
    Загружает активный чекпоинт (JSON + PT).
    Используется в generate_diffusers.py при resume.
    
    Returns:
        tuple: (json_data, torch_data) или (None, None) если чекпоинт не найден
    """
    import torch  # ленивый импорт
    
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    
    if not os.path.exists(json_path) or not os.path.exists(pt_path):
        return None, None
    
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    # ИСПРАВЛЕНО: weights_only=False для PyTorch 2.6+
    torch_data = torch.load(pt_path, map_location="cpu", weights_only=False)
    
    return json_data, torch_data


def checkpoint_exists():
    """
    Проверяет наличие активного чекпоинта.
    
    Returns:
        bool: True если чекпоинт существует
    """
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    return os.path.exists(json_path) and os.path.exists(pt_path)


def delete_checkpoint():
    """Удаляет активный чекпоинт (после успешного завершения генерации)"""
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    
    if os.path.exists(json_path):
        os.remove(json_path)
    if os.path.exists(pt_path):
        os.remove(pt_path)


def get_checkpoint_info():
    """
    Возвращает краткую информацию об активном чекпоинте (для UI).
    
    Returns:
        dict или None
    """
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    
    if not os.path.exists(json_path):
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "prompt": data.get("prompt", "")[:50] + "..." if len(data.get("prompt", "")) > 50 else data.get("prompt", ""),
            "model": os.path.basename(data.get("model", "")),
            "current_step": data.get("current_step", 0),
            "total_steps": data.get("total_steps", 0),
            "seed": data.get("seed", -1),
            "width": data.get("width", 0),
            "height": data.get("height", 0)
        }
    except Exception:
        return None


def archive_checkpoint():
    """
    Переименовывает активный чекпоинт в архивный с timestamp.
    Вызывается после завершения или остановки генерации.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_src = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_src = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    json_dst = os.path.join(CHECKPOINT_DIR, f"{timestamp}.json")
    pt_dst = os.path.join(CHECKPOINT_DIR, f"{timestamp}.pt")
    
    if os.path.exists(json_src):
        os.rename(json_src, json_dst)
    if os.path.exists(pt_src):
        os.rename(pt_src, pt_dst)


def list_archived_checkpoints():
    """
    Возвращает список архивных чекпоинтов (отсортированных по времени, новые первыми).
    
    Returns:
        list[dict]: [{"timestamp": str, "filename": str, "display_name": str}, ...]
    """
    checkpoints = []
    
    if not os.path.exists(CHECKPOINT_DIR):
        return checkpoints
    
    for filename in os.listdir(CHECKPOINT_DIR):
        if filename.endswith('.json') and filename != 'checkpoint.json':
            timestamp = filename[:-5]  # убираем .json
            # Формат: 2026-07-05_14-30-45 → 2026-07-05 14:30:45
            display_name = f"{timestamp[:10].replace('-', '.')} {timestamp[11:19].replace('-', ':')}"
            checkpoints.append({
                "timestamp": timestamp,
                "filename": filename,
                "display_name": display_name
            })
    
    # Сортируем по timestamp (новые первыми)
    return sorted(checkpoints, key=lambda x: x["timestamp"], reverse=True)


def load_archived_metadata(filename):
    """
    Загружает ТОЛЬКО метаданные (JSON) из архивного чекпоинта.
    НЕ требует torch — безопасна для вызова из UI.
    
    Args:
        filename: имя файла (например, "2026-07-05_14-30-45.json")
    
    Returns:
        dict или None
    """
    json_path = os.path.join(CHECKPOINT_DIR, filename)
    
    if not os.path.exists(json_path):
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_archived_checkpoint(filename):
    """
    Загружает полный архивный чекпоинт (JSON + PT).
    ТРЕБУЕТ torch — используется только в generate_diffusers.py.
    
    Args:
        filename: имя файла (например, "2026-07-05_14-30-45.json")
    
    Returns:
        tuple: (json_data, torch_data) или (None, None) если не найден
    """
    import torch  # ленивый импорт
    
    json_path = os.path.join(CHECKPOINT_DIR, filename)
    pt_path = json_path.replace('.json', '.pt')
    
    if not os.path.exists(json_path) or not os.path.exists(pt_path):
        return None, None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        
        # ИСПРАВЛЕНО: weights_only=False для PyTorch 2.6+
        torch_data = torch.load(pt_path, map_location="cpu", weights_only=False)
        
        return json_data, torch_data
    except Exception:
        return None, None
