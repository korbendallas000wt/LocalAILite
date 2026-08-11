#!/usr/bin/env python3
"""
core/model_validator.py — проверка целостности моделей.

Используется инсталлером и (в будущем) менеджером моделей в приложении.

Функции:
  validate_model(model_path, expected_metadata=None) -> ValidationResult
      Основная функция проверки. Если expected_metadata есть (наши модели) —
      проверяет размер + структуру. Если нет (незнакомые) — только структуру.

  validate_hf_cache_structure(model_path) -> ValidationResult
      Проверка структуры HF cache: blobs/, snapshots/, симлинки, обязательные папки.

  validate_single_file(file_path, expected_size=None) -> ValidationResult
      Проверка single-file модели (.safetensors, .ckpt).

  get_model_metadata_from_hf(model_id) -> dict
      Получение metadata из HF API (размеры файлов, список файлов).
      Возвращает {file_path: size} или None при ошибке.
"""

import os
import json
import requests
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Результат проверки целостности модели."""
    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def __str__(self):
        if self.valid:
            return "✅ OK"
        return f"❌ Errors: {'; '.join(self.errors)}"


def validate_model(model_path: str, expected_metadata: dict = None) -> ValidationResult:
    """
    Основная функция проверки целостности модели.

    Args:
        model_path: Путь к модели (папка HF cache или файл)
        expected_metadata: Ожидаемое metadata {file_path: size} из HF API.
                           Если None — проверяется только структура.

    Returns:
        ValidationResult с valid, errors, warnings
    """
    if not os.path.exists(model_path):
        return ValidationResult(False, errors=[f"Путь не существует: {model_path}"])

    # Single-file модель
    if os.path.isfile(model_path):
        return validate_single_file(model_path,
                                     expected_size=expected_metadata.get("size") if expected_metadata else None)

    # HF cache папка
    if os.path.isdir(model_path):
        result = validate_hf_cache_structure(model_path)
        if not result.valid:
            return result

        # Если есть expected_metadata — проверяем размеры
        if expected_metadata:
            size_result = _validate_file_sizes(model_path, expected_metadata)
            result.errors.extend(size_result.errors)
            result.warnings.extend(size_result.warnings)
            result.valid = len(result.errors) == 0

        return result

    return ValidationResult(False, errors=[f"Неизвестный тип: {model_path}"])


def validate_hf_cache_structure(model_path: str) -> ValidationResult:
    """
    Проверка структуры HF cache папки.

    Проверяет:
    1. Наличие папок blobs/, snapshots/
    2. Наличие хотя бы одного snapshot
    3. Наличие model_index.json в snapshot
    4. Живость симлинков (указывают на существующие файлы в blobs/)
    5. Наличие обязательных папок: unet/, vae/, text_encoder/, text_encoder_2/
    """
    errors = []
    warnings = []

    # Проверка blobs/
    blobs_dir = os.path.join(model_path, "blobs")
    if not os.path.isdir(blobs_dir):
        errors.append(f"Отсутствует папка blobs/: {blobs_dir}")
        return ValidationResult(False, errors=errors)

    # Проверка snapshots/
    snapshots_dir = os.path.join(model_path, "snapshots")
    if not os.path.isdir(snapshots_dir):
        errors.append(f"Отсутствует папка snapshots/: {snapshots_dir}")
        return ValidationResult(False, errors=errors)

    # Проверка наличия хотя бы одного snapshot
    snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                       if os.path.isdir(os.path.join(snapshots_dir, d))]
    if not snapshot_hashes:
        errors.append(f"Нет snapshot'ов в {snapshots_dir}")
        return ValidationResult(False, errors=errors)

    # Берём первый snapshot
    snapshot_path = os.path.join(snapshots_dir, snapshot_hashes[0])

    # Проверка model_index.json
    model_index = os.path.join(snapshot_path, "model_index.json")
    if not os.path.exists(model_index):
        errors.append(f"Отсутствует model_index.json: {model_index}")

    # Проверка обязательных папок
    required_dirs = ["unet", "vae", "text_encoder", "text_encoder_2"]
    for req_dir in required_dirs:
        dir_path = os.path.join(snapshot_path, req_dir)
        if not os.path.isdir(dir_path):
            errors.append(f"Отсутствует обязательная папка: {req_dir}/")

    # Проверка живости симлинков
    broken_links = _find_broken_symlinks(snapshot_path)
    if broken_links:
        errors.append(f"Битые симлинки ({len(broken_links)}): {broken_links[:5]}...")

    valid = len(errors) == 0
    return ValidationResult(valid, errors=errors, warnings=warnings)


def validate_single_file(file_path: str, expected_size: int = None) -> ValidationResult:
    """
    Проверка single-file модели (.safetensors, .ckpt).

    Args:
        file_path: Путь к файлу
        expected_size: Ожидаемый размер в байтах (опционально)
    """
    errors = []
    warnings = []

    if not os.path.isfile(file_path):
        return ValidationResult(False, errors=[f"Файл не существует: {file_path}"])

    # Проверка размера
    actual_size = os.path.getsize(file_path)
    if actual_size == 0:
        errors.append(f"Файл пустой: {file_path}")

    if expected_size is not None:
        # Допускаем отклонение 1% (на случай разных версий)
        tolerance = expected_size * 0.01
        if abs(actual_size - expected_size) > tolerance:
            errors.append(
                f"Размер файла не совпадает: ожидалось {expected_size} байт, "
                f"фактически {actual_size} байт"
            )

    # Проверка расширения
    valid_extensions = ['.safetensors', '.ckpt', '.bin', '.pt']
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in valid_extensions:
        warnings.append(f"Необычное расширение: {ext}")

    valid = len(errors) == 0
    return ValidationResult(valid, errors=errors, warnings=warnings)


def get_model_metadata_from_hf(model_id: str, revision: str = "main") -> dict:
    """
    Получение metadata из HF API.

    Args:
        model_id: ID модели (например, "stabilityai/stable-diffusion-xl-base-1.0")
        revision: Ветка/коммит (по умолчанию "main")

    Returns:
        {file_path: size} или None при ошибке
    """
    url = f"https://huggingface.co/api/models/{model_id}/tree/{revision}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None

        files = resp.json()
        metadata = {}
        for file_info in files:
            if file_info.get("type") == "file":
                path = file_info.get("path", "")
                size = file_info.get("size", 0)
                metadata[path] = size

        return metadata if metadata else None

    except Exception:
        return None


def _validate_file_sizes(model_path: str, expected_metadata: dict) -> ValidationResult:
    """Проверка размеров файлов в HF cache."""
    errors = []
    warnings = []

    snapshots_dir = os.path.join(model_path, "snapshots")
    snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                       if os.path.isdir(os.path.join(snapshots_dir, d))]
    if not snapshot_hashes:
        return ValidationResult(False, errors=["Нет snapshot'ов"])

    snapshot_path = os.path.join(snapshots_dir, snapshot_hashes[0])

    for expected_file, expected_size in expected_metadata.items():
        file_path = os.path.join(snapshot_path, expected_file)
        if not os.path.exists(file_path):
            warnings.append(f"Файл отсутствует (возможно, не обязателен): {expected_file}")
            continue

        actual_size = os.path.getsize(file_path)
        # Допускаем отклонение 1%
        tolerance = expected_size * 0.01
        if abs(actual_size - expected_size) > tolerance:
            errors.append(
                f"Размер {expected_file}: ожидалось {expected_size}, "
                f"фактически {actual_size}"
            )

    valid = len(errors) == 0
    return ValidationResult(valid, errors=errors, warnings=warnings)


def _find_broken_symlinks(directory: str) -> list:
    """Находит битые симлинки в директории (рекурсивно)."""
    broken = []
    for root, dirs, files in os.walk(directory):
        for name in files + dirs:
            path = os.path.join(root, name)
            if os.path.islink(path) and not os.path.exists(path):
                broken.append(os.path.relpath(path, directory))
    return broken


def validate_ollama_model(model_name: str, ollama_models_path: str = None) -> ValidationResult:
    """
    Проверка целостности Ollama модели (LLM).

    Ollama хранит модели в собственном формате:
      ~/.ollama/models/
      ├── blobs/                    # Бинарные данные (веса, конфиги)
      │   └── sha256-{hash}
      └── manifests/
          └── registry.ollama.ai/library/{model}/
              └── {tag}             # Манифест JSON

    Манифест содержит список layers, каждый с digest (хэш) и size (размер).
    Blobs хранятся отдельно, имя blob = digest с заменой ":" на "-".

    Проверяет:
    1. Наличие манифеста
    2. Наличие всех blobs, на которые ссылается манифест
    3. Размеры blobs (сравнение с манифестом)

    Args:
        model_name: Имя модели (например, "qwen2.5-coder:3b" или "llama3:latest")
        ollama_models_path: Путь к папке моделей Ollama.
                            По умолчанию ~/.ollama/models

    Returns:
        ValidationResult с valid, errors, warnings
    """
    if ollama_models_path is None:
        ollama_models_path = os.path.expanduser("~/.ollama/models")

    errors = []
    warnings = []

    # Проверка существования папки моделей
    if not os.path.isdir(ollama_models_path):
        return ValidationResult(False, errors=[f"Папка моделей Ollama не найдена: {ollama_models_path}"])

    # Поиск манифеста
    manifests_dir = os.path.join(ollama_models_path, "manifests", "registry.ollama.ai", "library")
    if not os.path.isdir(manifests_dir):
        return ValidationResult(False, errors=[f"Нет папки манифестов: {manifests_dir}"])

    # Разбираем model_name на имя и тег (например, "qwen2.5-coder:3b")
    if ":" in model_name:
        name, tag = model_name.split(":", 1)
    else:
        name, tag = model_name, "latest"

    manifest_path = os.path.join(manifests_dir, name, tag)
    if not os.path.isfile(manifest_path):
        return ValidationResult(False, errors=[f"Манифест не найден: {manifest_path}"])

    # Читаем манифест
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        return ValidationResult(False, errors=[f"Ошибка чтения манифеста: {e}"])

    # Проверяем каждый layer
    blobs_dir = os.path.join(ollama_models_path, "blobs")
    if not os.path.isdir(blobs_dir):
        return ValidationResult(False, errors=[f"Нет папки blobs: {blobs_dir}"])

    layers = manifest.get("layers", [])
    if not layers:
        errors.append("Манифест не содержит layers")

    for layer in layers:
        digest = layer.get("digest", "")
        expected_size = layer.get("size", 0)
        media_type = layer.get("mediaType", "")

        # digest имеет формат "sha256:{hash}", blob хранится как "sha256-{hash}"
        blob_name = digest.replace(":", "-")
        blob_path = os.path.join(blobs_dir, blob_name)

        if not os.path.isfile(blob_path):
            errors.append(f"Blob отсутствует: {blob_name} ({media_type})")
            continue

        actual_size = os.path.getsize(blob_path)
        if actual_size != expected_size:
            errors.append(
                f"Размер blob {blob_name}: ожидалось {expected_size}, "
                f"фактически {actual_size}"
            )

    valid = len(errors) == 0
    return ValidationResult(valid, errors=errors, warnings=warnings)
