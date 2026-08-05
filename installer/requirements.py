"""
installer/requirements.py — пороги и требования для вердиктов.
Все числовые пороги в одном месте. advisor.py применяет их к фактам от detector.py.

Примечание: пороги совместимости Python (3.10–3.12) живут в detector.py
(PYTHON_COMPAT_MIN/MAX), чтобы не дублировать. При будущей чистке можно
централизовать сюда.
"""

# === RAM (GB) ===
RAM_MIN_FOR_APP_GB = 4        # минимум для запуска приложения + Ollama
RAM_SDXL_MIN_GB = 12          # минимум для SDXL (нужно ~11 GB + запас)
RAM_SDXL_COMFORTABLE_GB = 16  # SDXL комфортно

# === Диск (GB) ===
DISK_MIN_FREE_GB = 10         # минимум свободного места для установки
DISK_SDXL_VENV_GB = 6         # venv с torch+diffusers
DISK_SDXL_MODEL_GB = 7        # одна SDXL модель
DISK_OLLAMA_MODEL_3B_GB = 2   # Ollama модель ~3B
DISK_OLLAMA_MODEL_7B_GB = 5   # Ollama модель ~7B

# === CPU ===
CPU_CORES_MIN = 2             # минимум ядер
CPU_CORES_RECOMMENDED = 4     # рекомендуется

# === Модели Ollama под RAM ===
# (min_ram_gb, max_ram_gb, recommended_model)
OLLAMA_MODELS_BY_RAM = [
    (0, 6, "qwen2.5-coder:0.5b"),
    (6, 10, "qwen2.5-coder:3b"),
    (10, 20, "qwen2.5-coder:7b"),
    (20, 999, "qwen2.5-coder:14b"),
]
