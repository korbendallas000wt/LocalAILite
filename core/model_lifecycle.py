"""
Жизненный цикл моделей (core/model_lifecycle.py).

Удаление и проверка валидности установленных моделей.
Отдельный модуль, чтобы не мешать логику скачивания (model_downloader.py)
и логику удаления/проверки (SRP).
"""
import os
import shutil
import subprocess
import socket
import time


def _is_ollama_server_running() -> bool:
    """Проверяет, запущен ли Ollama сервер на порту 11434."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 11434))
        sock.close()
        return result == 0
    except Exception:
        return False


def _start_ollama_server(ollama_bin: str, models_path: str = ""):
    """Запускает Ollama сервер в фоне. Возвращает Popen-объект."""
    env = os.environ.copy()
    if models_path:
        env["OLLAMA_MODELS"] = models_path
    proc = subprocess.Popen(
        [ollama_bin, "serve"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env
    )
    return proc


def _wait_ollama_ready(timeout: int = 30) -> bool:
    """Ждёт, пока Ollama сервер станет доступен на порту 11434."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_ollama_server_running():
            return True
        time.sleep(0.5)
    return False


def delete_ollama_model(model_name: str, config) -> dict:
    """Удаляет модель Ollama через 'ollama rm'.

    Args:
        model_name: Имя модели в формате 'model:tag' (например, 'qwen2.5:3b').
        config: Конфигурация приложения.

    Returns:
        {"success": bool, "message": str}

    Контракт: Ollama сервер после операции остаётся жить (не останавливается).
    Если сервер был выключен — запускаем перед удалением и оставляем.
    """
    from core.paths_manager import PathsManager
    pm = PathsManager()
    ollama_bin = pm.get_path(config, "ollama_binary")
    models_path = pm.get_path(config, "ollama_models")

    if not ollama_bin or not os.path.exists(ollama_bin):
        return {"success": False, "message": f"Бинарник Ollama не найден: {ollama_bin}"}

    # Запускаем сервер, если не запущен (ollama rm требует работающий сервер)
    if not _is_ollama_server_running():
        _start_ollama_server(ollama_bin, models_path)
        if not _wait_ollama_ready(timeout=30):
            return {"success": False, "message": "Ollama сервер не запустился за 30 секунд"}

    # Выполняем ollama rm
    env = os.environ.copy()
    if models_path:
        env["OLLAMA_MODELS"] = models_path

    try:
        result = subprocess.run(
            [ollama_bin, "rm", model_name],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Таймаут удаления модели (60 сек)"}
    except Exception as e:
        return {"success": False, "message": f"Ошибка запуска ollama rm: {e}"}

    if result.returncode == 0:
        return {"success": True, "message": f"Модель {model_name} удалена"}
    else:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка"
        return {"success": False, "message": f"ollama rm завершился с кодом {result.returncode}: {error_msg}"}


def delete_diffusers_model(full_name: str, config) -> dict:
    """Удаляет модель Diffusers: папку на диске + запись из реестра.

    Args:
        full_name: HF repo id (например, 'stabilityai/stable-diffusion-xl-base-1.0').
        config: Конфигурация приложения.

    Returns:
        {"success": bool, "message": str}
    """
    from core.models_registry import load_registry, remove_model_from_registry

    registry = load_registry(config)

    # Ищем запись по full_name
    model_path = None
    display_name = None
    for name, info in registry.items():
        if isinstance(info, dict) and info.get("full_name") == full_name:
            model_path = info.get("path")
            display_name = name
            break

    if not model_path or not display_name:
        return {"success": False, "message": f"Модель {full_name} не найдена в реестре"}

    # Для HF cache формата путь ведёт на snapshots/{hash} — нужно удалить
    # корень models--{org}--{name} (два уровня выше).
    # Пример: /path/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/{hash}
    #   → удалить нужно: /path/models--stabilityai--stable-diffusion-xl-base-1.0
    actual_delete_path = model_path

    if "snapshots" in model_path:
        parts = model_path.split(os.sep)
        try:
            snap_idx = parts.index("snapshots")
            if snap_idx >= 1:
                actual_delete_path = os.sep.join(parts[:snap_idx])
        except ValueError:
            pass

    if not os.path.exists(actual_delete_path):
        return {"success": False, "message": f"Путь модели не существует: {actual_delete_path}"}

    try:
        if os.path.isdir(actual_delete_path):
            shutil.rmtree(actual_delete_path)
        else:
            os.remove(actual_delete_path)
    except Exception as e:
        return {"success": False, "message": f"Ошибка удаления файлов: {e}"}

    # Удаляем запись из реестра
    if not remove_model_from_registry(config, full_name):
        return {"success": False, "message": f"Файлы удалены, но не удалось обновить реестр"}

    return {"success": True, "message": f"Модель {display_name} удалена"}


def validate_installed_model(model_name_or_path: str, section: str, config) -> dict:
    """Синхронная проверка целостности установленной модели.

    Args:
        model_name_or_path: Для Ollama — имя модели ('qwen2.5:3b').
                           Для Diffusers — путь к модели или HF repo id.
        section: "ollama" или "diffusers".
        config: Конфигурация приложения.

    Returns:
        {"success": bool, "valid": bool, "errors": list, "warnings": list}
    """
    from core.model_validator import validate_ollama_model, validate_model

    if section == "ollama":
        from core.paths_manager import PathsManager
        pm = PathsManager()
        models_path = pm.get_path(config, "ollama_models")
        try:
            result = validate_ollama_model(model_name_or_path, models_path)
            return {
                "success": True,
                "valid": result.valid,
                "errors": result.errors,
                "warnings": result.warnings
            }
        except Exception as e:
            return {"success": False, "valid": False, "errors": [str(e)], "warnings": []}

    elif section == "diffusers":
        # Для Diffusers нужен путь к модели
        model_path = model_name_or_path

        # Если передан HF repo id — ищем путь в реестре
        if "/" in model_name_or_path and not os.path.exists(model_name_or_path):
            from core.models_registry import load_registry
            registry = load_registry(config)
            for info in registry.values():
                if isinstance(info, dict) and info.get("full_name") == model_name_or_path:
                    model_path = info.get("path", "")
                    break


        # Для HF cache путь может вести на snapshots/{hash} — поднимаем до корня
        # Пример: /path/models--org--name/snapshots/{hash}
        #   → нужно: /path/models--org--name
        if "snapshots" in model_path:
            parts = model_path.split(os.sep)
            try:
                snap_idx = parts.index("snapshots")
                if snap_idx >= 1:
                    model_path = os.sep.join(parts[:snap_idx])
            except ValueError:
                pass

        if not model_path or not os.path.exists(model_path):
            return {
                "success": False,
                "valid": False,
                "errors": [f"Путь модели не найден: {model_name_or_path}"],
                "warnings": []
            }

        try:
            result = validate_model(model_path)
            return {
                "success": True,
                "valid": result.valid,
                "errors": result.errors,
                "warnings": result.warnings
            }
        except Exception as e:
            return {"success": False, "valid": False, "errors": [str(e)], "warnings": []}

    return {"success": False, "valid": False, "errors": [f"Неизвестная секция: {section}"], "warnings": []}
