"""
installer/advisor.py — вердикты на основе детекции.
Принимает факты от detector.py, применяет пороги из requirements.py,
возвращает честные вердикты.

Принцип: НЕ блокировать, а предупреждать. Дать шанс на чудо.
Каждый вердикт говорит: что потянет, как медленно, что делать.
"""

import os

try:
    from installer.detector import HardwareDetector
    from installer import requirements as req
except ImportError:
    from detector import HardwareDetector
    import requirements as req


class Advisor:
    """Формирует вердикты на основе детекции железа."""

    def __init__(self, detector=None):
        self.detector = detector or HardwareDetector()

    def advise(self, detection: dict = None) -> dict:
        """Главный метод: детекция + вердикты."""
        if detection is None:
            detection = self.detector.detect_all()
        return {
            "python": self._advise_python(detection),
            "ollama": self._advise_ollama(detection),
            "sdxl": self._advise_sdxl(detection),
            "warnings": self._collect_warnings(detection),
            "pkg_manager": detection.get("os", {}).get("pkg_manager", "unknown"),
        }

    # === Python ===
    def _advise_python(self, detection: dict) -> dict:
        py = detection.get("python", {})
        if py.get("has_compatible"):
            best = py["compatible"][0]
            return {
                "ok": True,
                "message": f"Найден совместимый Python {best['version_str']} ({best['source']})",
                "compatible_path": best["path"],
                "compatible_version": best["version_str"],
                "action_needed": "none",
            }
        return {
            "ok": False,
            "message": (
                f"Совместимый Python не найден. "
                f"Системный: {py.get('system_version', '?')}. "
                f"Требуется: {py.get('compat_range', {}).get('min', '3.10')}"
                f"–{py.get('compat_range', {}).get('max', '3.12')}."
            ),
            "compatible_path": None,
            "compatible_version": None,
            "action_needed": "install_python",
        }

    # === Ollama ===
    def _advise_ollama(self, detection: dict) -> dict:
        ram_gb = detection.get("ram", {}).get("total_gb", 0)
        if ram_gb < req.RAM_MIN_FOR_APP_GB:
            return {
                "supported": False,
                "message": f"Слишком мало RAM ({ram_gb:.1f} GB). Минимум {req.RAM_MIN_FOR_APP_GB} GB.",
                "recommended_model": None,
            }
        model = self._pick_ollama_model(ram_gb)
        return {
            "supported": True,
            "message": f"Ollama будет работать на CPU. RAM: {ram_gb:.1f} GB.",
            "recommended_model": model,
        }

    def _pick_ollama_model(self, ram_gb: float) -> str:
        for min_ram, max_ram, model in req.OLLAMA_MODELS_BY_RAM:
            if min_ram <= ram_gb < max_ram:
                return model
        return req.OLLAMA_MODELS_BY_RAM[-1][2]

    # === SDXL / Diffusers ===
    def _advise_sdxl(self, detection: dict) -> dict:
        ram_gb = detection.get("ram", {}).get("total_gb", 0)
        gpu = detection.get("gpu", {})
        cpu = detection.get("cpu", {})
        flags = cpu.get("flags", {})

        if ram_gb < req.RAM_SDXL_MIN_GB:
            return {
                "supported": False,
                "message": (
                    f"Недостаточно RAM для SDXL: {ram_gb:.1f} GB "
                    f"(нужно минимум {req.RAM_SDXL_MIN_GB} GB). "
                    f"Рекомендуем только Ollama-чат."
                ),
                "speed": "none",
                "recommended_size": None,
                "estimated_time": None,
            }

        # NVIDIA + CUDA → быстро
        if gpu.get("vendor") == "nvidia" and gpu.get("cuda_present"):
            return {
                "supported": True,
                "message": (
                    f"NVIDIA GPU ({gpu.get('model', '')}). "
                    f"SDXL будет работать быстро через CUDA."
                ),
                "speed": "fast",
                "recommended_size": "1024x1024",
                "estimated_time": "~30-60 сек на изображение",
            }

        # CPU режим — оцениваем скорость по AVX2 и ядрам
        has_avx2 = flags.get("avx2", False)
        cores = cpu.get("cores", 1)
        if has_avx2 and cores >= req.CPU_CORES_RECOMMENDED:
            speed, size, est = "slow", "512x512", "~5-15 мин на 512x512"
            msg = f"SDXL на CPU (AVX2, {cores} ядер). Медленно, но приемлемо."
        else:
            speed, size, est = "very_slow", "512x512", "~1-2 мин/шаг на 512x512, часы на 1024x1024"
            msg = (
                f"SDXL на CPU, ОЧЕНЬ медленно ({cores} ядер, "
                f"{'AVX2' if has_avx2 else 'без AVX2'}). "
                f"Рекомендуем 512x512 и терпение."
            )
        if gpu.get("vendor") not in ("none", "", None):
            msg += f" Видеокарта ({gpu.get('vendor')}) есть, но для SDXL не используется (нет CUDA)."
        return {
            "supported": True,
            "message": msg,
            "speed": speed,
            "recommended_size": size,
            "estimated_time": est,
        }

    # === Рекомендации моделей (для step_models и UI-визарда) ===
    def recommend_models(self, detection: dict = None) -> dict:
        """Возвращает рекомендации моделей с альтернативами и предупреждениями.
        
        Принцип: не навязываем, но помогаем максимально.
        Рекомендация выделена, альтернативы показаны с честными заметками.
        Пользователь может выбрать любую модель или добавить свою.
        
        Returns:
            dict: {
                "ollama": {"recommended": str, "alternatives": [...]},
                "sdxl": {"recommended": str, "alternatives": [...]}
            }
        """
        if detection is None:
            detection = self.detector.detect_all()
        
        ram_gb = detection.get("ram", {}).get("total_gb", 0)
        cpu = detection.get("cpu", {})
        gpu = detection.get("gpu", {})
        cores = cpu.get("cores", 1)
        has_avx2 = cpu.get("flags", {}).get("avx2", False)
        has_cuda = gpu.get("vendor") == "nvidia" and gpu.get("cuda_present", False)
        
        return {
            "ollama": self._recommend_ollama_models(ram_gb, cores),
            "sdxl": self._recommend_sdxl_models(ram_gb, has_cuda, has_avx2, cores),
        }
    
    def _recommend_ollama_models(self, ram_gb: float, cores: int) -> dict:
        """Рекомендации Ollama-моделей на основе RAM."""
        recommended = self._pick_ollama_model(ram_gb)
        
        # Список всех доступных моделей с заметками
        all_models = [
            {
                "name": "qwen2.5-coder:0.5b",
                "size_gb": 0.5,
                "note": "⚡ Очень быстрая, ограниченные возможности кодинга",
                "min_ram": 2,
            },
            {
                "name": "qwen2.5-coder:1.5b",
                "size_gb": 1.0,
                "note": "⚡ Быстрая, базовый кодинг и чат",
                "min_ram": 4,
            },
            {
                "name": "qwen2.5-coder:3b",
                "size_gb": 2.0,
                "note": "✅ Хороший баланс скорости и качества",
                "min_ram": 6,
            },
            {
                "name": "qwen2.5-coder:7b",
                "size_gb": 4.5,
                "note": "🐢 Медленная на CPU (~1-2 мин/ответ), хорошее качество",
                "min_ram": 10,
            },
            {
                "name": "qwen2.5-coder:14b",
                "size_gb": 9.0,
                "note": "🐢 Очень медленная на CPU, требует ≥16 GB RAM",
                "min_ram": 16,
            },
        ]
        
        # Добавляем предупреждения к моделям, которые не подходят под железо
        alternatives = []
        for m in all_models:
            entry = {"name": m["name"], "note": m["note"]}
            if ram_gb < m["min_ram"]:
                entry["note"] += f" ⚠ Нужно ≥{m['min_ram']} GB RAM"
            if m["name"] == recommended:
                entry["recommended"] = True
            alternatives.append(entry)
        
        return {
            "recommended": recommended,
            "alternatives": alternatives,
        }
    
    def _recommend_sdxl_models(self, ram_gb: float, has_cuda: bool,
                                has_avx2: bool, cores: int) -> dict:
        """Рекомендации SDXL-моделей на основе железа."""
        # Базовая рекомендация — Dreamshaper XL Turbo (без лицензии HF, скачивается сразу)
        # SDXL Base требует принятия лицензии через веб-интерфейс HF — оставлен в альтернативах
        recommended = "Lykon/dreamshaper-xl-v2-turbo"
        
        alternatives = [
            {
                "name": "Lykon/dreamshaper-xl-v2-turbo",
                "display_name": "Dreamshaper XL v2 Turbo",
                "size_gb": 6.5,
                "note": "🎨 Художественный стиль, быстрее base, без лицензии HF",
                "recommended": True,
            },
            {
                "name": "stabilityai/stable-diffusion-xl-base-1.0",
                "display_name": "SDXL Base 1.0",
                "size_gb": 6.5,
                "note": "✅ Стандартная модель, универсальная. ⚠ Требует принятия лицензии HF",
            },
            {
                "name": "RunDiffusion/Juggernaut-XL-v9",
                "display_name": "Juggernaut XL v9",
                "size_gb": 6.5,
                "note": "📸 Фотореализм, высокое качество",
            },
            {
                "name": "stabilityai/stable-diffusion-xl-refiner-1.0",
                "display_name": "SDXL Refiner 1.0",
                "size_gb": 6.2,
                "note": "🔧 Улучшает детали (используется вместе с Base)",
            },
        ]
        
        # Предупреждения для слабого железа
        warnings = []
        if not has_cuda and not has_avx2:
            warnings.append(
                "Без AVX2 и CUDA генерация будет очень медленной. "
                "Рекомендуем размер 512×512."
            )
        elif not has_cuda:
            warnings.append(
                "Нет CUDA — генерация на CPU. "
                "Рекомендуем размер 512×512 для приемлемой скорости."
            )
        
        if ram_gb < req.RAM_SDXL_COMFORTABLE_GB:
            warnings.append(
                f"RAM {ram_gb:.0f} GB < комфортных {req.RAM_SDXL_COMFORTABLE_GB} GB. "
                f"Может потребоваться закрытие других приложений."
            )
        
        return {
            "recommended": recommended,
            "alternatives": alternatives,
            "warnings": warnings,
        }

    # === Предупреждения ===
    def _collect_warnings(self, detection: dict) -> list:
        warnings = []
        disk = self.detector.detect_disk(os.path.expanduser("~"))
        if disk.get("mounted") and disk.get("free_gb", 0) < req.DISK_MIN_FREE_GB:
            warnings.append(
                f"Мало места на диске: {disk['free_gb']:.1f} GB "
                f"(нужно минимум {req.DISK_MIN_FREE_GB} GB)."
            )
        gpu = detection.get("gpu", {})
        if gpu.get("vendor") == "nvidia" and not gpu.get("cuda_present"):
            warnings.append(
                "NVIDIA GPU обнаружен, но драйвер/CUDA не установлены. "
                "SDXL будет работать на CPU."
            )
        flags = detection.get("cpu", {}).get("flags", {})
        if not flags.get("avx2", False):
            warnings.append(
                "CPU не поддерживает AVX2. Генерация будет медленной, "
                "некоторые операции могут работать некорректно."
            )
        return warnings


if __name__ == "__main__":
    import json
    advisor = Advisor()
    verdict = advisor.advise()
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
