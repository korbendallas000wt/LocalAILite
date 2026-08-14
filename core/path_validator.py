import os
import subprocess
import requests

class PathValidator:
    def validate_venv(self, path: str) -> dict:
        """Проверка venv (быстрая: только пути и запуск Python)"""
        if not path:
            return {"valid": False, "error": "Путь не указан"}

        if not os.path.exists(path):
            return {"valid": False, "error": "Папка не существует"}

        python_path = os.path.join(path, "bin", "python")
        if not os.path.exists(python_path):
            return {"valid": False, "error": "bin/python не найден"}

        # Проверяем запуск Python
        try:
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return {"valid": True, "error": ""}
            else:
                return {"valid": False, "error": f"Python вернул ошибку: {result.stderr}"}
        except subprocess.TimeoutExpired:
            return {"valid": False, "error": "Таймаут при запуске Python"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_models_path(self, path: str) -> dict:
        """Проверка папки моделей (быстрая: только подсчёт)"""
        if not path:
            return {"valid": False, "error": "Путь не указан", "count": 0}
        if not os.path.exists(path):
            return {"valid": False, "error": "Папка не существует", "count": 0}
        if not os.path.isdir(path):
            return {"valid": False, "error": "Это не папка", "count": 0}

        models_count = 0

        for item in os.listdir(path):
            item_path = os.path.join(path, item)

            # 1. Одиночные файлы
            if os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    models_count += 1

            # 2. HF cache папки (models--org--model-name)
            elif os.path.isdir(item_path) and item.startswith("models--"):
                models_count += 1

            # 3. Распакованные модели (папки с model_index.json)
            elif os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    models_count += 1

        if models_count == 0:
            return {"valid": False, "error": "Модели не найдены", "count": 0}

        return {"valid": True, "error": "", "count": models_count}

    def validate_output_dir(self, path: str) -> dict:
        """Проверка папки сохранения"""
        if not path:
            return {"valid": False, "error": "Путь не указан"}

        # Пытаемся создать если не существует
        try:
            os.makedirs(path, exist_ok=True)

            # Проверяем права на запись
            test_file = os.path.join(path, ".test_write")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)

            return {"valid": True, "error": ""}
        except PermissionError:
            return {"valid": False, "error": "Нет прав на запись"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_ollama_url(self, url: str) -> dict:
        """Проверка Ollama"""
        if not url:
            return {"valid": False, "error": "URL не указан", "models_count": 0}

        try:
            res = requests.get(f"{url}/api/tags", timeout=5)
            if res.status_code == 200:
                models = res.json().get('models', [])
                return {"valid": True, "error": "", "models_count": len(models)}
            else:
                return {"valid": False, "error": f"HTTP {res.status_code}", "models_count": 0}
        except requests.exceptions.ConnectionError:
            return {"valid": False, "error": "Не удалось подключиться", "models_count": 0}
        except requests.exceptions.Timeout:
            return {"valid": False, "error": "Таймаут соединения", "models_count": 0}
        except Exception as e:
            return {"valid": False, "error": str(e), "models_count": 0}

    def validate_ollama_binary(self, path: str) -> dict:
        """Проверка бинарника Ollama.
        Если путь не задан — проверяем системный бинарник (shutil.which).
        Это позволяет использовать системный Ollama без указания пути.
        """
        import shutil
        if not path:
            # Проверяем системный бинарник
            system_bin = shutil.which("ollama")
            if system_bin:
                return {"valid": True, "error": ""}
            return {"valid": False, "error": "Путь не указан и системный бинарник не найден"}
        if not os.path.exists(path):
            return {"valid": False, "error": "Бинарник не найден"}
        if not os.path.isfile(path):
            return {"valid": False, "error": "Это не файл"}
        if not os.access(path, os.X_OK):
            return {"valid": False, "error": "Нет прав на исполнение"}
        # Проверяем запуск
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return {"valid": True, "error": ""}
            return {"valid": False, "error": f"Ollama вернул ошибку: {result.stderr[:100]}"}
        except subprocess.TimeoutExpired:
            return {"valid": False, "error": "Таймаут при запуске Ollama"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_ollama_models_path(self, path: str) -> dict:
        """Проверка папки моделей Ollama.
        В отличие от SDXL-моделей, папка может быть пустой
        (модели ещё не скачаны) — это не ошибка.
        """
        if not path:
            return {"valid": False, "error": "Путь не указан", "count": 0}
        # Пытаемся создать, если не существует
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            return {"valid": False, "error": f"Не удалось создать папку: {e}", "count": 0}
        if not os.path.isdir(path):
            return {"valid": False, "error": "Это не папка", "count": 0}
        # Считаем модели (Ollama хранит в manifests/registry)
        models_count = 0
        manifests_dir = os.path.join(path, "manifests", "registry.ollama.ai", "library")
        if os.path.isdir(manifests_dir):
            models_count = len([d for d in os.listdir(manifests_dir)
                               if os.path.isdir(os.path.join(manifests_dir, d))])
        return {"valid": True, "error": "", "count": models_count}

    def validate_all(self, config) -> dict:
        """Проверка всех путей"""
        result = {
            "venv": self.validate_venv(config.get_sdxl_venv_path()),
            "models": self.validate_models_path(config.get_sdxl_models_path()),
            "output": self.validate_output_dir(config.get_sdxl_output_dir()),
            "ollama": self.validate_ollama_url(config.get_ollama_url()),
            "ollama_binary": self.validate_ollama_binary(config.get("ollama/binary_path", "")),
            "ollama_models": self.validate_ollama_models_path(config.get("ollama/models_path", ""))
        }

        # Проверяем, все ли критичные пути валидны
        # ollama (URL) не критичен при старте — сервер запустится автоматически
        # ollama_models не критичен — модели могут быть ещё не скачаны
        # ollama_binary критичен — без него Ollama не запустится
        result["all_valid"] = (
            result["venv"]["valid"] and
            result["models"]["valid"] and
            result["output"]["valid"] and
            result["ollama_binary"]["valid"]
        )

        return result

    def validate_installed(self, config) -> dict:
        """Проверка путей только для включённых компонентов (features/*).
        Используется в усечённом приложении.
        """
        result = {}
        all_valid = True

        # Ollama
        if config.get_feature("ollama", True):
            result["ollama"] = self.validate_ollama_url(config.get_ollama_url())
            if not result["ollama"]["valid"]:
                all_valid = False
            # Бинарник Ollama — КРИТИЧНО (без него Ollama не запустится)
            ollama_binary = config.get("ollama/binary_path", "")
            if ollama_binary:
                result["ollama_binary"] = self.validate_ollama_binary(ollama_binary)
                if not result["ollama_binary"]["valid"]:
                    all_valid = False
            else:
                # Путь не задан — тоже критично
                result["ollama_binary"] = {"valid": False, "error": "Путь к бинарнику не задан"}
                all_valid = False
            # Папка моделей Ollama (не критично — модели могут быть ещё не скачаны)
            ollama_models = config.get("ollama/models_path", "")
            if ollama_models:
                result["ollama_models"] = self.validate_ollama_models_path(ollama_models)

        # SDXL / Diffusers
        if config.get_feature("sdxl", True):
            result["venv"] = self.validate_venv(config.get_sdxl_venv_path())
            result["models"] = self.validate_models_path(config.get_sdxl_models_path())
            result["output"] = self.validate_output_dir(config.get_sdxl_output_dir())
            if not (result["venv"]["valid"] and result["models"]["valid"] and result["output"]["valid"]):
                all_valid = False

        # Image Prep — не требует обвязки, всегда OK
        if config.get_feature("image_prep", True):
            result["image_prep"] = {"valid": True, "error": ""}

        result["all_valid"] = all_valid
        return result
