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


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(text):
    print(f"\n--- {text} ---")


def main():
    print_header("LocalAILite — бутстрап (уровень 1)")

    # 1. Детекция системы
    print_step("Шаг 0: Диагностика системы")
    detector = HardwareDetector()
    detection = detector.detect_all()

    os_info = detection["os"]
    cpu_info = detection["cpu"]
    ram_info = detection["ram"]
    python_info = detection["python"]

    print(f"  ОС: {os_info['distro']} ({os_info['family']})")
    print(f"  CPU: {cpu_info['model']} ({cpu_info['cores']} ядер)")
    print(f"  RAM: {ram_info['total_gb']:.1f} GB "
          f"(доступно {ram_info['available_gb']:.1f} GB)")
    print(f"  Python совместимый (3.10-3.12): "
          f"{'да' if python_info['has_compatible'] else 'нет'}")

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

    # 4. Шаг окружения (venv)
    print_step("Шаг 3: Создание окружения приложения")
    step_env = StepEnv()
    result = step_env.run(
        progress=lambda pct, msg: print(f"   [{pct:3d}%] {msg}")
    )
    icon = "✅" if result.ok else ("⏭" if result.skipped else "❌")
    print(f"  {icon} {result.message}")

    # 5. Итог
    print_header("Итог")
    if result.ok or result.skipped:
        print("  ✅ Бутстрап завершён!")
        print("  Запуск приложения:")
        print("     venv/bin/python main.py")
        print()
        print("  Следующий шаг (уровень 2):")
        print("     настройка путей и моделей через UI-визард")
    else:
        print("  ❌ Бутстрап не завершён. Проверьте ошибки выше.")
        sys.exit(1)


if __name__ == "__main__":
    main()
