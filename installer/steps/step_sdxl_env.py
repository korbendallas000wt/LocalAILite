"""
installer/steps/step_sdxl_env.py — шаг создания SDXL окружения (уровень 2).

Создаёт отдельный venv для SDXL/Diffusers и устанавливает:
torch (CPU-only), diffusers, torchvision, torchaudio, pillow.

НЕ путать с основным venv приложения (venv/) — тот для UI (PyQt6).
Этот venv — только для генерации изображений через scripts/generate_diffusers.py.

Идемпотентен: если venv уже создан и зависимости работают — пропускает.
Чистый Python, без PyQt — работает и в CLI-бутстрапе, и в UI-визарде.
"""

import os
import subprocess

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus

# Интеграция валидатора пакетов для идемпотентности (баг #15)
try:
    from core.package_validator import verify_critical_imports, check_numpy_version
except ImportError:
    try:
        from package_validator import verify_critical_imports, check_numpy_version
    except ImportError:
        verify_critical_imports = None
        check_numpy_version = None


class StepSdxlEnv(InstallStep):
    """Создание SDXL venv + установка torch/diffusers."""

    id = "sdxl_env"
    name = "SDXL окружение"
    description = "Создание venv для SDXL + установка torch, diffusers (~6 GB)"

    # Пакеты Python 3.12 по пакетным менеджерам (для автоустановки)
    PYTHON_312_PACKAGES = {
        "pacman": "python312",           # AUR; на Manjaro обычно есть pyenv
        "apt": "python3.12 python3.12-venv python3.12-dev",
        "dnf": "python3.12 python3.12-devel",
        "zypper": "python312 python312-devel",
        "emerge": "dev-lang/python:3.12",
        "xbps": "python3.12",
    }

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        # Детектор для поиска совместимого Python
        try:
            from installer.detector import HardwareDetector
        except ImportError:
            from detector import HardwareDetector
        self.detector = HardwareDetector()
        # Пути читаются из Config динамически (см. _get_paths)

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
        """Читает значение из Config (JSON, без PyQt)."""
        try:
            from utils.config import Config
            config = Config()
            value = config.get(key, default)
            return value if value else default
        except Exception:
            return default

    def _get_paths(self) -> dict:
        """Читает путь SDXL venv из Config с fallback на venv_sdxl.
        Валидирует: если python_path не существует — fallback на дефолт.
        """
        venv_path = self._read_config_value("sdxl/venv_path", "")
        if venv_path:
            python_path = os.path.join(venv_path, "bin", "python")
            # Валидация: python должен существовать
            if os.path.exists(python_path):
                return {
                    "venv_path": venv_path,
                    "python_path": python_path,
                }
        # Fallback на дефолт (путь из Config не существует)
        venv_path = os.path.join(self.base_dir, "venv_sdxl")
        python_path = os.path.join(venv_path, "bin", "python")
        return {
            "venv_path": venv_path,
            "python_path": python_path,
        }

    def _find_python_for_sdxl(self):
        """Находит совместимый Python (3.10-3.12) для SDXL venv.
        Использует sdxl_mode=True в детекторе — строгий диапазон 3.10-3.12
        + приоритет портативного Python из bin/python/.
        Возвращает None, если совместимого нет (без fallback на несовместимый).
        """
        detection = self.detector.detect_python(sdxl_mode=True)
        if detection.get("has_compatible") and detection.get("compatible"):
            first = detection["compatible"][0]
            print(f"  Найден Python {first['version_str']} ({first['source']})")
            return first["path"]
        return None

    def _ensure_compatible_python(self) -> str:
        """Пытается установить Python 3.12 через пакетный менеджер.
        Возвращает путь к совместимому Python или None.
        """
        os_info = self.detector.detect_os()
        pkg_manager = os_info.get("pkg_manager")
        if not pkg_manager or pkg_manager not in self.PYTHON_312_PACKAGES:
            print(f"  ⚠ Пакетный менеджер не определён или не поддерживается")
            return None

        py312_pkg = self.PYTHON_312_PACKAGES[pkg_manager]
        pm_info = self.detector.PKG_MANAGERS.get(pkg_manager, {})
        install_cmd = pm_info.get("install_cmd", [])
        noconfirm = pm_info.get("noconfirm_flag", "")

        cmd = install_cmd[:]
        if noconfirm:
            cmd.append(noconfirm)
        cmd.extend(py312_pkg.split())

        print(f"  Совместимый Python (3.10-3.12) не найден.")
        print(f"  Системный Python несовместим с torch/diffusers.")
        print(f"  Команда установки: {' '.join(cmd)}")
        reply = input("  Установить Python 3.12? (sudo) [Y/n]: ").strip().lower()
        if reply not in ('', 'y', 'yes', 'да'):
            print("  ⏭ Пропущено")
            return None

        apt_success = False
        try:
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=600
            )
            if result.returncode == 0:
                apt_success = True
            else:
                print(f"  ❌ Ошибка установки: {result.stderr.strip()[:200]}")
        except Exception as e:
            print(f"  ❌ Ошибка установки: {e}")

        # Повторная детекция (если apt отработал без ошибок)
        result = None
        if apt_success:
            print("  Поиск установленного Python 3.12...")
            result = self._find_python_for_sdxl()

        # Если apt упал или Python не найден — предлагаем портативный
        if not result:
            print(f"  Системный Python 3.12 недоступен.")
            print(f"  Предлагаю скачать портативный Python (~60 MB) из astral-sh.")
            reply = input("  Скачать портативный Python? [Y/n]: ").strip().lower()
            if reply not in ('', 'y', 'yes', 'да'):
                print("  ⏭ Пропущено")
                return None
            return self._download_portable_python()

        return result

    def _download_portable_python(self) -> str:
        """Скачивает портативный Python из astral-sh.
        URL и путь берутся из installer/config.json (поле python.portable).
        Возвращает путь к python3 или None.
        """
        try:
            from installer.config_loader import load_config
            config = load_config()
            
            url = config.get('python.portable.url')
            version = config.get('python.portable.version', '3.12')
            local_path = config.get_path('python.portable.local_path')
            
            if not url or not local_path:
                print(f"  ❌ URL портативного Python не настроен в installer/config.json")
                return None
            
            print(f"  Скачивание портативного Python {version}...")
            print(f"  URL: {url[:80]}...")
            
            # Скачиваем tar.gz в /tmp
            import tarfile
            import shutil
            import urllib.request
            
            tmp_tar = "/tmp/portable-python.tar.gz"
            extract_dir = os.path.join(self.base_dir, "bin", "python")
            
            try:
                urllib.request.urlretrieve(url, tmp_tar)
            except Exception as e:
                print(f"  ❌ Ошибка скачивания: {e}")
                return None
            
            # Распаковываем
            try:
                os.makedirs(extract_dir, exist_ok=True)
                with tarfile.open(tmp_tar, "r:gz") as tar:
                    tar.extractall(extract_dir)
            except Exception as e:
                print(f"  ❌ Ошибка распаковки: {e}")
                return None
            
            # Удаляем tar
            try:
                os.remove(tmp_tar)
            except Exception:
                pass
            
            # Проверяем, что python существует
            if os.path.exists(local_path):
                print(f"  ✅ Портативный Python установлен: {local_path}")
                return local_path
            else:
                print(f"  ❌ Python не найден после установки: {local_path}")
                return None
                
        except Exception as e:
            print(f"  ❌ Ошибка скачивания портативного Python: {e}")
            return None

    def _get_torch_index_url(self) -> str:
        """Выбирает URL для torch на основе детекции GPU.
        NVIDIA + CUDA → cu121, иначе → cpu.
        """
        gpu = self.detector.detect_gpu()
        if gpu.get("vendor") == "nvidia" and gpu.get("cuda_present"):
            return "https://download.pytorch.org/whl/cu121"
        return "https://download.pytorch.org/whl/cpu"

    def _write_config_path(self, venv_path: str) -> bool:
        """Записывает путь к SDXL venv в data/local_config.json (прямой импорт, без subprocess)."""
        try:
            from utils.config import Config
            config = Config()
            config.set_sdxl_venv_path(venv_path)
            return True
        except Exception as e:
            print(f"  ⚠ Ошибка записи в Config: {e}")
            return False

    def is_installed(self) -> StepStatus:
        """Проверяет, создан ли SDXL venv и работают ли torch/diffusers.
        Использует package_validator для детальной проверки пакетов (идемпотентность, баг #15).
        """
        paths = self._get_paths()
        if not os.path.exists(paths['python_path']):
            return StepStatus.failed(
                "SDXL venv не создан",
                details=f"Ожидался: {paths['venv_path']}"
            )

        # Проверка критических пакетов через валидатор (баг #15)
        if verify_critical_imports:
            validation = verify_critical_imports(paths['python_path'])
            if not validation.valid:
                error_msg = f"Критические пакеты не работают: {'; '.join(validation.errors[:2])}"
                print(f"  ❌ {error_msg}")
                return StepStatus.failed(
                    "SDXL venv создан, но пакеты битые",
                    details=error_msg
                )

        # Проверка numpy (критично для старых CPU, баг #15)
        if check_numpy_version:
            numpy_validation = check_numpy_version(paths['python_path'])
            if not numpy_validation.valid:
                error_msg = f"numpy не работает: {'; '.join(numpy_validation.errors[:2])}"
                print(f"  ❌ {error_msg}")
                return StepStatus.failed(
                    "SDXL venv создан, но numpy битый",
                    details=error_msg
                )

        # Глубокая проверка: импорт torch и diffusers
        try:
            result = subprocess.run(
                [paths['python_path'], "-c",
                 "import torch; print(f'torch {torch.__version__}'); "
                 "from diffusers import StableDiffusionXLPipeline; "
                 "print('diffusers OK')"],
                capture_output=True, text=True, timeout=120  # Увеличен для CPU-only (torch долго грузится на старых CPU)
            )
            if result.returncode == 0:
                return StepStatus.success(
                    f"SDXL venv готов ({paths['venv_path']})",
                    details=result.stdout.strip()
                )
            error_details = result.stderr.strip()[:300]
            print(f"  ❌ Детали ошибки: {error_details}")
            return StepStatus.failed(
                "SDXL venv создан, но torch/diffusers не работают",
                details=error_details
            )
        except Exception as e:
            return StepStatus.failed(f"Ошибка проверки SDXL venv: {e}")

    def install(self, progress=None) -> StepStatus:
        """Создаёт SDXL venv и устанавливает torch/diffusers."""
        paths = self._get_paths()
        
        # 1. Находим совместимый Python
        self._report(progress, 5, "Поиск совместимого Python (3.10-3.12)...")
        python_bin = self._find_python_for_sdxl()
        if not python_bin:
            # Совместимого нет — пробуем установить через пакетный менеджер
            python_bin = self._ensure_compatible_python()
            if not python_bin:
                return StepStatus.failed(
                    "Не найден совместимый Python (3.10-3.12) для SDXL venv. "
                    "Установите Python 3.12 вручную и повторите установку."
                )
        self._report(progress, 10, f"Python: {python_bin}")

        # 2. Создаём venv
        self._report(progress, 15, f"Создание SDXL venv: {paths['venv_path']}")
        try:
            result = subprocess.run(
                [python_bin, "-m", "venv", paths['venv_path']],
                capture_output=True, text=True, timeout=180
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка создания SDXL venv: {result.stderr.strip()}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка создания SDXL venv: {e}")

        # 3. Обновляем pip
        self._report(progress, 20, "Обновление pip...")
        try:
            subprocess.run(
                [paths['python_path'], "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True, text=True, timeout=180
            )
        except Exception:
            pass

        # 4. Устанавливаем torch (CPU-only) + diffusers
        # Добавляем --retries и --timeout для устойчивости к сетевым сбоям (баг #17)
        torch_index_url = self._get_torch_index_url()
        self._report(progress, 25, f"Установка torch ({'CUDA' if 'cu121' in torch_index_url else 'CPU'})...")
        torch_cmd = [
            paths['python_path'], "-m", "pip", "install",
            "--retries", "5", "--timeout", "120",
            "torch", "torchvision", "torchaudio",
            "--index-url", torch_index_url
        ]
        try:
            result = subprocess.run(
                torch_cmd, capture_output=True, text=True, timeout=1800
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка установки torch: {result.stderr.strip()[:300]}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка установки torch: {e}")

        self._report(progress, 60, "Установка diffusers и зависимостей...")
        # Добавляем --retries и --timeout для устойчивости к сетевым сбоям (баг #17)
        diffusers_cmd = [
            paths['python_path'], "-m", "pip", "install",
            "--retries", "5", "--timeout", "120",
            "diffusers", "transformers", "accelerate",
            "safetensors", "pillow", "numpy<2"
        ]
        try:
            result = subprocess.run(
                diffusers_cmd, capture_output=True, text=True, timeout=900
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка установки diffusers: {result.stderr.strip()[:300]}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка установки diffusers: {e}")

        # 5. Финальная проверка
        self._report(progress, 90, "Проверка работоспособности torch/diffusers...")
        try:
            result = subprocess.run(
                [paths['python_path'], "-c",
                 "import torch; print(f'torch {torch.__version__}'); "
                 "from diffusers import StableDiffusionXLPipeline; "
                 "print('diffusers OK')"],
                capture_output=True, text=True, timeout=120  # Увеличен для CPU-only (torch долго грузится на старых CPU)
            )
            if result.returncode != 0:
                error_details = result.stderr.strip()[:300]
                print(f"  ❌ Детали ошибки: {error_details}")
                return StepStatus.failed(
                    "torch/diffusers установлены, но не работают",
                    details=error_details
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка проверки: {e}")

        # 6. Записываем путь в Config
        self._report(progress, 95, "Запись пути в конфиг...")
        self._write_config_path(paths['venv_path'])

        self._report(progress, 100, "SDXL окружение готово")
        return StepStatus.success(
            f"SDXL venv создан, torch/diffusers установлены ({paths['venv_path']})"
        )

    def verify(self) -> StepStatus:
        """Проверяет после установки."""
        return self.is_installed()
