"""
Менеджер истории генерации.
Сохраняет PNG на каждом шаге в data/history/{timestamp}/
"""
import os
import json
from datetime import datetime

# Путь к папке истории: data/history/
HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "history"
)


def create_history_folder() -> str:
    """
    Создаёт папку для новой генерации с timestamp.
    Returns:
        str: путь к созданной папке
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    history_path = os.path.join(HISTORY_DIR, timestamp)
    os.makedirs(history_path, exist_ok=True)
    return history_path


def save_metadata(history_dir: str, params: dict):
    """
    Сохраняет метаданные генерации в metadata.json
    Args:
        history_dir: путь к папке истории
        params: dict с параметрами генерации
    """
    metadata_path = os.path.join(history_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)


def save_step_image(history_dir: str, step: int, image_path: str):
    """
    Копирует PNG превью в папку истории с именем step_{N:04d}.png
    Args:
        history_dir: путь к папке истории
        step: номер шага
        image_path: путь к исходному PNG (из previews/)
    """
    import shutil
    step_filename = f"step_{step:04d}.png"
    dest_path = os.path.join(history_dir, step_filename)
    if os.path.exists(image_path):
        shutil.copy2(image_path, dest_path)


def list_history() -> list[dict]:
    """
    Возвращает список всех историй (отсортированных по времени, новые первыми).
    Returns:
        list[dict]: [{"timestamp": str, "path": str, "display_name": str}, ...]
    """
    histories = []
    if not os.path.exists(HISTORY_DIR):
        return histories
    
    for item in os.listdir(HISTORY_DIR):
        item_path = os.path.join(HISTORY_DIR, item)
        if os.path.isdir(item_path):
            # Формат: 2026-07-05_14-30-45 → 2026-07-05 14:30:45
            display_name = f"{item[:10].replace('-', '.')} {item[11:19].replace('-', ':')}"
            histories.append({
                "timestamp": item,
                "path": item_path,
                "display_name": display_name
            })
    
    # Сортируем по timestamp (новые первыми)
    return sorted(histories, key=lambda x: x["timestamp"], reverse=True)


def delete_history(history_dir: str):
    """
    Удаляет папку истории
    Args:
        history_dir: путь к папке истории
    """
    import shutil
    if os.path.exists(history_dir):
        shutil.rmtree(history_dir)


def get_history_size_mb(history_dir: str) -> float:
    """
    Возвращает размер папки истории в MB
    Args:
        history_dir: путь к папке истории
    Returns:
        float: размер в MB
    """
    total_size = 0
    if os.path.exists(history_dir):
        for dirpath, dirnames, filenames in os.walk(history_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)
