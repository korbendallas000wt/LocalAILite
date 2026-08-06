import os
import subprocess
import requests

class PathValidator:
    def validate_venv(self, path: str) -> dict:
        """Проверка venv"""
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
        """Проверка папки моделей"""
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

    def validate_all(self, config) -> dict:
        """Проверка всех путей"""
        result = {
            "venv": self.validate_venv(config.get_sdxl_venv_path()),
            "models": self.validate_models_path(config.get_sdxl_models_path()),
            "output": self.validate_output_dir(config.get_sdxl_output_dir()),
            "ollama": self.validate_ollama_url(config.get_ollama_url())
        }

        # Проверяем, все ли критичные пути валидны
        result["all_valid"] = (
            result["venv"]["valid"] and
            result["models"]["valid"] and
            result["output"]["valid"] and
            result["ollama"]["valid"]
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
