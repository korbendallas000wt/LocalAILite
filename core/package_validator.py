#!/usr/bin/env python3
"""
installer/package_validator.py — проверка целостности Python пакетов в venv.

Решает проблему race condition (баг #15): если инсталлер падает между установкой
torch и diffusers, numpy может остаться версии 2.x, что ломает работу на старых CPU.

Идемпотентность: при повторном запуске инсталлер увидит битые пакеты и предложит
переустановить, не трогая рабочий алгоритм установки.

Функции:
  validate_venv_packages(venv_python, required_packages) -> ValidationResult
      Проверяет наличие и версии пакетов в venv.

  check_numpy_version(venv_python) -> ValidationResult
      Специфичная проверка numpy < 2 (критично для старых CPU без SSE4.2).

  verify_critical_imports(venv_python) -> ValidationResult
      Проверка импорта критических пакетов (torch, diffusers).
"""

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

@dataclass
class ValidationResult:
    """Результат проверки целостности пакетов."""
    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    package_versions: dict = field(default_factory=dict)

    def __str__(self):
        if self.valid:
            versions = ", ".join(f"{k}={v}" for k, v in self.package_versions.items())
            return f"✅ OK ({versions})"
        return f"❌ Errors: {'; '.join(self.errors)}"


def validate_venv_packages(
    venv_python: str,
    required_packages: Dict[str, str]
) -> ValidationResult:
    """
    Проверяет наличие и версии пакетов в venv.

    Args:
        venv_python: Путь к Python интерпретатору venv
        required_packages: Словарь {package_name: version_spec}
                           Пример: {"torch": ">=2.0", "numpy": "<2"}

    Returns:
        ValidationResult с valid, errors, warnings, package_versions
    """
    errors = []
    warnings = []
    package_versions = {}

    for package, version_spec in required_packages.items():
        try:
            # Проверяем наличие пакета
            result = subprocess.run(
                [venv_python, "-m", "pip", "show", package],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                errors.append(f"Пакет {package} не установлен")
                continue

            # Парсим версию из вывода pip show
            version = None
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':', 1)[1].strip()
                    break

            if not version:
                warnings.append(f"Не удалось определить версию {package}")
                continue

            package_versions[package] = version

            # Проверяем соответствие version_spec (простая проверка)
            if not _check_version_constraint(version, version_spec):
                errors.append(
                    f"{package} {version} не соответствует требованию {version_spec}"
                )

        except subprocess.TimeoutExpired:
            errors.append(f"Таймаут проверки {package}")
        except Exception as e:
            errors.append(f"Ошибка проверки {package}: {e}")

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        package_versions=package_versions
    )


def check_numpy_version(venv_python: str) -> ValidationResult:
    """
    Специфичная проверка numpy < 2 (критично для старых CPU без SSE4.2).

    numpy 2.x требует SSE4.2, которого нет на E5450 и подобных CPU.
    Если numpy >= 2 установлен, но не работает — это race condition.
    """
    errors = []
    warnings = []
    package_versions = {}

    try:
        # Проверяем версию numpy
        result = subprocess.run(
            [venv_python, "-c", "import numpy; print(numpy.__version__)"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            # numpy не установлен или не импортируется
            errors.append("numpy не установлен или не импортируется")
            return ValidationResult(False, errors=errors, package_versions=package_versions)

        version = result.stdout.strip()
        package_versions["numpy"] = version

        # Парсим major версию
        try:
            major = int(version.split('.')[0])
            if major >= 2:
                # Проверяем, работает ли numpy (может быть битый)
                test_result = subprocess.run(
                    [venv_python, "-c", "import numpy; numpy.array([1,2,3]).sum()"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if test_result.returncode != 0:
                    errors.append(
                        f"numpy {version} установлен, но не работает "
                        f"(возможно, требует SSE4.2). Требуется переустановка."
                    )
                else:
                    warnings.append(
                        f"numpy {version} >= 2.0, но работает. "
                        f"Рекомендуется < 2 для совместимости со старыми CPU."
                    )
        except (ValueError, IndexError):
            warnings.append(f"Не удалось распарсить версию numpy: {version}")

    except subprocess.TimeoutExpired:
        errors.append("Таймаут проверки numpy")
    except Exception as e:
        errors.append(f"Ошибка проверки numpy: {e}")

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        package_versions=package_versions
    )


def verify_critical_imports(venv_python: str) -> ValidationResult:
    """
    Проверка импорта критических пакетов (torch, diffusers).

    Это финальная проверка: даже если пакеты установлены, они могут не импортироваться
    из-за битых зависимостей или несовместимости.
    """
    errors = []
    warnings = []
    package_versions = {}

    critical_imports = [
        ("torch", "import torch; print(torch.__version__)"),
        ("diffusers", "from diffusers import StableDiffusionXLPipeline; print('diffusers OK')"),
    ]

    for package, import_cmd in critical_imports:
        try:
            result = subprocess.run(
                [venv_python, "-c", import_cmd],
                capture_output=True,
                text=True,
                timeout=60  # torch долго грузится на старых CPU
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()[:200]
                errors.append(f"{package} не импортируется: {stderr}")
            else:
                # Пытаемся извлечь версию из stdout
                stdout = result.stdout.strip()
                if package == "torch":
                    package_versions[package] = stdout
                else:
                    package_versions[package] = "OK"

        except subprocess.TimeoutExpired:
            errors.append(f"Таймаут импорта {package}")
        except Exception as e:
            errors.append(f"Ошибка импорта {package}: {e}")

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        package_versions=package_versions
    )


def _check_version_constraint(version: str, constraint: str) -> bool:
    """
    Простая проверка версии по ограничению.
    Поддерживает: >=, <=, >, <, ==, !=

    Примеры:
      "2.1.0", ">=2.0" -> True
      "2.4.4", "<2" -> False
    """
    if not constraint:
        return True  # Нет ограничения

    # Парсим оператор и требуемую версию
    operators = ['>=', '<=', '!=', '==', '>', '<']
    op = None
    req_version = None

    for operator in operators:
        if constraint.startswith(operator):
            op = operator
            req_version = constraint[len(operator):]
            break

    if not op or not req_version:
        return True  # Не удалось распарсить — пропускаем

    try:
        # Парсим версии в кортежи чисел
        ver_tuple = tuple(map(int, version.split('.')[:3]))
        req_tuple = tuple(map(int, req_version.split('.')[:3]))

        if op == '>=':
            return ver_tuple >= req_tuple
        elif op == '<=':
            return ver_tuple <= req_tuple
        elif op == '>':
            return ver_tuple > req_tuple
        elif op == '<':
            return ver_tuple < req_tuple
        elif op == '==':
            return ver_tuple == req_tuple
        elif op == '!=':
            return ver_tuple != req_tuple
    except (ValueError, IndexError):
        return True  # Не удалось распарсить — пропускаем

    return True
