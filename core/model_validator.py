#!/usr/bin/env python3
"""
core/model_validator.py — проверка целостности моделей (v3, двухуровневая).

Два уровня:

  БЫСТРАЯ (структурная, мгновенная, БЕЗ чтения содержимого):
    - Diffusers: структура HF cache + отсутствие .incomplete + размеры > 0
    - Ollama:    манифест + наличие blobs + точные размеры

  ГЛУБОКАЯ (хэш, читает файлы, с прогрессом):
    - Diffusers: SHA256 файлов blobs/ (имя 64 hex = хэш содержимого)
    - Ollama:    SHA256 blobs против digest из манифеста

Публичный контракт (сохранён для инсталлера и генерации):
  validate_model(model_path, expected_metadata=None) -> ValidationResult
  validate_ollama_model(model_name, ollama_models_path=None) -> ValidationResult
  validate_hf_cache_structure(model_path) -> ValidationResult
  validate_single_file(file_path, expected_size=None) -> ValidationResult

Новое в v3:
  validate_model_fast(model_path) -> ValidationResult
  validate_model_deep(model_path, progress=None) -> ValidationResult
  validate_ollama_model_deep(model_name, ollama_models_path=None, progress=None) -> ValidationResult
"""

import os
import json
import hashlib
from dataclasses import dataclass, field

_HASH_HEX = set("0123456789abcdef")
_CHUNK = 8 * 1024 * 1024  # 8 MB


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


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _is_hex(name: str, length: int) -> bool:
    """True, если name — ровно length hex-символов."""
    return len(name) == length and all(c in _HASH_HEX for c in name.lower())


class ValidationCancelled(Exception):
    """Поднимается при отмене проверки во время хэширования."""


