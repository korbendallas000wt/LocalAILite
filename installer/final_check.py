"""
installer/final_check.py — единый модуль глубоких проверок перед вердиктом.

Запускается после шага 8 (скачивание моделей). Проверяет:
1. SDXL окружение (импорт torch/diffusers, numpy) — 30-60 сек на старом CPU
2. SDXL модели (целостность файлов)
3. Ollama сервер + модели (регистрация в сервере)

Время выполнения: 1-2 минуты. Идемпотентен: можно запускать повторно.
Без кэширования — инсталлер запускается по причинам, не регулярно.
"""

import os
import sys
import subprocess
import time

# Добавляем корень проекта в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class FinalCheck:
    """Единый модуль глубоких проверок перед вердиктом инсталлера."""

    def __init__(self, progress=None):
        """
        Args:
            progress: callback(current, total, message) для индикатора прогресса
        """
        self.progress = progress or (lambda cur, tot, msg: None)

    def run(self, features: dict) -> dict:
        """Запускает все глубокие проверки.
        
        Args:
            features: {"ollama": True, "sdxl": True, "image_prep": True}
        
        Returns:
            {
                "sdxl_env": {"ok": True, "message": "...", "details": "..."},
                "sdxl_models": {"ok": True, "message": "...", "count": 1},
                "ollama": {"ok": True, "message": "...", "models": [...]},
                "all_ok": True
            }
        """
        results = {}
        
        # Считаем количество проверок для прогресса
        checks = []
        if features.get("sdxl"):
            checks.append(("sdxl_env", "SDXL окружение (импорт torch/diffusers)..."))
            checks.append(("sdxl_models", "SDXL модели (целостность файлов)..."))
        if features.get("ollama"):
            checks.append(("ollama", "Ollama сервер и модели..."))
        
        total = len(checks)
        
        for i, (key, message) in enumerate(checks, 1):
            self.progress(i, total, message)
            start_time = time.time()
            
            if key == "sdxl_env":
                results[key] = self._check_sdxl_env_deep()
            elif key == "sdxl_models":
                results[key] = self._check_sdxl_models_deep()
            elif key == "ollama":
                results[key] = self._check_ollama_deep()
            
            elapsed = time.time() - start_time
            results[key]["elapsed"] = round(elapsed, 1)

        # Итог
        results["all_ok"] = all(
            r.get("ok", False) for r in results.values() if isinstance(r, dict) and "ok" in r
        )

        return results

    def _check_sdxl_env_deep(self) -> dict:
        """Глубокая проверка SDXL venv: импорт torch/diffusers, проверка numpy."""
        try:
            from utils.config import Config
            config = Config()
            venv_path = config.get_sdxl_venv_path()
            python_path = os.path.join(venv_path, "bin", "python")

            if not os.path.exists(python_path):
                return {
                    "ok": False,
                    "message": "SDXL venv не найден",
                    "action": "Запустите инсталлер повторно"
                }

            # Используем package_validator для глубокой проверки
            try:
                from core.package_validator import verify_critical_imports, check_numpy_version
            except ImportError:
                from package_validator import verify_critical_imports, check_numpy_version

            # Проверка критических пакетов (torch, diffusers)
            validation = verify_critical_imports(python_path)
            if not validation.valid:
                return {
                    "ok": False,
                    "message": f"Критические пакеты не работают: {'; '.join(validation.errors[:2])}",
                    "action": "Переустановить SDXL venv (шаг 7)"
                }

            # Проверка numpy (критично для старых CPU)
            numpy_validation = check_numpy_version(python_path)
            if not numpy_validation.valid:
                return {
                    "ok": False,
                    "message": f"numpy не работает: {'; '.join(numpy_validation.errors[:2])}",
                    "action": "Переустановить SDXL venv (шаг 7)"
                }

            return {
                "ok": True,
                "message": "torch, diffusers, numpy работают корректно",
                "details": f"torch {validation.package_versions.get('torch', '?')}, numpy {numpy_validation.package_versions.get('numpy', '?')}"
            }

        except Exception as e:
            return {
                "ok": False,
                "message": f"Ошибка проверки SDXL окружения: {e}",
                "action": "Запустите инсталлер повторно"
            }

    def _check_sdxl_models_deep(self) -> dict:
        """Глубокая проверка SDXL моделей: целостность файлов."""
        try:
            from utils.config import Config
            config = Config()
            models_path = config.get_sdxl_models_path()

            if not os.path.exists(models_path):
                return {
                    "ok": False,
                    "message": "Папка SDXL моделей не найдена",
                    "action": "Запустите инсталлер повторно (шаг 8)"
                }

            # Используем model_validator для проверки
            try:
                from core.model_validator import validate_model
            except ImportError:
                from model_validator import validate_model

            invalid_models = []
            models_count = 0

            # Правильная логика подсчёта моделей (как в path_validator)
            for item in os.listdir(models_path):
                item_path = os.path.join(models_path, item)
                is_model = False

                # 1. Одиночные файлы .safetensors / .ckpt
                if os.path.isfile(item_path):
                    if item.endswith('.safetensors') or item.endswith('.ckpt'):
                        is_model = True

                # 2. HF cache папки (models--org--model-name)
                elif os.path.isdir(item_path) and item.startswith("models--"):
                    is_model = True

                # 3. Распакованные модели (папки с model_index.json)
                elif os.path.isdir(item_path):
                    if os.path.exists(os.path.join(item_path, "model_index.json")):
                        is_model = True

                # Если это модель — проверяем
                if is_model:
                    models_count += 1
                    validation = validate_model(item_path)
                    if not validation.valid:
                        invalid_models.append(item)

            if models_count == 0:
                return {
                    "ok": False,
                    "message": "SDXL модели не найдены",
                    "action": "Запустите инсталлер повторно (шаг 8)"
                }

            if invalid_models:
                return {
                    "ok": False,
                    "message": f"Повреждённые модели: {', '.join(invalid_models[:3])}",
                    "action": "Перекачайте модели (шаг 8)"
                }

            return {
                "ok": True,
                "message": f"SDXL модели целы ({models_count} шт.)",
                "count": models_count
            }

        except Exception as e:
            return {
                "ok": False,
                "message": f"Ошибка проверки SDXL моделей: {e}",
                "action": "Запустите инсталлер повторно"
            }

    def _check_ollama_deep(self) -> dict:
        """Глубокая проверка Ollama: сервер + регистрация моделей."""
        try:
            from utils.config import Config
            config = Config()
            ollama_bin = config.get_ollama_binary_path()

            if not os.path.exists(ollama_bin):
                return {
                    "ok": False,
                    "message": "Бинарник Ollama не найден",
                    "action": "Запустите инсталлер повторно (шаг 6)"
                }

            # Проверяем, запущен ли сервер
            server_proc = None
            server_started_by_us = False
            models_path = config.get("ollama/models_path", "")

            if not self._is_ollama_running():
                # Запускаем сервер для проверки
                env = os.environ.copy()
                if models_path:
                    env["OLLAMA_MODELS"] = models_path

                server_proc = subprocess.Popen(
                    [ollama_bin, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env
                )
                server_started_by_us = True

                # Ждём запуска
                if not self._wait_ollama_ready(timeout=15):
                    server_proc.terminate()
                    return {
                        "ok": False,
                        "message": "Ollama сервер не запустился за 15 секунд",
                        "action": "Проверьте бинарник Ollama"
                    }

            try:
                # Проверяем список моделей через ollama list
                env = os.environ.copy()
                if models_path:
                    env["OLLAMA_MODELS"] = models_path

                result = subprocess.run(
                    [ollama_bin, "list"],
                    capture_output=True, text=True, timeout=10, env=env
                )

                if result.returncode != 0:
                    return {
                        "ok": False,
                        "message": "Ollama сервер не отвечает на запрос списка моделей",
                        "action": "Перезапустите Ollama"
                    }

                # Парсим список моделей (первая строка — заголовок)
                lines = result.stdout.strip().split('\n')
                models = []
                for line in lines[1:]:
                    if line.strip():
                        model_name = line.split()[0]
                        models.append(model_name)

                if not models:
                    return {
                        "ok": False,
                        "message": "Ollama сервер работает, но модели не зарегистрированы",
                        "action": "Запустите инсталлер повторно (шаг 8)"
                    }

                return {
                    "ok": True,
                    "message": f"Ollama сервер работает, {len(models)} моделей зарегистрировано",
                    "models": models
                }

            finally:
                # Останавливаем сервер, если мы его запустили
                if server_started_by_us and server_proc:
                    try:
                        server_proc.terminate()
                        server_proc.wait(timeout=5)
                    except Exception:
                        try:
                            server_proc.kill()
                        except Exception:
                            pass

        except Exception as e:
            return {
                "ok": False,
                "message": f"Ошибка проверки Ollama: {e}",
                "action": "Запустите инсталлер повторно"
            }

    def _is_ollama_running(self) -> bool:
        """Проверяет, запущен ли Ollama сервер (по порту 11434)."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 11434))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _wait_ollama_ready(self, timeout: int = 15) -> bool:
        """Ждёт, пока Ollama сервер станет доступен."""
        import requests
        start = time.time()
        while time.time() - start < timeout:
            try:
                res = requests.get("http://localhost:11434/api/version", timeout=2)
                if res.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False
