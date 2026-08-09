"""
installer/detector.py — диагностика железа и окружения.

Принципы:
- ТОЛЬКО stdlib (os, platform, shutil, subprocess, re, glob).
  Никакого psutil/torch — это этап бутстрапа, когда они ещё не установлены.
- Чистый диагност: ничего не устанавливает и не меняет в системе.
- Возвращает факты (dict). Решения принимает advisor.py.
- Идемпотентен: можно вызывать сколько угодно раз.

Контракт:
    detect_os()      -> {distro, family, pkg_manager, kernel}
    detect_cpu()     -> {model, cores, freq_mhz, flags{sse4_2,avx,avx2,fma}}
    detect_ram()     -> {total_gb, available_gb}
    detect_gpu()     -> {vendor, model, vram_gb, driver, cuda_present}
    detect_disk(path)-> {path, total_gb, free_gb, exists, mounted}
    detect_python()  -> {candidates[], compatible[], has_compatible, ...}
    detect_all()     -> всё сразу единым dict
"""

import os
import re
import glob
import shutil
import platform
import subprocess


class HardwareDetector:
    """Диагностика железа и окружения для инсталлера."""

    # Диапазон версий Python, совместимых с torch/diffusers.
    # Проверено на рабочей сборке: 3.12.8 работает, 3.14 — нет.
    PYTHON_COMPAT_MIN = (3, 10)
    PYTHON_COMPAT_MAX = (3, 12)

    # Маппинг пакетных менеджеров: команда установки, флаг, пакет PyQt6
    PKG_MANAGERS = {
        "pacman": {
            "install_cmd": ["sudo", "pacman", "-S"],
            "noconfirm_flag": "--noconfirm",
            "pyqt6_package": "python-pyqt6",
        },
        "apt": {
            "install_cmd": ["sudo", "apt-get", "install"],
            "noconfirm_flag": "-y",
            "pyqt6_package": "python3-pyqt6",
        },
        "dnf": {
            "install_cmd": ["sudo", "dnf", "install"],
            "noconfirm_flag": "-y",
            "pyqt6_package": "python3-pyqt6",
        },
        "zypper": {
            "install_cmd": ["sudo", "zypper", "install"],
            "noconfirm_flag": "-y",
            "pyqt6_package": "python3-pyqt6",
        },
        "emerge": {
            "install_cmd": ["sudo", "emerge"],
            "noconfirm_flag": "",
            "pyqt6_package": "dev-python/PyQt6",
        },
        "xbps": {
            "install_cmd": ["sudo", "xbps-install"],
            "noconfirm_flag": "-y",
            "pyqt6_package": "python3-PyQt6",
        },
    }

    # === ОС и пакетный менеджер ===
    def detect_os(self) -> dict:
        info = {
            "distro": platform.system(),
            "family": "unknown",
            "pkg_manager": None,
            "kernel": platform.release(),
        }
        os_release = {}
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        key, _, val = line.strip().partition("=")
                        os_release[key] = val.strip('"')
        except Exception:
            pass

        info["distro"] = os_release.get("PRETTY_NAME") or os_release.get("NAME") or info["distro"]
        ids = [os_release.get("ID", "").lower()] + os_release.get("ID_LIKE", "").lower().split()

        if any(x in ids for x in ("arch", "manjaro")):
            info["family"], info["pkg_manager"] = "arch", "pacman"
        elif any(x in ids for x in ("debian", "ubuntu")):
            info["family"], info["pkg_manager"] = "debian", "apt"
        elif any(x in ids for x in ("fedora", "rhel", "centos", "rocky", "almalinux")):
            info["family"], info["pkg_manager"] = "fedora", "dnf"
        elif any(x in ids for x in ("suse", "opensuse")):
            info["family"], info["pkg_manager"] = "suse", "zypper"
        elif any(x in ids for x in ("gentoo",)):
            info["family"], info["pkg_manager"] = "gentoo", "emerge"
        elif any(x in ids for x in ("void",)):
            info["family"], info["pkg_manager"] = "void", "xbps"
        return info

    # === CPU ===
    def detect_cpu(self) -> dict:
        info = {
            "model": "",
            "cores": os.cpu_count() or 1,
            "freq_mhz": 0.0,
            "flags": {"sse4_2": False, "popcnt": False, "avx": False, "avx2": False, "fma": False},
        }
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                content = f.read()
            m = re.search(r"model name\s*:\s*(.+)", content)
            if m:
                info["model"] = m.group(1).strip()
            m = re.search(r"cpu MHz\s*:\s*([\d.]+)", content)
            if m:
                info["freq_mhz"] = float(m.group(1))
            m = re.search(r"^flags\s*:\s*(.+)$", content, re.MULTILINE)
            if m:
                flags = m.group(1).split()
                info["flags"] = {
                    "sse4_2": "sse4_2" in flags,
                    "popcnt": "popcnt" in flags,
                    "avx": "avx" in flags,
                    "avx2": "avx2" in flags,
                    "fma": "fma" in flags,
                }
        except Exception:
            pass
        return info

    # === RAM ===
    def detect_ram(self) -> dict:
        info = {"total_gb": 0.0, "available_gb": 0.0}
        try:
            meminfo = {}
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val)
            info["total_gb"] = round(meminfo.get("MemTotal", 0) / (1024 ** 2), 2)
            info["available_gb"] = round(meminfo.get("MemAvailable", 0) / (1024 ** 2), 2)
        except Exception:
            pass
        return info

    # === GPU ===
    def detect_gpu(self) -> dict:
        info = {"vendor": "none", "model": "", "vram_gb": None, "driver": "", "cuda_present": False}
        # 1. NVIDIA: nvidia-smi отвечает = драйвер установлен
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                info["vendor"] = "nvidia"
                info["model"] = parts[0] if parts else ""
                if len(parts) > 1:
                    m = re.match(r"(\d+)", parts[1])
                    if m:
                        info["vram_gb"] = round(int(m.group(1)) / 1024, 1)
                info["driver"] = "nvidia"
                info["cuda_present"] = True
                return info
        except Exception:
            pass
        # 2. lspci: определяем вендора даже без драйвера
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if any(k in line for k in ("VGA compatible controller", "3D controller", "Display controller")):
                        lower = line.lower()
                        model = line.split(":")[-1].strip()
                        if "nvidia" in lower:
                            info.update(vendor="nvidia", model=model, driver="not_installed")
                        elif "amd" in lower or "ati" in lower or "advanced micro devices" in lower:
                            info.update(vendor="amd", model=model, driver="amdgpu")
                        elif "intel" in lower:
                            info.update(vendor="intel", model=model, driver="i915/xe")
                        break
        except Exception:
            pass
        return info

    # === Диск ===
    def detect_disk(self, path: str) -> dict:
        info = {"path": path, "total_gb": 0.0, "free_gb": 0.0, "exists": False, "mounted": False}
        if not path:
            return info
        info["exists"] = os.path.exists(path)
        if not info["exists"]:
            return info
        try:
            usage = shutil.disk_usage(path)
            info["total_gb"] = round(usage.total / (1024 ** 3), 1)
            info["free_gb"] = round(usage.free / (1024 ** 3), 1)
            info["mounted"] = True
        except Exception:
            pass
        return info

    # === Python (ГЛАВНЫЙ метод) ===
    def _get_python_version(self, path: str):
        """Возвращает (tuple_version, str_version) или (None, None)."""
        try:
            result = subprocess.run(
                [path, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                version_str = result.stdout.strip()
                parts = version_str.split(".")
                return tuple(int(p) for p in parts[:3]), version_str
        except Exception:
            pass
        return None, None

    def detect_python(self) -> dict:
        result = {
            "candidates": [],
            "compatible": [],
            "has_compatible": False,
            "system_version": None,
            "compat_range": {"min": "3.10", "max": "3.12"},
        }
        seen = set()
        candidates = []

        # 1. PATH
        for name in ("python3", "python"):
            p = shutil.which(name)
            if p:
                candidates.append((os.path.realpath(p), "path"))

        # 2. pyenv versions
        pyenv_versions = os.path.expanduser("~/.pyenv/versions")
        if os.path.isdir(pyenv_versions):
            for entry in sorted(os.listdir(pyenv_versions)):
                py_bin = os.path.join(pyenv_versions, entry, "bin", "python")
                if os.path.exists(py_bin):
                    candidates.append((os.path.realpath(py_bin), "pyenv"))

        # 3. /usr/bin/python*
        for py_bin in glob.glob("/usr/bin/python*"):
            base = os.path.basename(py_bin)
            if base.endswith("-config"):
                continue
            if re.match(r"^python(\d(\.\d+)?)?$", base) and os.path.exists(py_bin):
                candidates.append((os.path.realpath(py_bin), "usr"))

        for real_path, source in candidates:
            if real_path in seen:
                continue
            seen.add(real_path)
            version_tuple, version_str = self._get_python_version(real_path)
            if version_tuple is None:
                continue
            major, minor = version_tuple[0], version_tuple[1]
            compatible = self.PYTHON_COMPAT_MIN <= (major, minor) <= self.PYTHON_COMPAT_MAX
            cand = {
                "path": real_path,
                "version": list(version_tuple),
                "version_str": version_str,
                "source": source,
                "compatible": compatible,
            }
            result["candidates"].append(cand)
            if compatible:
                result["compatible"].append(cand)

        result["has_compatible"] = len(result["compatible"]) > 0
        for c in result["candidates"]:
            if c["source"] == "path":
                result["system_version"] = c["version_str"]
                break
        return result

    # === Всё сразу ===
    def can_use_pip_pyqt6(self) -> bool:
        """Проверяет, может ли pip-PyQt6 работать на этом CPU.
        Требуются sse4_2 И popcnt (иначе 'Incompatible processor').
        """
        cpu = self.detect_cpu()
        flags = cpu.get("flags", {})
        return flags.get("sse4_2", False) and flags.get("popcnt", False)

    def detect_system_pyqt6(self) -> dict:
        """Проверяет, установлен ли системный PyQt6 и работает ли он.
        Использует системный Python (/usr/bin/python3), а не venv.
        Возвращает {installed: bool, works: bool, version: str, path: str}
        """
        result = {"installed": False, "works": False, "version": "", "path": ""}
        # Находим системный Python (не venv, не pyenv shim)
        system_python = None
        for candidate in ["/usr/bin/python3", "/usr/bin/python"]:
            if os.path.exists(candidate):
                system_python = candidate
                break
        if not system_python:
            system_python = shutil.which("python3")
        if not system_python:
            return result
        # Проверяем, установлен ли PyQt6 в системном Python
        try:
            proc = subprocess.run(
                [system_python, "-c", "import PyQt6; print(PyQt6.__file__)"],
                capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result["installed"] = True
                result["path"] = proc.stdout.strip()
            else:
                return result
        except Exception:
            return result
        # Глубокая проверка: загружаем QtCore (может упасть на старом CPU)
        try:
            proc = subprocess.run(
                [system_python, "-c",
                 "from PyQt6 import QtCore; print(QtCore.PYQT_VERSION_STR)"],
                capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result["works"] = True
                result["version"] = proc.stdout.strip()
        except Exception:
            pass
        return result

    def detect_all(self) -> dict:
        return {
            "os": self.detect_os(),
            "cpu": self.detect_cpu(),
            "ram": self.detect_ram(),
            "gpu": self.detect_gpu(),
            "python": self.detect_python(),
            # disk — отдельный метод, вызывается с конкретным путём из конфига
        }


if __name__ == "__main__":
    import json
    detector = HardwareDetector()
    report = detector.detect_all()
    # Демо: проверим диск для home
    report["disk_home"] = detector.detect_disk(os.path.expanduser("~"))
    print(json.dumps(report, indent=2, ensure_ascii=False))
