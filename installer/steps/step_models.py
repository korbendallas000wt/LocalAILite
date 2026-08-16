"""
installer/steps/step_models.py — шаг скачивания моделей (уровень 2).

Скачивает модели Ollama (через ollama pull) и SDXL (через huggingface_hub).
Использует рекомендации из advisor.recommend_models().

Идемпотентен: если модели уже есть — пропускает.
Чистый Python, БЕЗ PyQt — работает в CLI-бутстрапе и в UI-визарде.
"""

import os
import subprocess
import shutil
import re

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus

try:
    from core.model_validator import validate_ollama_model, validate_model
except ImportError:
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from core.model_validator import validate_ollama_model, validate_model


class StepModels(InstallStep):
    """Скачивание моделей Ollama и SDXL."""

    id = "models"
    name = "Скачивание моделей"
    description = "Скачивание моделей Ollama и SDXL (рекомендованные советником)"

    def __init__(self, base_dir: str = None, ollama_model: str = None, sdxl_model: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        self.venv_python = os.path.join(base_dir, "venv", "bin", "python")
        # Модели для скачивания (None = рекомендованные из advisor)
        self.ollama_model = ollama_model
        self.sdxl_model = sdxl_model
        # Детектор и советник
        try:
            from installer.detector import HardwareDetector
            from installer.advisor import Advisor
        except ImportError:
            from detector import HardwareDetector
            from advisor import Advisor
        self.detector = HardwareDetector()
        self.advisor = Advisor(self.detector)

    def _find_project_root(self) -> str:
        """Ищем корень проекта (где main.py)."""
        cur = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            if os.path.exists(os.path.join(cur, "main.py")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.getcwd()

    def _read_config_value(self, key: str, default: str = "") -> str:
        """Читает значение из QSettings через venv python."""
        if not os.path.exists(self.venv_python):
            return default
        try:
            result = subprocess.run(
                [self.venv_python, "-c",
                 f"from utils.config import Config; c = Config(); print(c.get('{key}', '{default}') or '{default}')"],
                capture_output=True, text=True, timeout=10, cwd=self.base_dir
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return default

    def _get_feature(self, feature_name: str) -> bool:
        """Читает флаг features/* из QSettings."""
        value = self._read_config_value(f"features/{feature_name}", "true")
        return value.lower() == "true"

    def _find_ollama_binary(self) -> str:
        """Находит бинарник Ollama."""
        # 1. Из Config
        binary_path = self._read_config_value("ollama/binary_path", "")
        if binary_path and os.path.exists(binary_path) and os.access(binary_path, os.X_OK):
            return binary_path
        # 2. Локальный (в проекте)
        local_bin = os.path.join(self.base_dir, "bin", "ollama", "bin", "ollama")
        if os.path.exists(local_bin) and os.access(local_bin, os.X_OK):
            return local_bin
        # 3. Системный (в PATH)
        system_bin = shutil.which("ollama")
        if system_bin:
            return system_bin
        return ""

    def _get_sdxl_python(self) -> str:
        """Возвращает путь к SDXL venv python."""
        sdxl_venv = self._read_config_value("sdxl/venv_path", "")
        if not sdxl_venv:
            sdxl_venv = os.path.join(self.base_dir, "venv_sdxl")
        python_path = os.path.join(sdxl_venv, "bin", "python")
        if os.path.exists(python_path):
            return python_path
        return ""

    def _get_models_path(self) -> str:
        """Возвращает путь к папке моделей SDXL."""
        models_path = self._read_config_value("sdxl/models_path", "")
        if not models_path:
            models_path = os.path.join(self.base_dir, "data", "diffusers", "models")
        return models_path

    def _get_paths(self) -> dict:
        """Читает пути моделей из Config с валидацией."""
        models_path = self._read_config_value("sdxl/models_path", "")
        if models_path and os.path.exists(models_path):
            pass  # Используем путь из Config
        else:
            # Fallback на дефолт
            models_path = os.path.join(self.base_dir, "data", "diffusers", "models")
        
        ollama_models_path = self._read_config_value("ollama/models_path", "")
        if not ollama_models_path:
            ollama_models_path = os.path.join(self.base_dir, "data", "ollama", "models")
        
        return {
            "models_path": models_path,
            "ollama_models_path": ollama_models_path,
        }

    def _check_disk_space(self, required_gb: float, path: str) -> dict:
        """Проверяет свободное место на диске."""
        disk = self.detector.detect_disk(path)
        if not disk.get("mounted"):
            return {"ok": False, "message": f"Диск не смонтирован: {path}"}
        free_gb = disk.get("free_gb", 0)
        if free_gb < required_gb:
            return {
                "ok": False,
                "message": f"Недостаточно места: нужно {required_gb:.1f} GB, свободно {free_gb:.1f} GB"
            }
        return {"ok": True, "message": f"Свободно {free_gb:.1f} GB"}

    def _estimate_ollama_model_size(self, model_name: str) -> float:
        """Оценивает размер Ollama модели по имени."""
        name = model_name.lower()
        if "0.5b" in name:
            return 0.5
        elif "1.5b" in name:
            return 1.0
        elif "3b" in name:
            return 2.0
        elif "7b" in name or "8b" in name:
            return 5.0
        elif "14b" in name:
            return 9.0
        return 4.0  # По умолчанию

    def _list_ollama_models(self, models_path: str = "") -> list:
        """Возвращает список установленных Ollama моделей.
        Сканирует папку manifests/registry.ollama.ai/library/ напрямую,
        не требует запущенного сервера (в отличие от ollama list).
        
        Реальная структура Ollama:
            manifests/registry.ollama.ai/library/{model}/{tag}
        Пример:
            library/qwen2.5-coder/3b     ← файл-манифест
            library/qwen2.5-coder/7b     ← файл-манифест
        Результат: ["qwen2.5-coder:3b", "qwen2.5-coder:7b"]
        """
        models = []
        if not models_path or not os.path.exists(models_path):
            return models
        
        # Путь к манифестам: {models_path}/manifests/registry.ollama.ai/library/
        library_path = os.path.join(models_path, "manifests", "registry.ollama.ai", "library")
        if not os.path.isdir(library_path):
            return models
        
        # Сканируем папки-модели напрямую в library/
        for model_name in os.listdir(library_path):
            model_path = os.path.join(library_path, model_name)
            if not os.path.isdir(model_path):
                continue
            
            # Сканируем теги (файлы внутри папки модели)
            for tag in os.listdir(model_path):
                tag_path = os.path.join(model_path, tag)
                if os.path.isfile(tag_path):
                    models.append(f"{model_name}:{tag}")
        
        return models

    def _list_sdxl_models(self, models_path: str) -> list:
        """Возвращает список установленных SDXL моделей."""
        models = []
        if not models_path or not os.path.exists(models_path):
            return models
        for item in os.listdir(models_path):
            item_path = os.path.join(models_path, item)
            # HF cache формат
            if os.path.isdir(item_path) and item.startswith("models--"):
                models.append(item)
            # Single-file модели
            elif os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    models.append(item)
            # Распакованные модели
            elif os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    models.append(item)
        return models

    def is_installed(self) -> StepStatus:
        """Проверяет, установлены ли модели и валидны ли они."""
        paths = self._get_paths()
        ollama_installed = self._get_feature("ollama")
        sdxl_installed = self._get_feature("sdxl")
        
        missing = []
        invalid = []
        
        # Проверяем Ollama
        if ollama_installed:
            ollama_bin = self._find_ollama_binary()
            # Сканируем папку моделей напрямую (не требует сервера)
            ollama_models = self._list_ollama_models(paths['ollama_models_path'])
            if not ollama_models:
                missing.append("Ollama модели")
            else:
                # Проверяем целостность каждой модели
                for model_name in ollama_models:
                    validation = validate_ollama_model(model_name, paths['ollama_models_path'])
                    if not validation.valid:
                        invalid.append(f"Ollama {model_name}: {validation.errors[0] if validation.errors else 'неизвестная ошибка'}")
        
        # Проверяем SDXL
        if sdxl_installed:
            sdxl_models = self._list_sdxl_models(paths['models_path'])
            if not sdxl_models:
                missing.append("SDXL модели")
            else:
                # Проверяем целостность каждой модели
                for model_name in sdxl_models:
                    model_path = os.path.join(paths['models_path'], model_name)
                    validation = validate_model(model_path)
                    if not validation.valid:
                        invalid.append(f"SDXL {model_name}: {validation.errors[0] if validation.errors else 'неизвестная ошибка'}")
        
        if missing:
            return StepStatus.failed(
                f"Модели не установлены: {', '.join(missing)}",
                details="Требуется скачивание моделей"
            )
        
        if invalid:
            return StepStatus.failed(
                f"Модели битые: {len(invalid)} шт.",
                details="; ".join(invalid[:3]) + ("..." if len(invalid) > 3 else "")
            )
        
        return StepStatus.success("Модели установлены и валидны")

    # === Управление Ollama сервером для скачивания моделей ===
    
    def _is_ollama_server_running(self) -> bool:
        """Проверяет, запущен ли Ollama сервер на порту 11434."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 11434))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def _start_ollama_server(self, ollama_bin: str, models_path: str = ""):
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
    
    def _wait_ollama_ready(self, timeout: int = 30) -> bool:
        """Ждёт, пока Ollama сервер станет доступен на порту 11434."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self._is_ollama_server_running():
                return True
            time.sleep(0.5)
        return False
    

    def _wait_model_registered(self, ollama_bin: str, model_name: str, models_path: str = "", timeout: int = 10) -> bool:
        """Ждёт, пока модель зарегистрируется в Ollama сервере (баг #16).
        Проверяет через 'ollama list' каждые 2 секунды.
        """
        import time
        env = os.environ.copy()
        if models_path:
            env["OLLAMA_MODELS"] = models_path
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(
                    [ollama_bin, "list"],
                    capture_output=True, text=True, timeout=10, env=env
                )
                if result.returncode == 0 and model_name in result.stdout:
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def _pull_ollama_model(self, ollama_bin: str, model_name: str, models_path: str = "", progress=None) -> StepStatus:
        """Скачивает Ollama модель через ollama pull.
        Если сервер не запущен — запускает его, скачивает модель, останавливает.
        Передаёт OLLAMA_MODELS env, чтобы модель скачалась в правильную папку.
        """
        self._report(progress, 10, f"Скачивание Ollama модели: {model_name}")
        
        env = os.environ.copy()
        if models_path:
            env["OLLAMA_MODELS"] = models_path
        
        # Проверяем, запущен ли сервер
        server_proc = None
        server_started_by_us = False
        if not self._is_ollama_server_running():
            self._report(progress, 12, "Ollama сервер не запущен — запускаем...")
            server_proc = self._start_ollama_server(ollama_bin, models_path)
            server_started_by_us = True
            if not self._wait_ollama_ready(timeout=30):
                # Не запустился — пытаемся убить и сообщаем об ошибке
                if server_proc:
                    try:
                        server_proc.terminate()
                    except Exception:
                        pass
                return StepStatus.failed(
                    "Ollama сервер не запустился за 30 секунд",
                    details="Невозможно скачать модель без работающего сервера"
                )
            self._report(progress, 15, "Ollama сервер готов")
        
        try:
            # Запускаем ollama pull
            proc = subprocess.Popen(
                [ollama_bin, "pull", model_name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env
            )
            
            # Читаем вывод построчно, фильтруем прогресс (выводим только при изменении на >=10%)
            last_pct = 0
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                
                # Парсим процент из строки прогресса
                match = re.search(r'(\d+)%', line)
                if match:
                    pct = int(match.group(1))
                    if pct >= last_pct + 10:
                        self._report(progress, 20 + int(pct * 0.7), f"Ollama: {pct}%")
                        last_pct = pct
                elif "verifying" in line.lower():
                    if last_pct < 92:
                        self._report(progress, 92, "Ollama: проверка контрольной суммы")
                        last_pct = 92
                elif "writing" in line.lower():
                    if last_pct < 96:
                        self._report(progress, 96, "Ollama: запись манифеста")
                        last_pct = 96
                elif "success" in line.lower():
                    if last_pct < 100:
                        self._report(progress, 100, f"Ollama: модель {model_name} скачана")
                        last_pct = 100
            
            proc.wait()
            if proc.returncode == 0:
                # Баг #16: ожидаем регистрацию модели в сервере
                self._report(progress, 97, f"Проверка регистрации модели в сервере...")
                if self._wait_model_registered(ollama_bin, model_name, models_path, timeout=10):
                    return StepStatus.success(f"Ollama модель {model_name} скачана и зарегистрирована")
                
                # Retry: пробуем ещё раз
                self._report(progress, 98, f"Модель не зарегистрировалась — повторная попытка...")
                retry_proc = subprocess.Popen(
                    [ollama_bin, "pull", model_name],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, env=env
                )
                retry_proc.wait()
                if retry_proc.returncode == 0:
                    if self._wait_model_registered(ollama_bin, model_name, models_path, timeout=15):
                        return StepStatus.success(f"Ollama модель {model_name} скачана (после retry)")
                
                return StepStatus.failed(
                    f"Модель {model_name} скачалась, но не зарегистрировалась в Ollama сервере",
                    details=f"Попробуйте перезапустить инсталлер или выполнить 'ollama pull {model_name}' вручную"
                )
            else:
                return StepStatus.failed(f"Ошибка скачивания Ollama модели: {model_name}")
        except Exception as e:
            return StepStatus.failed(f"Ошибка скачивания Ollama модели: {e}")
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

    def _download_sdxl_model(self, sdxl_python: str, repo_id: str, models_path: str, progress=None) -> StepStatus:
        """Скачивает SDXL модель через huggingface_hub.snapshot_download()."""
        self._report(progress, 10, f"Скачивание SDXL модели: {repo_id}")
        
        # Создаём папку моделей
        os.makedirs(models_path, exist_ok=True)
        
        # Скрипт для скачивания через SDXL venv python
        script = f"""
import sys
try:
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id='{repo_id}',
        cache_dir='{models_path}',
        allow_patterns=[
            "model_index.json",
            "scheduler/*",
            "text_encoder/config.json",
            "text_encoder/model.safetensors",
            "text_encoder_2/config.json",
            "text_encoder_2/model.safetensors",
            "tokenizer/*",
            "tokenizer_2/*",
            "unet/config.json",
            "unet/diffusion_pytorch_model.safetensors",
            "vae/config.json",
            "vae/diffusion_pytorch_model.safetensors",
        ]
    )
    print('SDXL_MODEL_DOWNLOADED')
except Exception as e:
    print(f'SDXL_MODEL_ERROR: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
        
        try:
            proc = subprocess.Popen(
                [sdxl_python, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.base_dir
            )
            
            # Читаем вывод (прогресс от tqdm будет в stderr, но мы объединили)
            for line in proc.stdout:
                line = line.strip()
                if line:
                    if "SDXL_MODEL_DOWNLOADED" in line:
                        self._report(progress, 100, f"SDXL модель {repo_id} скачана")
                    elif "SDXL_MODEL_ERROR" in line:
                        return StepStatus.failed(f"Ошибка скачивания SDXL модели: {line}")
                    elif "%" in line:
                        # Парсим прогресс из tqdm (если есть)
                        self._report(progress, 50, f"SDXL: {line[:60]}")
            
            proc.wait()
            if proc.returncode == 0:
                return StepStatus.success(f"SDXL модель {repo_id} скачана")
            else:
                return StepStatus.failed(f"Ошибка скачивания SDXL модели: {repo_id}")
        except Exception as e:
            return StepStatus.failed(f"Ошибка скачивания SDXL модели: {e}")

    def install(self, progress=None) -> StepStatus:
        """Скачивает модели (независимые компоненты Ollama и SDXL)."""
        paths = self._get_paths()
        
        # Определяем, какие модели качать
        ollama_installed = self._get_feature("ollama")
        sdxl_installed = self._get_feature("sdxl")
        
        # Получаем рекомендации из advisor
        recommendations = self.advisor.recommend_models()
        
        # Определяем модели для скачивания
        if self.ollama_model is None and ollama_installed:
            self.ollama_model = recommendations["ollama"]["recommended"]
        if self.sdxl_model is None and sdxl_installed:
            self.sdxl_model = recommendations["sdxl"]["recommended"]
        
        # Проверяем диск
        total_required = 0
        if ollama_installed and self.ollama_model:
            total_required += self._estimate_ollama_model_size(self.ollama_model)
        if sdxl_installed and self.sdxl_model:
            total_required += 7  # DISK_SDXL_MODEL_GB
        
        disk_check = self._check_disk_space(total_required, os.path.expanduser("~"))
        if not disk_check["ok"]:
            return StepStatus.failed(disk_check["message"])
        
        self._report(progress, 5, f"Проверка диска: {disk_check['message']}")
        
        # Флаги успеха для независимых компонентов
        ollama_success = True
        ollama_error = ""
        sdxl_success = True
        sdxl_error = ""
        
        # Скачиваем Ollama модель (независимо от SDXL)
        if ollama_installed and self.ollama_model:
            ollama_bin = self._find_ollama_binary()
            if not ollama_bin:
                print("  ⚠ Ollama бинарник не найден — пропускаем модели Ollama")
                ollama_success = False
                ollama_error = "Ollama бинарник не найден. Сначала выполните step_ollama."
            else:
                # Проверяем, не установлена ли уже модель
                # Сканируем папку моделей напрямую (не требует сервера)
                existing_models = self._list_ollama_models(paths['ollama_models_path'])
                if self.ollama_model in existing_models:
                    # Проверяем целостность уже установленной модели
                    validation = validate_ollama_model(self.ollama_model, paths['ollama_models_path'])
                    if validation.valid:
                        self._report(progress, 20, f"Ollama модель {self.ollama_model} уже установлена и валидна")
                    else:
                        print(f"  ⚠ Модель {self.ollama_model} битая: {validation.errors[:2]}")
                        self._report(progress, 18, f"Ollama модель {self.ollama_model} битая — перекачиваем")
                        # Удаляем битую модель через ollama rm
                        try:
                            subprocess.run([ollama_bin, "rm", self.ollama_model],
                                           capture_output=True, timeout=60)
                        except Exception:
                            pass
                        # Скачиваем заново
                        result = self._pull_ollama_model(ollama_bin, self.ollama_model, paths['ollama_models_path'], progress)
                        if not result.ok:
                            print(f"  ⚠ Ollama модель не скачана: {result.message}")
                            ollama_success = False
                            ollama_error = result.message
                        else:
                            # Проверяем целостность после скачивания
                            post_validation = validate_ollama_model(self.ollama_model, paths['ollama_models_path'])
                            if not post_validation.valid:
                                ollama_success = False
                                ollama_error = f"Модель скачалась, но не прошла проверку: {post_validation.errors[0] if post_validation.errors else 'неизвестная ошибка'}"
                else:
                    result = self._pull_ollama_model(ollama_bin, self.ollama_model, paths['ollama_models_path'], progress)
                    if not result.ok:
                        print(f"  ⚠ Ollama модель не скачана: {result.message}")
                        ollama_success = False
                        ollama_error = result.message
                    else:
                        # Проверяем целостность после скачивания
                        post_validation = validate_ollama_model(self.ollama_model, paths['ollama_models_path'])
                        if not post_validation.valid:
                            ollama_success = False
                            ollama_error = f"Модель скачалась, но не прошла проверку: {post_validation.errors[0] if post_validation.errors else 'неизвестная ошибка'}"
        
        # Скачиваем SDXL модель (независимо от Ollama)
        if sdxl_installed and self.sdxl_model:
            sdxl_python = self._get_sdxl_python()
            if not sdxl_python:
                print("  ⚠ SDXL venv не найден — пропускаем модели SDXL")
                sdxl_success = False
                sdxl_error = "SDXL venv не найден. Сначала выполните step_sdxl_env."
            else:
                models_path = paths['models_path']
                
                # Проверяем, не установлена ли уже модель
                existing_models = self._list_sdxl_models(models_path)
                # Ищем модель по имени репозитория (например, "models--stabilityai--sdxl-base-1.0")
                repo_folder_name = "models--" + self.sdxl_model.replace("/", "--")
                model_found = any(repo_folder_name in m for m in existing_models)
                
                if model_found:
                    # Находим точное имя папки модели
                    model_dir_name = None
                    for m in existing_models:
                        if repo_folder_name in m:
                            model_dir_name = m
                            break
                    model_path = os.path.join(models_path, model_dir_name) if model_dir_name else None
                    
                    # Проверяем целостность уже установленной модели
                    if model_path:
                        validation = validate_model(model_path)
                        if validation.valid:
                            self._report(progress, 60, f"SDXL модель {self.sdxl_model} уже установлена и валидна")
                        else:
                            print(f"  ⚠ Модель {self.sdxl_model} битая: {validation.errors[:2]}")
                            self._report(progress, 58, f"SDXL модель {self.sdxl_model} битая — перекачиваем")
                            # Удаляем битую модель
                            shutil.rmtree(model_path, ignore_errors=True)
                            # Скачиваем заново
                            result = self._download_sdxl_model(sdxl_python, self.sdxl_model, models_path, progress)
                            if not result.ok:
                                print(f"  ⚠ SDXL модель не скачана: {result.message}")
                                sdxl_success = False
                                sdxl_error = result.message
                            else:
                                # Проверяем целостность после скачивания
                                post_validation = validate_model(model_path)
                                if not post_validation.valid:
                                    sdxl_success = False
                                    sdxl_error = f"Модель скачалась, но не прошла проверку: {post_validation.errors[0] if post_validation.errors else 'неизвестная ошибка'}"
                    else:
                        self._report(progress, 60, f"SDXL модель {self.sdxl_model} уже установлена")
                else:
                    result = self._download_sdxl_model(sdxl_python, self.sdxl_model, models_path, progress)
                    if not result.ok:
                        print(f"  ⚠ SDXL модель не скачана: {result.message}")
                        sdxl_success = False
                        sdxl_error = result.message
                    else:
                        # Проверяем целостность после скачивания
                        model_dir_name = "models--" + self.sdxl_model.replace("/", "--")
                        model_path = os.path.join(models_path, model_dir_name)
                        if os.path.exists(model_path):
                            post_validation = validate_model(model_path)
                            if not post_validation.valid:
                                sdxl_success = False
                                sdxl_error = f"Модель скачалась, но не прошла проверку: {post_validation.errors[0] if post_validation.errors else 'неизвестная ошибка'}"
        
        # Сводный статус (независимые компоненты)
        if ollama_success and sdxl_success:
            self._report(progress, 100, "Все модели скачаны")
            return StepStatus.success("Модели скачаны")
        elif ollama_success or sdxl_success:
            # Частичный успех
            success_parts = []
            if ollama_success and ollama_installed and self.ollama_model:
                success_parts.append("Ollama")
            if sdxl_success and sdxl_installed and self.sdxl_model:
                success_parts.append("SDXL")
            self._report(progress, 100, f"Часть моделей скачана: {', '.join(success_parts)}")
            return StepStatus.success(
                f"Часть моделей скачана: {', '.join(success_parts)}",
                details="Повторите установку для скачивания оставшихся моделей"
            )
        else:
            # Оба провалились
            errors = []
            if ollama_error:
                errors.append(f"Ollama: {ollama_error}")
            if sdxl_error:
                errors.append(f"SDXL: {sdxl_error}")
            return StepStatus.failed(
                "Ни одна модель не скачана",
                details="; ".join(errors)
            )

    def verify(self) -> StepStatus:
        """Проверяет после установки."""
        return self.is_installed()
