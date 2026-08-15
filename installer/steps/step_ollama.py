"""
installer/steps/step_ollama.py — шаг установки бинарника Ollama (уровень 2).

Скачивает бинарник Ollama с GitHub releases, распаковывает в bin/ollama/,
устанавливает права на исполнение, записывает пути в Config.

Идемпотентен: если бинарник уже есть и работает — пропускает.
Чистый Python, БЕЗ PyQt — работает в CLI-бутстрапе.
"""

import os
import subprocess
import shutil
import stat

try:
    from installer.steps.base import InstallStep, StepStatus
except ImportError:
    from steps.base import InstallStep, StepStatus


class StepOllama(InstallStep):
    """Скачивание и установка бинарника Ollama."""

    id = "ollama"
    name = "Бинарник Ollama"
    description = "Скачивание и установка Ollama (~2.1 GB)"

    # URL для скачивания (linux-amd64 tgz)
    OLLAMA_RELEASE_URL = "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst"

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = self._find_project_root()
        self.base_dir = base_dir
        self.venv_python = os.path.join(base_dir, "venv", "bin", "python")
        # Пути читаются из Config динамически (см. _get_paths)

    def _get_paths(self) -> dict:
        """Читает пути Ollama из Config с fallback на дефолты из step_paths.
        
        Контракт: ollama/binary_path — это путь к ФАЙЛУ бинарника
        (например, .../bin/ollama/bin/ollama), а НЕ к папке.
        Определяем тип и извлекаем папку установки.
        """
        binary_path = self._read_config_value("ollama/binary_path", "")
        lib_path = self._read_config_value("ollama/lib_path", "")
        
        # Fallback на дефолты (путь к файлу, как в PathsManager)
        if not binary_path:
            binary_path = os.path.join(self.base_dir, "bin", "ollama", "bin", "ollama")
        
        # Определяем: binary_path — файл бинарника или папка установки?
        if os.path.isfile(binary_path):
            # Существующий файл — это бинарник
            ollama_bin = binary_path
            install_dir = os.path.dirname(os.path.dirname(binary_path))
        elif binary_path.endswith("/ollama") and not os.path.isdir(binary_path):
            # Путь заканчивается на /ollama и не является папкой — это файл
            ollama_bin = binary_path
            install_dir = os.path.dirname(os.path.dirname(binary_path))
        else:
            # Путь к папке установки — бинарник в {binary_path}/bin/ollama
            install_dir = binary_path
            ollama_bin = os.path.join(binary_path, "bin", "ollama")
        
        if not lib_path:
            lib_path = os.path.join(install_dir, "lib", "ollama")
        
        return {
            "binary_path": binary_path,
            "lib_path": lib_path,
            "ollama_bin": ollama_bin,
            "install_dir": install_dir,
        }

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

    def _find_existing_ollama(self) -> str:
        """Ищет существующий бинарник Ollama."""
        paths = self._get_paths()
        ollama_bin = paths['ollama_bin']
        # 1. Локальный (из Config или дефолт)
        if ollama_bin and os.path.exists(ollama_bin) and os.access(ollama_bin, os.X_OK):
            return ollama_bin
        # 2. Системный (в PATH)
        system_bin = shutil.which("ollama")
        if system_bin:
            return system_bin
        return ""

    def _check_ollama_works(self, binary_path: str) -> bool:
        """Проверяет, что бинарник запускается."""
        try:
            result = subprocess.run(
                [binary_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def _write_config_paths(self, binary_path: str, lib_path: str) -> bool:
        """Записывает пути в QSettings через venv python."""
        if not os.path.exists(self.venv_python):
            return False
        script = (
            f"from utils.config import Config; c = Config(); "
            f"c.set('ollama/binary_path', '{binary_path}'); "
            f"c.set('ollama/lib_path', '{lib_path}')"
        )
        try:
            result = subprocess.run(
                [self.venv_python, "-c", script],
                capture_output=True, text=True, timeout=10, cwd=self.base_dir
            )
            return result.returncode == 0
        except Exception:
            return False

    def _download_with_progress(self, url: str, dest: str, progress=None) -> bool:
        """Скачивает файл с прогрессом (через curl или wget)."""
        # Пробуем curl сначала (есть почти везде)
        curl_bin = shutil.which("curl")
        if curl_bin:
            cmd = [curl_bin, "-L", "-#", "-o", dest, url]
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True
                )
                # Читаем вывод построчно для прогресса
                last_pct = 0
                for line in proc.stdout:
                    line = line.strip()
                    if line and "%" in line:
                        # Парсим процент из вывода curl -#
                        try:
                            pct_str = line.split("%")[0].strip().split()[-1]
                            pct = int(pct_str)
                            if pct > last_pct:
                                self._report(progress, pct // 2, f"Скачивание: {pct}%")
                                last_pct = pct
                        except (ValueError, IndexError):
                            pass
                proc.wait()
                return proc.returncode == 0
            except Exception:
                pass

        # Fallback: wget
        wget_bin = shutil.which("wget")
        if wget_bin:
            cmd = [wget_bin, "-q", "--show-progress", "-O", dest, url]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                self._report(progress, 50, "Скачивание завершено (wget)")
                return result.returncode == 0
            except Exception:
                pass

        return False

    def _apply_selinux_context(self, binary_path: str, lib_path: str):
        """Снимает SELinux-ограничения с бинарника Ollama (если SELinux активен).
        На Fedora/RHEL с SELinux Enforcing скачанные из интернета бинарники
        блокируются. chcon устанавливает правильную SELinux-метку.
        """
        # Проверяем, активен ли SELinux
        try:
            result = subprocess.run(
                ["getenforce"], capture_output=True, text=True, timeout=5
            )
            selinux_status = result.stdout.strip().lower()
            if selinux_status != "enforcing":
                return  # SELinux не активен или в permissive режиме
        except Exception:
            return  # getenforce не найден (не Fedora/RHEL)

        # SELinux Enforcing — предлагаем снять ограничения
        print(f"  ⚠ SELinux Enforcing обнаружен.")
        print(f"  Бинарник Ollama скачан из интернета и может быть заблокирован.")
        reply = input("  Снять SELinux-ограничения через chcon? (sudo) [Y/n]: ").strip().lower()
        if reply not in ('', 'y', 'yes', 'да'):
            print("  ⏭ Пропущено (возможны проблемы с запуском)")
            return

        # Применяем chcon к бинарнику
        try:
            result = subprocess.run(
                ["sudo", "chcon", "-t", "bin_t", binary_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                print(f"  ✅ SELinux-контекст бинарника установлен (bin_t)")
            else:
                print(f"  ⚠ chcon не сработал: {result.stderr.strip()[:100]}")
        except Exception as e:
            print(f"  ⚠ Ошибка chcon: {e}")

        # Применяем chcon к библиотекам (если есть)
        if os.path.isdir(lib_path):
            try:
                subprocess.run(
                    ["sudo", "chcon", "-R", "-t", "lib_t", lib_path],
                    capture_output=True, text=True, timeout=10
                )
            except Exception:
                pass

    def is_installed(self) -> StepStatus:
        """Проверяет, установлен ли Ollama."""
        paths = self._get_paths()
        binary = self._find_existing_ollama()
        if not binary:
            return StepStatus.failed(
                "Ollama не найден",
                details="Требуется скачивание бинарника"
            )
        if not self._check_ollama_works(binary):
            return StepStatus.failed(
                f"Ollama найден ({binary}), но не запускается",
                details="Возможно, повреждён или несовместим"
            )
        return StepStatus.success(
            f"Ollama установлен: {binary}",
            details=f"lib_dir={paths['lib_path']}"
        )

    def install(self, progress=None) -> StepStatus:
        """Скачивает и устанавливает бинарник Ollama."""
        paths = self._get_paths()
        install_dir = paths['install_dir']
        
        # 1. Создаём папку установки
        self._report(progress, 5, f"Создание папки: {install_dir}")
        os.makedirs(install_dir, exist_ok=True)

        # 2. Скачиваем архив
        archive_path = os.path.join(install_dir, "ollama-linux-amd64.tar.zst")
        self._report(progress, 10, f"Скачивание Ollama (~2.1 GB)...")
        if not self._download_with_progress(self.OLLAMA_RELEASE_URL, archive_path, progress):
            return StepStatus.failed(
                "Не удалось скачать Ollama",
                details=f"URL: {self.OLLAMA_RELEASE_URL}"
            )

        # Проверка размера файла (защита от HTML-ошибок вместо архива)
        file_size = os.path.getsize(archive_path) if os.path.exists(archive_path) else 0
        if file_size < 1024 * 1024:  # < 1 MB — точно не архив Ollama (~2.1 GB)
            return StepStatus.failed(
                f"Скачанный файл слишком мал ({file_size} байт) — вероятно, это HTML-ошибка, а не архив",
                details=f"URL: {self.OLLAMA_RELEASE_URL}"
            )

        # 3. Распаковываем
        self._report(progress, 60, "Распаковка архива...")
        try:
            result = subprocess.run(
                ["tar", "-xf", archive_path, "-C", install_dir],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                return StepStatus.failed(
                    f"Ошибка распаковки: {result.stderr.strip()}"
                )
        except Exception as e:
            return StepStatus.failed(f"Ошибка распаковки: {e}")

        # 4. Удаляем архив
        try:
            os.remove(archive_path)
        except Exception:
            pass

        # 5. Права на исполнение
        self._report(progress, 80, "Установка прав на исполнение...")
        if os.path.exists(paths['ollama_bin']):
            st = os.stat(paths['ollama_bin'])
            os.chmod(paths['ollama_bin'], st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        else:
            return StepStatus.failed(
                "Бинарник ollama не найден после распаковки",
                details=f"Ожидался: {paths['ollama_bin']}"
            )

        # 5.5. SELinux: снимаем ограничения с бинарника (Fedora, RHEL)
        self._apply_selinux_context(paths['ollama_bin'], paths['lib_path'])

        # 6. Проверяем работоспособность
        self._report(progress, 90, "Проверка работоспособности...")
        if not self._check_ollama_works(paths['ollama_bin']):
            return StepStatus.failed(
                "Ollama установлен, но не запускается",
                details=f"binary={paths['ollama_bin']}"
            )

        # 7. Записываем пути в Config
        self._report(progress, 95, "Запись путей в конфиг...")
        self._write_config_paths(paths['ollama_bin'], paths['lib_path'])

        self._report(progress, 100, "Ollama установлен")
        return StepStatus.success(
            f"Ollama установлен: {paths['ollama_bin']}",
            details=f"lib_dir={paths['lib_path']}"
        )

    def verify(self) -> StepStatus:
        """Проверяет после установки."""
        return self.is_installed()