def _sha256_file(path: str, cancel_check=None) -> str:
    """SHA256 файла (чанками, без загрузки в память целиком).

    cancel_check() -> bool: если вернул True, хэширование
    прерывается исключением ValidationCancelled.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            if cancel_check is not None and cancel_check():
                raise ValidationCancelled()
            h.update(chunk)
    return h.hexdigest()


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _find_incomplete(model_path: str) -> list:
    """Ищет .incomplete в blobs/ — след прерванной загрузки."""
    out = []
    blobs_dir = os.path.join(model_path, "blobs")
    if os.path.isdir(blobs_dir):
        for name in os.listdir(blobs_dir):
            if name.endswith(".incomplete"):
                out.append(name)
    return out


def _find_zero_size(model_path: str) -> list:
    """Ищет пустые (0 байт) файлы в blobs/."""
    out = []
    blobs_dir = os.path.join(model_path, "blobs")
    if os.path.isdir(blobs_dir):
        for name in os.listdir(blobs_dir):
            if name.endswith(".incomplete"):
                continue
            p = os.path.join(blobs_dir, name)
            if os.path.isfile(p) and os.path.getsize(p) == 0:
                out.append(name)
    return out


def _find_broken_symlinks(directory: str) -> list:
    """Находит битые симлинки (рекурсивно)."""
    broken = []
    for root, dirs, files in os.walk(directory):
        for name in files + dirs:
            path = os.path.join(root, name)
            if os.path.islink(path) and not os.path.exists(path):
                broken.append(os.path.relpath(path, directory))
    return broken


# ---------------------------------------------------------------------------
# БЫСТРАЯ проверка (структурная)
# ---------------------------------------------------------------------------

def validate_model_fast(model_path: str) -> ValidationResult:
    """Быстрая строгая проверка БЕЗ чтения содержимого файлов.

    Для HF cache: структура + нет .incomplete + нет нулевых файлов.
    Для single-file / распакованной папки: базовая структура.
    """
    if not os.path.exists(model_path):
        return ValidationResult(False, errors=[f"Путь не существует: {model_path}"])

    if os.path.isfile(model_path):
        return validate_single_file(model_path)

    if os.path.isdir(model_path):
        blobs_dir = os.path.join(model_path, "blobs")

        # Распакованная модель без blobs/ (папка с model_index.json)
        if not os.path.isdir(blobs_dir):
            if os.path.exists(os.path.join(model_path, "model_index.json")):
                return _validate_unpacked_fast(model_path)
            return ValidationResult(
                False, errors=["Не HF cache и нет model_index.json"])

        # HF cache
        result = validate_hf_cache_structure(model_path)
        if not result.valid:
            return result

        incomplete = _find_incomplete(model_path)
        if incomplete:
            result.errors.append(
                f"Прерванная загрузка: {len(incomplete)} файл(ов) .incomplete")

        zero = _find_zero_size(model_path)
        if zero:
            result.errors.append(
                f"Пустые файлы (0 байт): {len(zero)} шт. в blobs/")

        result.valid = len(result.errors) == 0
        return result

    return ValidationResult(False, errors=[f"Неизвестный тип: {model_path}"])


def _validate_unpacked_fast(model_path: str) -> ValidationResult:
    """Быстрая проверка распакованной папки (без blobs/)."""
    errors = []
    if not os.path.exists(os.path.join(model_path, "model_index.json")):
        errors.append("Нет model_index.json")
    for req in ("unet", "vae", "text_encoder", "text_encoder_2"):
        if not os.path.isdir(os.path.join(model_path, req)):
            errors.append(f"Нет обязательной папки: {req}/")
    return ValidationResult(len(errors) == 0, errors=errors)


def validate_model(model_path: str, expected_metadata: dict = None) -> ValidationResult:
    """Основная функция проверки. КОНТРАКТ СОХРАНЁН.

    Без expected_metadata — быстрая строгая проверка.
    С expected_metadata — дополнительно сверка размеров с метаданными.
    """
    result = validate_model_fast(model_path)
    if not result.valid:
        return result
    if expected_metadata and os.path.isdir(model_path):
        size_result = _validate_file_sizes(model_path, expected_metadata)
        result.errors.extend(size_result.errors)
        result.warnings.extend(size_result.warnings)
        result.valid = len(result.errors) == 0
    return result


def validate_hf_cache_structure(model_path: str) -> ValidationResult:
    """Проверка структуры HF cache (контракт сохранён)."""
    errors = []
    warnings = []

    blobs_dir = os.path.join(model_path, "blobs")
    if not os.path.isdir(blobs_dir):
        return ValidationResult(False, errors=[f"Отсутствует папка blobs/: {blobs_dir}"])

    snapshots_dir = os.path.join(model_path, "snapshots")
    if not os.path.isdir(snapshots_dir):
        return ValidationResult(False, errors=[f"Отсутствует папка snapshots/: {snapshots_dir}"])

    snapshot_hashes = [d for d in os.listdir(snapshots_dir)
                       if os.path.isdir(os.path.join(snapshots_dir, d))]
    if not snapshot_hashes:
        return ValidationResult(False, errors=[f"Нет snapshot'ов в {snapshots_dir}"])

    snapshot_path = os.path.join(snapshots_dir, snapshot_hashes[0])

    if not os.path.exists(os.path.join(snapshot_path, "model_index.json")):
        errors.append(f"Отсутствует model_index.json в {snapshot_path}")

    for req_dir in ("unet", "vae", "text_encoder", "text_encoder_2"):
        if not os.path.isdir(os.path.join(snapshot_path, req_dir)):
            errors.append(f"Отсутствует обязательная папка: {req_dir}/")

    broken = _find_broken_symlinks(snapshot_path)
    if broken:
        errors.append(f"Битые симлинки ({len(broken)}): {broken[:5]}...")

    return ValidationResult(len(errors) == 0, errors=errors, warnings=warnings)


def validate_single_file(file_path: str, expected_size: int = None) -> ValidationResult:
    """Проверка single-file модели (контракт сохранён)."""
    errors = []
    warnings = []

    if not os.path.isfile(file_path):
        return ValidationResult(False, errors=[f"Файл не существует: {file_path}"])

    actual_size = os.path.getsize(file_path)
    if actual_size == 0:
        errors.append(f"Файл пустой: {file_path}")

    if expected_size is not None:
        tolerance = expected_size * 0.01
        if abs(actual_size - expected_size) > tolerance:
            errors.append(
                f"Размер файла не совпадает: ожидалось {expected_size}, "
                f"фактически {actual_size}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.safetensors', '.ckpt', '.bin', '.pt'):
        warnings.append(f"Необычное расширение: {ext}")

    return ValidationResult(len(errors) == 0, errors=errors, warnings=warnings)


def _validate_file_sizes(model_path: str, expected_metadata: dict) -> ValidationResult:
    """Сверка размеров файлов с expected_metadata (контракт сохранён)."""
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
        tolerance = expected_size * 0.01
        if abs(actual_size - expected_size) > tolerance:
            errors.append(
                f"Размер {expected_file}: ожидалось {expected_size}, "
                f"фактически {actual_size}")

    return ValidationResult(len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# ГЛУБОКАЯ проверка (хэши, с прогрессом)
# ---------------------------------------------------------------------------

def validate_model_deep(model_path: str, progress=None,
                        cancel_check=None) -> ValidationResult:
    """Глубокая проверка Diffusers-модели: хэши файлов в blobs/.

    Сначала быстрая проверка (если структура битая — хэшировать нет смысла).
    Затем для каждого файла с именем 64 hex (SHA256, Git LFS) считает SHA256
    и сравнивает с именем. Файлы 40 hex (SHA1, Git-объекты) и прочие —
    только размер (проверены в быстрой), чтобы не давать ложных срабатываний.

    progress(current, total, message) — для прогрессбара.
    """
    progress = progress or (lambda c, t, m: None)

    fast = validate_model_fast(model_path)
    if not fast.valid:
        return fast

    # Single-file: локального хэша нет — быстрая проверка есть потолок
    if os.path.isfile(model_path):
        return fast

    blobs_dir = os.path.join(model_path, "blobs")
    if not os.path.isdir(blobs_dir):
        # Распакованная папка: нет blobs для хэширования
        return fast

    blobs = sorted(
        f for f in os.listdir(blobs_dir)
        if os.path.isfile(os.path.join(blobs_dir, f)) and not f.endswith(".incomplete"))

    errors = []
    warnings = []
    total = len(blobs)
    checked = 0

    for i, blob_name in enumerate(blobs, 1):
        blob_path = os.path.join(blobs_dir, blob_name)
        size = os.path.getsize(blob_path)
        progress(i, total,
                 f"Хэш {i}/{total}: {blob_name[:12]}… ({_fmt_size(size)})")

        if _is_hex(blob_name, 64):
            actual = _sha256_file(blob_path, cancel_check)
            checked += 1
            if actual.lower() != blob_name.lower():
                errors.append(
                    f"Хэш не совпал {blob_name[:12]}…: "
                    f"ожидался {blob_name[:12]}…, получен {actual[:12]}…")

    if total > 0 and checked == 0:
        warnings.append("Не найдено SHA256-blob'ов для проверки хэшей")

    return ValidationResult(len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def validate_ollama_model(model_name: str, ollama_models_path: str = None) -> ValidationResult:
    """Быстрая проверка Ollama-модели: манифест + blobs + точные размеры.
    КОНТРАКТ СОХРАНЁН.
    """
    if ollama_models_path is None:
        ollama_models_path = os.path.expanduser("~/.ollama/models")

    errors = []
    warnings = []

    if not os.path.isdir(ollama_models_path):
        return ValidationResult(False, errors=[f"Папка моделей Ollama не найдена: {ollama_models_path}"])

    manifests_dir = os.path.join(ollama_models_path, "manifests", "registry.ollama.ai", "library")
    if not os.path.isdir(manifests_dir):
        return ValidationResult(False, errors=[f"Нет папки манифестов: {manifests_dir}"])

    if ":" in model_name:
        name, tag = model_name.split(":", 1)
    else:
        name, tag = model_name, "latest"

    manifest_path = os.path.join(manifests_dir, name, tag)
    if not os.path.isfile(manifest_path):
        return ValidationResult(False, errors=[f"Манифест не найден: {manifest_path}"])

    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        return ValidationResult(False, errors=[f"Ошибка чтения манифеста: {e}"])

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

        blob_name = digest.replace(":", "-")
        blob_path = os.path.join(blobs_dir, blob_name)

        if not os.path.isfile(blob_path):
            errors.append(f"Blob отсутствует: {blob_name} ({media_type})")
            continue

        actual_size = os.path.getsize(blob_path)
        if actual_size != expected_size:
            errors.append(
                f"Размер blob {blob_name}: ожидалось {expected_size}, "
                f"фактически {actual_size}")

    return ValidationResult(len(errors) == 0, errors=errors, warnings=warnings)


def validate_ollama_model_deep(model_name: str, ollama_models_path: str = None,
                               progress=None,
                               cancel_check=None) -> ValidationResult:
    """Глубокая проверка Ollama: SHA256 каждого blob против digest манифеста.

    Сначала быстрая проверка (размеры). Затем хэши.
    progress(current, total, message) — для прогрессбара.
    """
    progress = progress or (lambda c, t, m: None)

    fast = validate_ollama_model(model_name, ollama_models_path)
    if not fast.valid:
        return fast

    if ollama_models_path is None:
        ollama_models_path = os.path.expanduser("~/.ollama/models")

    if ":" in model_name:
        name, tag = model_name.split(":", 1)
    else:
        name, tag = model_name, "latest"

    manifest_path = os.path.join(
        ollama_models_path, "manifests", "registry.ollama.ai", "library", name, tag)
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        return ValidationResult(False, errors=[f"Ошибка чтения манифеста: {e}"])

    layers = manifest.get("layers", [])
    blobs_dir = os.path.join(ollama_models_path, "blobs")

    errors = []
    total = len(layers)
    for i, layer in enumerate(layers, 1):
        digest = layer.get("digest", "")
        media_type = layer.get("mediaType", "")
        blob_name = digest.replace(":", "-")
        blob_path = os.path.join(blobs_dir, blob_name)
        progress(i, total, f"Хэш {i}/{total}: {media_type}")

        if not os.path.isfile(blob_path):
            errors.append(f"Blob отсутствует: {blob_name}")
            continue

        if digest.startswith("sha256:"):
            expected_hash = digest.split(":", 1)[1].lower()
            actual_hash = _sha256_file(blob_path, cancel_check)
            if actual_hash.lower() != expected_hash:
                errors.append(f"Хэш blob не совпал: {blob_name[:16]}…")

    return ValidationResult(len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Метаданные из HF API (опционально, сеть; в проверке не используется)
# ---------------------------------------------------------------------------

def get_model_metadata_from_hf(model_id: str, revision: str = "main") -> dict:
    """{file_path: size} из HF API или None. Требует сеть."""
    import requests
    url = f"https://huggingface.co/api/models/{model_id}/tree/{revision}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        files = resp.json()
        metadata = {}
        for file_info in files:
            if file_info.get("type") == "file":
                metadata[file_info.get("path", "")] = file_info.get("size", 0)
        return metadata if metadata else None
    except Exception:
        return None
