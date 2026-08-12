#!/usr/bin/env python3
"""
installer/cli.py — точка входа бутстрапа LocalAILite.

Уровень 1 установки: создаёт минимальное окружение для запуска main.py.
Запуск из корня проекта: python3 installer/cli.py

Что делает:
1. Детектирует систему (detector)
2. Показывает вердикты (advisor)
3. Создаёт структуру data/ (step_config)
4. Создаёт venv + зависимости (step_env)
5. Говорит, как запустить приложение

Идемпотентен: можно запускать повторно — пропустит уже установленное.
Чистый Python, без PyQt — работает на системном Python до создания venv.
"""

import sys
import os

# Добавляем корень проекта в path для импортов installer.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from installer.detector import HardwareDetector
from installer.advisor import Advisor
from installer.steps.step_config import StepConfig
from installer.steps.step_env import StepEnv
from installer.steps.step_paths import StepPaths
from installer.steps.step_ollama import StepOllama
from installer.steps.step_sdxl_env import StepSdxlEnv
from installer.steps.step_models import StepModels


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(text):
    print(f"\n--- {text} ---")


def main():
    print_header("LocalAILite — бутстрап (уровень 1)")
    step_results = {}  # Сбор статусов шагов для честного итога

    # 1. Детекция системы
    print_step("Шаг 0: Диагностика системы")
    detector = HardwareDetector()
    detection = detector.detect_all()

    os_info = detection["os"]
    cpu_info = detection["cpu"]
    ram_info = detection["ram"]
    python_info = detection["python"]

    print(f"  ОС: {os_info['distro']} ({os_info['family']})")
    pkg_mgr = os_info.get('pkg_manager') or 'не определён'
    print(f"  Пакетный менеджер: {pkg_mgr}")
    print(f"  CPU: {cpu_info['model']} ({cpu_info['cores']} ядер)")
    print(f"  RAM: {ram_info['total_gb']:.1f} GB "
          f"(доступно {ram_info['available_gb']:.1f} GB)")
    print(f"  Python совместимый (3.10-3.13): "
          f"{'да' if python_info['has_compatible'] else 'нет'}")

    # Sudo доступ (информативно, не блокируем)
    sudo_info = detection.get("sudo", {})
    if sudo_info.get("has_sudo"):
        print(f"  Sudo доступ: ✅ {sudo_info.get('message', '')}")
    else:
        print(f"  Sudo доступ: ❌ {sudo_info.get('message', '')}")
        print(f"     ⚠ Если потребуется установка системных пакетов (PyQt6, Python 3.12),")
        print(f"        она не сработает. Решение (от root): usermod -aG sudo {sudo_info.get('username', 'USERNAME')}")
        print(f"        Если зависимости уже установлены — инсталлятор пройдёт без sudo.")

    # 2. Вердикты советника
    print_step("Шаг 1: Вердикты советника")
    advisor = Advisor(detector)
    verdict = advisor.advise(detection)

    py_verdict = verdict["python"]
    icon = "✅" if py_verdict["ok"] else "❌"
    print(f"  {icon} Python: {py_verdict['message']}")

    ollama_verdict = verdict["ollama"]
    icon = "✅" if ollama_verdict["supported"] else "❌"
    print(f"  {icon} Ollama: {ollama_verdict['message']}")
    if ollama_verdict.get("recommended_model"):
        print(f"     Модель: {ollama_verdict['recommended_model']}")

    sdxl_verdict = verdict["sdxl"]
    icon = "✅" if sdxl_verdict["supported"] else "❌"
    print(f"  {icon} SDXL: {sdxl_verdict['message']}")
    if sdxl_verdict.get("estimated_time"):
        print(f"     Время: {sdxl_verdict['estimated_time']}")

    if verdict["warnings"]:
        print(f"\n  ⚠ Предупреждения:")
        for w in verdict["warnings"]:
            print(f"     - {w}")

    # 3. Шаг конфигурации (data/)
    print_step("Шаг 2: Создание структуры данных")
    step_config = StepConfig()
    result = step_config.run(
        progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
    )
    icon = "✅" if result.ok else ("⏭" if result.skipped else "❌")
    print(f"  {icon} {result.message}")
    step_results["step_config"] = {"name": "Структура данных", "ok": result.ok, "skipped": result.skipped, "message": result.message}

    # 4. Шаг окружения (venv)
    print_step("Шаг 3: Создание окружения приложения")
    step_env = StepEnv()
    result = step_env.run(
        progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
    )
    icon = "✅" if result.ok else ("⏭" if result.skipped else "❌")
    print(f"  {icon} {result.message}")
    step_results["step_env"] = {"name": "Окружение приложения", "ok": result.ok, "skipped": result.skipped, "message": result.message}

    # 4.5. Запись флагов компонентов в QSettings (через venv python)
    print_step("Шаг 4: Запись флагов компонентов")
    try:
        import subprocess
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        venv_python = os.path.join(project_root, "venv", "bin", "python")
        if os.path.exists(venv_python):
            ollama_flag = str(verdict["ollama"]["supported"])
            sdxl_flag = str(verdict["sdxl"]["supported"])
            result_flags = subprocess.run(
                [venv_python, "-c",
                 "import sys; from utils.config import Config; c = Config(); "
                 "c.set_feature('ollama', sys.argv[1]=='True'); "
                 "c.set_feature('sdxl', sys.argv[2]=='True'); "
                 "c.set_feature('image_prep', True); "
                 "print('Флаги записаны: ollama=' + sys.argv[1] + ', sdxl=' + sys.argv[2] + ', image_prep=True')",
                 ollama_flag, sdxl_flag],
                capture_output=True, text=True, cwd=project_root
            )
            if result_flags.returncode == 0:
                print(f"  ✅ {result_flags.stdout.strip()}")
                step_results["step_flags"] = {"name": "Запись флагов компонентов", "ok": True, "skipped": False, "message": result_flags.stdout.strip()}
            else:
                print(f"  ⚠ Ошибка записи флагов: {result_flags.stderr.strip()}")
                step_results["step_flags"] = {"name": "Запись флагов компонентов", "ok": False, "skipped": False, "message": result_flags.stderr.strip()[:100]}
        else:
            print("  ⏭ venv не найден — флаги не записаны (дефолт: все True)")
            step_results["step_flags"] = {"name": "Запись флагов компонентов", "ok": True, "skipped": True, "message": "venv не найден (дефолт: все True)"}
    except Exception as e:
        print(f"  ⚠ Ошибка записи флагов: {e}")
        step_results["step_flags"] = {"name": "Запись флагов компонентов", "ok": False, "skipped": False, "message": str(e)[:100]}

    # === УРОВЕНЬ 2: Пути, бинарники, окружения, модели ===

    # Шаг 5: Настройка путей
    print_step("Шаг 5: Настройка путей")
    step_paths = StepPaths()
    paths_status = step_paths.is_installed()
    if paths_status.ok:
        print(f"  ⏭ {paths_status.message}")
        step_results["step_paths"] = {"name": "Настройка путей", "ok": True, "skipped": True, "message": paths_status.message}
    else:
        reply = input("  Настроить пути сейчас? [Y/n]: ").strip().lower()
        if reply in ('', 'y', 'yes', 'да'):
            chosen_paths = step_paths.choose_paths_interactive()
            result = step_paths.install(
                progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}"),
                paths=chosen_paths
            )
            icon = "✅" if result.ok else "❌"
            print(f"  {icon} {result.message}")
            step_results["step_paths"] = {"name": "Настройка путей", "ok": result.ok, "skipped": False, "message": result.message}
        else:
            print("  ⏭ Пропущено (пути можно настроить позже через UI)")
            step_results["step_paths"] = {"name": "Настройка путей", "ok": True, "skipped": True, "message": "Пропущено пользователем"}

    # Шаг 6: Бинарник Ollama (только если features/ollama)
    ollama_supported = verdict["ollama"]["supported"]
    if ollama_supported:
        print_step("Шаг 6: Бинарник Ollama")
        step_ollama = StepOllama()
        ollama_status = step_ollama.is_installed()
        if ollama_status.ok:
            print(f"  ⏭ {ollama_status.message}")
            step_results["step_ollama"] = {"name": "Бинарник Ollama", "ok": True, "skipped": True, "message": ollama_status.message}
        else:
            reply = input("  Установить бинарник Ollama (~2.1 GB)? [y/N]: ").strip().lower()
            if reply in ('y', 'yes', 'да'):
                result = step_ollama.install(
                    progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
                )
                icon = "✅" if result.ok else "❌"
                print(f"  {icon} {result.message}")
                step_results["step_ollama"] = {"name": "Бинарник Ollama", "ok": result.ok, "skipped": False, "message": result.message}
            else:
                print("  ⏭ Пропущено (бинарник можно установить позже)")
                step_results["step_ollama"] = {"name": "Бинарник Ollama", "ok": True, "skipped": True, "message": "Пропущено пользователем"}
    else:
        print_step("Шаг 6: Бинарник Ollama")
        print(f"  ⏭ Пропущено: {verdict['ollama']['message']}")
        step_results["step_ollama"] = {"name": "Бинарник Ollama", "ok": True, "skipped": True, "message": verdict['ollama']['message']}

    # Шаг 7: SDXL окружение (только если features/sdxl)
    sdxl_supported = verdict["sdxl"]["supported"]
    if sdxl_supported:
        print_step("Шаг 7: SDXL окружение (torch/diffusers)")
        step_sdxl_env = StepSdxlEnv()
        sdxl_env_status = step_sdxl_env.is_installed()
        if sdxl_env_status.ok:
            print(f"  ⏭ {sdxl_env_status.message}")
            step_results["step_sdxl_env"] = {"name": "SDXL окружение", "ok": True, "skipped": True, "message": sdxl_env_status.message}
        else:
            reply = input("  Создать SDXL окружение (~6 GB)? [y/N]: ").strip().lower()
            if reply in ('y', 'yes', 'да'):
                result = step_sdxl_env.install(
                    progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
                )
                icon = "✅" if result.ok else "❌"
                print(f"  {icon} {result.message}")
                step_results["step_sdxl_env"] = {"name": "SDXL окружение", "ok": result.ok, "skipped": False, "message": result.message}
            else:
                print("  ⏭ Пропущено (SDXL окружение можно создать позже)")
                step_results["step_sdxl_env"] = {"name": "SDXL окружение", "ok": True, "skipped": True, "message": "Пропущено пользователем"}
    else:
        print_step("Шаг 7: SDXL окружение")
        print(f"  ⏭ Пропущено: {verdict['sdxl']['message']}")
        step_results["step_sdxl_env"] = {"name": "SDXL окружение", "ok": True, "skipped": True, "message": verdict['sdxl']['message']}

    # Шаг 8: Скачивание моделей (только если есть хотя бы один компонент)
    if ollama_supported or sdxl_supported:
        print_step("Шаг 8: Скачивание моделей")
        step_models = StepModels()
        models_status = step_models.is_installed()
        if models_status.ok:
            print(f"  ⏭ {models_status.message}")
            step_results["step_models"] = {"name": "Скачивание моделей", "ok": True, "skipped": True, "message": models_status.message}
        else:
            reply = input("  Скачать модели (рекомендованные советником)? [y/N]: ").strip().lower()
            if reply in ('y', 'yes', 'да'):
                result = step_models.install(
                    progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
                )
                icon = "✅" if result.ok else "❌"
                print(f"  {icon} {result.message}")
                step_results["step_models"] = {"name": "Скачивание моделей", "ok": result.ok, "skipped": False, "message": result.message}
            else:
                print("  ⏭ Пропущено (модели можно скачать позже)")
                step_results["step_models"] = {"name": "Скачивание моделей", "ok": True, "skipped": True, "message": "Пропущено пользователем"}
    else:
        print_step("Шаг 8: Скачивание моделей")
        print("  ⏭ Пропущено: нет поддерживаемых компонентов")
        step_results["step_models"] = {"name": "Скачивание моделей", "ok": True, "skipped": True, "message": "Нет поддерживаемых компонентов"}

    # 9. Итог (честный, с анализом статусов шагов)
    print_header("Итог")
    failed_steps = [k for k, v in step_results.items() if not v.get("ok") and not v.get("skipped")]
    if failed_steps:
        print(f"  ⚠ Установка завершена с ошибками ({len(failed_steps)} из {len(step_results)} шагов провалились)")
        print()
        print("  Проваленные шаги:")
        for step_id in failed_steps:
            s = step_results[step_id]
            print(f"     ❌ {s['name']}: {s['message']}")
        print()
        print("  Повторите установку после исправления проблем.")
    else:
        print("  ✅ Установка завершена!")
        print("  Запуск приложения:")
        print("     venv/bin/python main.py")
        print()
        print("  Компоненты:")
        print(f"     Ollama: {'✅ поддерживается' if ollama_supported else '❌ не поддерживается'}")
        print(f"     SDXL:   {'✅ поддерживается' if sdxl_supported else '❌ не поддерживается'}")
        print(f"     Visual editor: ✅ всегда доступен")


if __name__ == "__main__":
    main()
