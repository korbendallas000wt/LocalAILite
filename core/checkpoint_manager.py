"""
Менеджер чекпоинтов для Resume генерации.
Работает с папками истории data/diffusers/history/{timestamp}/.
Каждая папка содержит:
  - step_NNNN.pt  — латенты на каждом шаге
  - step_NNNN.json — метаданные шага (step, timestep, seed)
  - metadata.json — общие параметры генерации
"""
import os
import json

# Путь к папке истории: data/history/
HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "diffusers", "history"
)


def load_step_metadata(history_dir: str, step_filename: str) -> dict:
    """
    Загружает метаданные конкретного шага (step_NNNN.json).
    Args:
        history_dir: путь к папке истории
        step_filename: имя файла (например, "step_0015.json")
    Returns:
        dict или None
    """
    json_path = os.path.join(history_dir, step_filename)
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_generation_metadata(history_dir: str) -> dict:
    """
    Загружает общие метаданные генерации (metadata.json).
    Args:
        history_dir: путь к папке истории
    Returns:
        dict или None
    """
    json_path = os.path.join(history_dir, "metadata.json")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_step_latents(history_dir: str, step_filename: str):
    """
    Загружает латенты из step_NNNN.pt.
    ТРЕБУЕТ torch — используется только в generate_diffusers.py.
    Args:
        history_dir: путь к папке истории
        step_filename: имя файла (например, "step_0015.pt")
    Returns:
        torch.Tensor или None
    """
    import torch
    pt_path = os.path.join(history_dir, step_filename)
    if not os.path.exists(pt_path):
        return None
    try:
        data = torch.load(pt_path, map_location="cpu", weights_only=False)
        return data.get("latents")
    except Exception:
        return None


def load_step_full(history_dir: str, step_filename: str) -> dict:
    """
    Загружает полный чекпоинт из step_NNNN.pt.
    Включает: latents, scheduler_state, generator_state.
    
    Args:
        history_dir: путь к папке истории
        step_filename: имя файла (например, "step_0015.pt")
    Returns:
        dict с ключами "latents", "scheduler_state", "generator_state" или None
    """
    import torch
    pt_path = os.path.join(history_dir, step_filename)
    if not os.path.exists(pt_path):
        return None
    try:
        data = torch.load(pt_path, map_location="cpu", weights_only=False)
        # Проверяем, что это полный чекпоинт (не старый формат)
        if "latents" not in data:
            return None
        return data
    except Exception as e:
        print(f"[CheckpointManager] Ошибка загрузки {pt_path}: {e}")
        return None


def list_steps_in_history(history_dir: str) -> list[dict]:
    """
    Возвращает список шагов в папке истории (отсортированных по номеру).
    Args:
        history_dir: путь к папке истории
    Returns:
        list[dict]: [{"step": int, "pt_file": str, "json_file": str}, ...]
    """
    steps = []
    if not os.path.exists(history_dir):
        return steps
    for filename in os.listdir(history_dir):
        if filename.startswith("step_") and filename.endswith(".pt"):
            step_num = int(filename.replace("step_", "").replace(".pt", ""))
            json_file = filename.replace(".pt", ".json")
            steps.append({
                "step": step_num,
                "pt_file": filename,
                "json_file": json_file
            })
    return sorted(steps, key=lambda x: x["step"])
