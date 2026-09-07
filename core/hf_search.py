"""
core/hf_search.py — поиск моделей на HuggingFace через публичный API.

Асинхронный поиск (QThread) для вкладки «Поиск» Менеджера моделей.
Возвращает список моделей с метаданными для заполнения реестра.

Контракт:
    worker = HFSearchWorker(query, base_filter, category_filter)
    worker.results_ready.connect(on_results)   # list[dict]
    worker.error_occurred.connect(on_error)    # str
    worker.start()

Каждый результат:
    {
        "ref":         "автор/название",       # для add_model_by_ref
        "name":        "Красивое имя",         # для отображения
        "size_gb":     6.9,                     # размер (0 если неизвестен)
        "downloads":   2100000,                 # количество загрузок
        "likes":       5400,                    # лайки
        "tags":        ["sdxl", "text-to-image"],
        "base":        "SDXL",                  # базовая модель (для фильтра)
        "category":    "checkpoint",            # checkpoint / lora / vae
        "packaging":   "hf_cache",              # hf_cache (папка) / file (single-file)
        "description": "Первая строка карточки",
        "url":         "https://huggingface.co/...",
    }
"""

import requests
from PyQt6.QtCore import QThread, pyqtSignal


API_SEARCH_URL = "https://huggingface.co/api/models"
API_TIMEOUT = 30  # секунд на запрос


# === Определение базовой модели по тегам и названию ===

def _detect_base(tags: list, model_id: str) -> str:
    """Определяет базовую модель (SDXL/SD1.5/Flux/SD3/другое) по тегам и имени."""
    tags_lower = [t.lower() for t in tags]
    name_lower = model_id.lower()

    # Порядок важен: сначала более специфичные
    if any(t in ("flux", "flux.1") or t.startswith("flux-") for t in tags_lower) or "flux" in name_lower:
        return "Flux"
    if any(t in ("sd3", "stable-diffusion-3") for t in tags_lower) or "sd3" in name_lower:
        return "SD3"
    if any(t in ("sdxl", "stable-diffusion-xl", "xl") for t in tags_lower) or "sdxl" in name_lower or "xl" in name_lower:
        return "SDXL"
    if any(t in ("sd1.5", "stable-diffusion", "sd") for t in tags_lower):
        return "SD1.5"
    return "Другое"


# === Определение категории (чекпоинт / LoRA / VAE) ===

def _detect_category(tags: list, model_id: str) -> str:
    """Определяет категорию модели по тегам и имени."""
    tags_lower = [t.lower() for t in tags]
    name_lower = model_id.lower()

    if any(t in ("lora",) for t in tags_lower) or "lora" in name_lower:
        return "lora"
    if any(t in ("vae",) for t in tags_lower) or "vae" in name_lower:
        return "vae"
    return "checkpoint"


# === Определение формата (папка / single-file) ===

def _detect_packaging(tags: list, siblings: list) -> str:
    """Определяет формат: hf_cache (папка с model_index.json) или file (single-file)."""
    # Если в репозитории есть model_index.json — это Diffusers-папка
    if siblings:
        filenames = [s.get("rfilename", "") for s in siblings]
        if any(f == "model_index.json" for f in filenames):
            return "hf_cache"
        # Если только .safetensors/.ckpt в корне — это single-file
        if any(f.endswith((".safetensors", ".ckpt")) for f in filenames):
            return "file"
    # По тегам: если есть "diffusers" — скорее всего папка
    tags_lower = [t.lower() for t in tags]
    if "diffusers" in tags_lower:
        return "hf_cache"
    return "file"


# === Получение размера модели ===

def _estimate_size_gb(siblings: list) -> float:
    """Считает суммарный размер файлов в репозитории (в ГБ)."""
    if not siblings:
        return 0.0
    total = sum(s.get("size", 0) for s in siblings if s.get("size"))
    return round(total / (1024 ** 3), 1)


# === Основной воркер поиска ===

class HFSearchWorker(QThread):
    """Асинхронный поиск моделей на HuggingFace."""

    results_ready = pyqtSignal(list)   # список результатов
    error_occurred = pyqtSignal(str)   # сообщение об ошибке

    def __init__(self, query: str, base_filter: str = "Все",
                 category_filter: str = "Все", show_nsfw: bool = False, parent=None):
        super().__init__(parent)
        self._query = query.strip()
        self._base_filter = base_filter
        self._category_filter = category_filter
        self._show_nsfw = show_nsfw

    def run(self):
        try:
            results = self._search()
            self.results_ready.emit(results)
        except requests.exceptions.Timeout:
            self.error_occurred.emit("Превышено время ожидания. Проверь интернет.")
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Нет соединения с HuggingFace. Проверь интернет.")
        except Exception as e:
            self.error_occurred.emit(f"Ошибка поиска: {e}")

    def _search(self) -> list:
        """Выполняет поиск и возвращает отфильтрованный список моделей."""
        # Базовые параметры: ищем модели для генерации изображений
        params = {
            "search": self._query,
            "sort": "downloads",
            "direction": "-1",  # по убыванию
            "limit": 100,
            # Фильтр по типу задачи — только генерация изображений
            "pipeline_tag": "text-to-image",
        }

        response = requests.get(API_SEARCH_URL, params=params, timeout=API_TIMEOUT)
        response.raise_for_status()
        models = response.json()

        results = []
        for m in models:
            model_id = m.get("modelId", "")
            tags = m.get("tags", [])
            siblings = m.get("siblings", [])

            # Локальная фильтрация NSFW: тег «nsfw» или вхождение в имени/пути репо
            # (у части моделей тег отсутствует, но маркер есть в названии)
            tags_lower = [t.lower() for t in tags]
            is_nsfw = ("nsfw" in tags_lower) or ("nsfw" in model_id.lower())
            if not self._show_nsfw and is_nsfw:
                continue

            base = _detect_base(tags, model_id)
            category = _detect_category(tags, model_id)
            packaging = _detect_packaging(tags, siblings)
            # Размер — поисковый API не возвращает размер файлов, пропускаем
            # (доп. запрос к /api/models/{id} замедлит поиск в 10 раз)
            size_gb = 0.0

            # Фильтр по базовой модели
            if self._base_filter != "Все" and base != self._base_filter:
                continue
            # Фильтр по категории
            if self._category_filter != "Все":
                cat_map = {"Чекпоинты": "checkpoint", "LoRA": "lora", "VAE": "vae"}
                if category != cat_map.get(self._category_filter, "checkpoint"):
                    continue

            # Описание — поисковый API не возвращает cardData, пропускаем
            # (доп. запрос к /api/models/{id} замедлит поиск в 10 раз)
            description = ""

            # Красивое имя из model_id
            raw_name = model_id.split("/")[-1] if "/" in model_id else model_id
            display_name = raw_name.replace("-", " ").replace("_", " ").title()

            results.append({
                "ref": model_id,
                "name": display_name,
                "size_gb": size_gb,
                "downloads": m.get("downloads", 0),
                "likes": m.get("likes", 0),
                "tags": tags[:5],
                "base": base,
                "category": category,
                "packaging": packaging,
                "description": description,
                "url": f"https://huggingface.co/{model_id}",
            })

        return results
