"""
installer/steps/step_env.py — шаг создания окружения основного приложения.

Создаёт venv для основного приложения (UI) и устанавливает базовые зависимости:
PyQt6, requests, psutil. Это минимум для запуска main.py (уровень 1 — бутстрап).

НЕ путать с SDXL venv (sdxl/venv_path) — тот отдельный, с torch/diffusers,
и создаётся на уровне 2 (UI-визард).

Стратегия установки PyQt6 (гибридная):
- Современный CPU (sse4_2 + popcnt) → PyQt6 из pip в venv
- Старый CPU (без sse4_2) → системный PyQt6 из пакетного менеджера (venv --system-site-packages)
- Ничего не подходит → честно сообщаем

Идемпотентен: если venv уже создан и зависимости установлены — пропускает.
Чистый Python, без PyQt — работает и в CLI-бутстрапе, и в UI-визарде.
"""

import os
import subprocess

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus


class StepEnv(InstallStep):
    """Создание venv для основного приложения + установка зависимостей."""

    id = "env"
    name = "Окружение приложения"
    description = "Создание venv и установка PyQt6, requests, psutil"

    # Базовые зависимости для основного приложения (бутстрап, уровень 1)
    BASE_PACKAGES = ["PyQt6", "requests", "psutil", "numpy<2", "pillow"]
    # Пакеты, которые всегда ставим из pip (не зависят от CPU)
    PIP_ONLY_PACKAGES = ["requests", "psutil", "numpy<2", "pillow"]

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        # Основной venv — в корне проекта
        self.venv_dir = os.path.join(self.base_dir, "venv")
        self.python_path = os.path.join(self.venv_dir, "bin", "python")
        # Детектор для поиска Python и определения стратегии
        try:
            from installer.detector import HardwareDetector
        except ImportError:
            from detector import HardwareDetector
        self.detector = HardwareDetector()
        # Определяем стратегию установки PyQt6
        self._strategy = self._determine_strategy()

    def _find_project_root(self) -> str:
        """Ищем корень проекта (где main.py), поднимаясь от этого файла."""
        cur = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            if os.path.exists(os.path.join(cur, "main.py")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.getcwd()

    def _determine_strategy(self) -> str:
        """Определяет стратегию установки PyQt6.
        Возвращает: 'pip' | 'system' | 'none'
        """
        if self.detector.can_use_pip_pyqt6():
            return "pip"
        # Старый CPU — проверяем системный PyQt6
        sys_pyqt6 = self.detector.detect_system_pyqt6()
        if sys_pyqt6.get("installed") and sys_pyqt6.get("works"):
            return "system"
        return "none"

    def _find_python_for_venv(self):
        """Находит подходящий Python для создания venv.
        Для стратегии 'system' — системный Python (чтобы увидеть PyQt6 из pacman).
        Для стратегии 'pip' — совместимый (3.10-3.12) или системный.
        """
        if self._strategy == "system":
            for candidate in ["/usr/bin/python3", "/usr/bin/python"]:
                if os.path.exists(candidate):
                    return candidate
        # Для стратегии "pip" или fallback
        detection = self.detector.detect_python()
        if detection.get("has_compatible") and detection.get("compatible"):
            return detection["compatible"][0]["path"]
        for cand in detection.get("candidates", []):
            if cand.get("source") == "path":
                return cand["path"]
        if detection.get("candidates"):
            return detection["candidates"][0]["path"]
        return None

    def _check_ensurepip(self, python_bin: str) -> bool:
        """Проверяет наличие модуля ensurepip перед созданием venv.
        Если не найден — предлагает установить python3.X-venv через пакетный менеджер.
        Возвращает True, если ensurepip доступен.
        """
        # Проверяем, работает ли ensurepip
        try:
            result = subprocess.run(
                [python_bin, "-c", "import ensurepip"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        
        # ensurepip не найден — предлагаем установку
        print(f"  ⚠ Модуль ensurepip не найден в {python_bin}")
        print(f"  venv не может быть создан без ensurepip.")
        
        os_info = self.detector.detect_os()
        pkg_manager = os_info.get("pkg_manager")
        if not pkg_manager:
            print(f"  Пакетный менеджер не определён. Установите python3-venv вручную.")
            return False
        
        # Определяем версию Python
        try:
            result = subprocess.run(
                [python_bin, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                py_version = result.stdout.strip()
            else:
                py_version = "3"
        except Exception:
            py_version = "3"
        
        # Маппинг пакетов venv для разных пакетных менеджеров
        venv_packages = {
            "apt": f"python{py_version}-venv",
            "dnf": f"python{py_version}-venv",
            "pacman": "python",  # На Arch/Manjaro venv встроен
            "zypper": f"python{py_version}-venv",
        }
        
        pkg_name = venv_packages.get(pkg_manager)
        if not pkg_name:
            print(f"  Пакет для {pkg_manager} не определён.")
            return False
        
        pm_info = self.detector.PKG_MANAGERS.get(pkg_manager, {})
        install_cmd = pm_info.get("install_cmd", [])
        noconfirm = pm_info.get("noconfirm_flag", "")
        
        cmd = install_cmd[:]
        if noconfirm:
            cmd.append(noconfirm)
        cmd.append(pkg_name)
        
        print(f"  Команда установки: {' '.join(cmd)}")
        reply = input(f"  Установить {pkg_name}? (sudo) [Y/n]: ").strip().lower()
        if reply not in ('', 'y', 'yes', 'да'):
            print("  ⏭ Пропущено")
            return False
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=600
            )
            if result.returncode != 0:
                print(f"  ❌ Ошибка установки: {result.stderr.strip()[:200]}")
                return False
        except Exception as e:
            print(f"  ❌ Ошибка установки: {e}")
            return False
        
        # Повторная проверка
        try:
            result = subprocess.run(
                [python_bin, "-c", "import ensurepip"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                print(f"  ✅ ensurepip доступен")
                return True
        except Exception:
            pass
        
        print(f"  ❌ ensurepip всё ещё не найден после установки")
        return False

    def _install_system_numpy(self) -> bool:
        """Устанавливает numpy из пакетного менеджера (для стратегии system).
        Системный numpy собран под базовый amd64, работает на старом CPU.
        Возвращает True, если установка прошла успешно.
        """
        os_info = self.detector.detect_os()
        pkg_manager = os_info.get("pkg_manager")
        if not pkg_manager:
            return False
        
        # Маппинг пакетов numpy для разных пакетных менеджеров
        numpy_packages = {
            "apt": "python3-numpy",
            "dnf": "python3-numpy",
            "pacman": "python-numpy",
            "zypper": "python3-numpy",
        }
        
        pkg_name = numpy_packages.get(pkg_manager)
        if not pkg_name:
            return False
        
        pm_info = self.detector.PKG_MANAGERS.get(pkg_manager, {})
        install_cmd = pm_info.get("install_cmd", [])
        noconfirm = pm_info.get("noconfirm_flag", "")
        
        cmd = install_cmd[:]
        if noconfirm:
            cmd.append(noconfirm)
        cmd.append(pkg_name)
        
        print(f"  Установка системного numpy (собран под базовый amd64)...")
        print(f"  Команда: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=600
            )
            if result.returncode != 0:
                print(f"  ⚠ Ошибка установки: {result.stderr.strip()[:200]}")
                return False
        except Exception as e:
            print(f"  ⚠ Ошибка установки: {e}")
            return False
        
        print(f"  ✅ Системный numpy установлен")
        return True

    def _get_packages_to_install(self):
        """Возвращает список пакетов для установки из pip.
        Для стратегии system: numpy ставится из пакетного менеджера, а не из pip.
        """
        if self._strategy == "pip":
            return self.BASE_PACKAGES
        elif self._strategy == "system":
            # Убираем numpy из pip — ставим из пакетного менеджера
            return [pkg for pkg in self.PIP_ONLY_PACKAGES if not pkg.startswith("numpy")]
        return []

    def _ensure_system_pyqt6(self) -> bool:
        """Пытается установить системный PyQt6 через пакетный менеджер.
        Возвращает True, если после установки PyQt6 работает.
        Спрашивает разрешение пользователя (sudo).
        """
        os_info = self.detector.detect_os()
        pkg_manager = os_info.get("pkg_manager")
        if not pkg_manager or pkg_manager not in self.detector.PKG_MANAGERS:
            print(f"  ⚠ Пакетный менеджер не определён для {os_info.get('distro', '?')}")
            return False

        pm_info = self.detector.PKG_MANAGERS[pkg_manager]
        pyqt6_pkg = pm_info["pyqt6_package"]
        cmd = pm_info["install_cmd"][:]
        if pm_info["noconfirm_flag"]:
            cmd.append(pm_info["noconfirm_flag"])
        cmd.append(pyqt6_pkg)

        print(f"  Системный PyQt6 не найден.")
        print(f"  Команда установки: {' '.join(cmd)}")
        reply = input("  Установить системный PyQt6? (sudo) [Y/n]: ").strip().lower()
        if reply not in ('', 'y', 'yes', 'да'):
            print("  ⏭ Пропущено")
            return False

        try:
            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=600
            )
            if result.returncode != 0:
                print(f"  ❌ Ошибка установки: {result.stderr.strip()[:200]}")
                return False
        except Exception as e:
            print(f"  ❌ Ошибка установки: {e}")
            return False

        # Повторная проверка: PyQt6 реально работает (глубокий импорт)
        sys_pyqt6 = self.detector.detect_system_pyqt6()
        if sys_pyqt6.get("installed") and sys_pyqt6.get("works"):
            print(f"  ✅ Системный PyQt6 работает ({sys_pyqt6.get('version', '')})")
            return True
        else:
            print("  ❌ PyQt6 установлен, но не работает на этом CPU "
                  "(возможно, сборка требует SSE4.2/AVX)")
            return False

    def is_installed(self) -> StepStatus:
        """Проверяет, создан ли venv и установлены ли зависимости.
        ГЛУБОКАЯ проверка PyQt6 (from PyQt6.QtWidgets import QApplication),
        а не поверхностный import PyQt6, который обманывает на старом CPU.
        """
        if not os.path.exists(self.python_path):
            return StepStatus.failed("venv не создан (нет bin/python)")
        try:
            result = subprocess.run(
                [self.python_path, "-c",
                 "from PyQt6.QtWidgets import QApplication; "
                 "import requests; import psutil"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return StepStatus.success(
                    f"venv готов, зависимости установлены ({self.venv_dir})"
                )
            return StepStatus.failed(
                "venv создан, но зависимости не установлены "
                "или PyQt6 не работает на этом CPU"
            )
        except Exception as e:
            return StepStatus.failed(f"Ошибка проверки venv: {e}")

    def install(self, progress=None) -> StepStatus:
        """Создаёт venv и устанавливает базовые зависимости."""
        # 0. Проверяем стратегию
        if self._strategy == "none":
            # Старый CPU без системного PyQt6 — пробуем установить
            print("  Процессор без sse4_2/popcnt, системный PyQt6 не найден.")
            if self._ensure_system_pyqt6():
                self._strategy = "system"
            else:
                return StepStatus.failed(
                    "Не удалось определить способ установки PyQt6. "
                    "Процессор не поддерживает sse4_2/popcnt, "
                    "и системный PyQt6 не найден или не работает."
                )

        # 1. Находим Python для venv
        self._report(progress, 10,
                     f"Поиск Python (стратегия: {self._strategy})...")
        python_bin = self._find_python_for_venv()
        if not python_bin:
            return StepStatus.failed(
                "Не найден подходящий Python для создания venv"
            )

        # 1.5. Проверяем ensurepip перед созданием venv
        self._report(progress, 25, "Проверка ensurepip...")
        if not self._check_ensurepip(python_bin):
            return StepStatus.failed(
                "ensurepip не доступен. venv не может быть создан. "
                "Установите python3.X-venv вручную и повторите установку."
            )

        # 2. Создаём venv (--system-site-packages для стратегии system)
        self._report(progress, 30, f"Создание venv: {self.venv_dir}")
        venv_cmd = [python_bin, "-m", "venv"]
        if self._strategy == "system":
            venv_cmd.append("--system-site-packages")
        venv_cmd.append(self.venv_dir)
        try:
            result = subprocess.run(
                venv_cmd, capture_output=True, text=True, timeout=180
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка создания venv: {result.stderr.strip()}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка создания venv: {e}")

        # 3. Обновляем pip (не критично)
        self._report(progress, 50, "Обновление pip...")
        try:
            subprocess.run(
                [self.python_path, "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True, text=True, timeout=180
            )
        except Exception:
            pass

        # 3.5. Для стратегии system — устанавливаем numpy из пакетного менеджера
        if self._strategy == "system":
            self._report(progress, 60, "Установка системного numpy...")
            if not self._install_system_numpy():
                print(f"  ⚠ Системный numpy не установлен. Попытка из pip...")

        # 4. Устанавливаем зависимости из pip
        packages = self._get_packages_to_install()
        self._report(progress, 70,
                     f"Установка зависимостей: {', '.join(packages)}...")
        try:
            result = subprocess.run(
                [self.python_path, "-m", "pip", "install"] + packages,
                capture_output=True, text=True, timeout=900
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка установки зависимостей: {result.stderr.strip()}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка установки зависимостей: {e}")

        # 5. Финальная проверка: PyQt6 реально работает (глубокий импорт)
        self._report(progress, 90, "Проверка работоспособности PyQt6...")
        try:
            result = subprocess.run(
                [self.python_path, "-c",
                 "from PyQt6.QtWidgets import QApplication; print('PyQt6 OK')"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    "PyQt6 установлен, но не работает на этом CPU "
                    f"(exit code {result.returncode})."
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка проверки PyQt6: {e}")

        self._report(progress, 100, "Окружение приложения готово")
        return StepStatus.success(
            f"venv создан, зависимости установлены ({self.venv_dir})"
        )

    def verify(self) -> StepStatus:
        return self.is_installed()
