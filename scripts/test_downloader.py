#!/usr/bin/env python3
"""
Тестовый скрипт для проверки model_downloader.py из терминала.

Использование:
    python3 scripts/test_downloader.py --type ollama --model qwen2.5:3b
    python3 scripts/test_downloader.py --type diffusers --model "SDXL Base 1.0" --repo stabilityai/stable-diffusion-xl-base-1.0
"""

import sys
import os
import argparse
import signal

# Добавляем корень проекта в sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication
from utils.config import Config
from core.model_downloader import OllamaDownloader, DiffusersDownloader

def test_ollama_downloader(config, model_name: str):
    """Тестирует OllamaDownloader."""
    print(f"[TEST] Запуск OllamaDownloader для модели: {model_name}")
    
    downloader = OllamaDownloader(config, model_name)
    downloader.set_model_size(2.1)  # qwen2.5:3b ~2.1 GB
    
    # Подключаем сигналы
    downloader.progress_updated.connect(lambda pct, msg: print(f"  [{pct:3d}%] {msg}"))
    downloader.download_finished.connect(
        lambda ok, msg: print(f"[{'✓' if ok else '✗'}] Завершено: {msg}")
    )
    downloader.error_occurred.connect(lambda msg: print(f"[!] Ошибка: {msg}"))
    downloader.download_cancelled.connect(lambda: print("[!] Отменено пользователем"))
    
    # Запускаем
    downloader.start()
    return downloader

def test_diffusers_downloader(config, model_name: str, repo_id: str):
    """Тестирует DiffusersDownloader."""
    print(f"[TEST] Запуск DiffusersDownloader для модели: {model_name}")
    print(f"       Repo ID: {repo_id}")
    
    downloader = DiffusersDownloader(config, model_name)
    downloader.set_repo_id(repo_id)
    downloader.set_model_size(6.9)  # SDXL ~6.9 GB
    
    # Подключаем сигналы
    downloader.progress_updated.connect(lambda pct, msg: print(f"  [{pct:3d}%] {msg}"))
    downloader.download_finished.connect(
        lambda ok, msg: print(f"[{'✓' if ok else '✗'}] Завершено: {msg}")
    )
    downloader.error_occurred.connect(lambda msg: print(f"[!] Ошибка: {msg}"))
    downloader.download_cancelled.connect(lambda: print("[!] Отменено пользователем"))
    
    # Запускаем
    downloader.start()
    return downloader

def main():
    parser = argparse.ArgumentParser(description="Тест model_downloader.py")
    parser.add_argument('--type', choices=['ollama', 'diffusers'], required=True,
                        help='Тип загрузчика: ollama или diffusers')
    parser.add_argument('--model', required=True,
                        help='Имя модели (например, "qwen2.5:3b" или "SDXL Base 1.0")')
    parser.add_argument('--repo', help='HuggingFace repo_id (только для diffusers)')
    
    args = parser.parse_args()
    
    # Создаём QApplication для работы с сигналами Qt
    app = QApplication(sys.argv)
    
    # Загружаем конфигурацию
    config = Config()
    
    # Запускаем тест
    if args.type == 'ollama':
        downloader = test_ollama_downloader(config, args.model)
    elif args.type == 'diffusers':
        if not args.repo:
            print("[!] Для diffusers требуется параметр --repo")
            sys.exit(1)
        downloader = test_diffusers_downloader(config, args.model, args.repo)
    
    # Обработка Ctrl+C для отмены скачивания
    def signal_handler(sig, frame):
        print("\n[!] Получен сигнал отмены (Ctrl+C)...")
        downloader.cancel()
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Запускаем event loop
    print("\n[INFO] Нажмите Ctrl+C для отмены скачивания\n")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
