"""
Монитор ресурсов и применение ограничений.
Используется перед запуском генерации для проверки доступных ресурсов
и применения лимитов CPU/RAM к процессам.
"""
import os
import psutil


class ResourceMonitor:
    """Мониторинг и управление ресурсами системы"""
    
    def __init__(self, config):
        self.config = config
    
    def get_limits(self) -> dict:
        """Возвращает текущие лимиты из конфига"""
        return {
            "max_ram_percent": int(self.config.get("resources/max_ram_percent", 80)),
            "cpu_cores": int(self.config.get("resources/cpu_cores", 3)),
            "cpu_priority": int(self.config.get("resources/cpu_priority", 0))
        }
    
    def get_system_info(self) -> dict:
        """Возвращает информацию о системе"""
        mem = psutil.virtual_memory()
        return {
            "ram_total_gb": mem.total / (1024**3),
            "ram_available_gb": mem.available / (1024**3),
            "ram_used_gb": mem.used / (1024**3),
            "ram_percent": mem.percent,
            "cpu_count": os.cpu_count() or 4,
            "cpu_percent": psutil.cpu_percent(interval=0.1)
        }
    
    def check_ram_available(self, required_gb: float) -> dict:
        """
        Проверяет, достаточно ли RAM для задачи.
        Args:
            required_gb: требуемая память в GB
        Returns:
            dict: {"ok": bool, "available_gb": float, "required_gb": float, "message": str}
        """
        limits = self.get_limits()
        # Реальная память системы (учитываем ВСЕ процессы, а не только GUI)
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        # Фактически занято системой (все процессы, без отдаваемого кэша)
        used_gb = total_gb - available_gb
        # Пользовательский потолок: сколько всего RAM может быть занято
        max_used_gb = total_gb * limits["max_ram_percent"] / 100
        # Запас до пользовательского потолка
        headroom_to_limit_gb = max_used_gb - used_gb
        # Реально свободно для задачи: минимум из (свободно в системе, запас до лимита),
        # с запасом 10% на непредвиденные расходы
        available_for_task = max(0.0, min(available_gb, headroom_to_limit_gb) * 0.9)
        
        if required_gb > available_for_task:
            return {
                "ok": False,
                "available_gb": available_for_task,
                "required_gb": required_gb,
                "message": (
                    f"Недостаточно RAM. "
                    f"Требуется: {required_gb:.1f} GB, "
                    f"доступно: {available_for_task:.1f} GB "
                    f"(свободно в системе: {available_gb:.1f} GB, лимит {limits['max_ram_percent']}% от {total_gb:.1f} GB)"
                )
            }
        
        return {
            "ok": True,
            "available_gb": available_for_task,
            "required_gb": required_gb,
            "message": f"Достаточно RAM: {available_for_task:.1f} GB"
        }
    
    def estimate_diffusers_ram(self, width: int, height: int, model: str) -> float:
        """
        Оценивает требуемую RAM для Diffusers.
        SDXL: ~9 GB для 512x512, ~11 GB для 1024x1024 (float32 на CPU)
        SD 1.5: ~4.5 GB для 512x512
        """
        # Базовая оценка по размеру изображения
        pixels = width * height
        base_gb = 4.5  # базовое потребление (SD 1.5)
        # SDXL требует больше (модель ~7 GB в float32 + активация + оверхед torch)
        if "xl" in model.lower() or pixels > 512*512:
            base_gb = 9.0
        # Масштабирование по размеру
        if pixels >= 1024*1024:
            base_gb *= 1.2
        elif pixels < 512*512:
            base_gb *= 0.85
        return base_gb
    
    def estimate_ollama_ram(self, model: str) -> float:
        """
        Оценивает требуемую RAM для Ollama модели.
        Примерные размеры:
        - 3B параметров: ~2 GB
        - 7B параметров: ~4-5 GB
        - 13B параметров: ~8 GB
        """
        model_lower = model.lower()
        
        if "3b" in model_lower or "1.5b" in model_lower:
            return 2.0
        elif "7b" in model_lower or "8b" in model_lower:
            return 5.0
        elif "13b" in model_lower:
            return 8.0
        elif "70b" in model_lower:
            return 40.0
        else:
            # По умолчанию — средняя модель
            return 4.0
    
    @staticmethod
    def apply_cpu_affinity(pid: int, cores: int):
        """Привязывает процесс к указанным ядрам CPU"""
        try:
            process = psutil.Process(pid)
            available_cores = list(range(os.cpu_count() or 4))
            # Берём первые N ядер
            affinity = available_cores[:cores]
            process.cpu_affinity(affinity)
            return True
        except Exception as e:
            print(f"[ResourceMonitor] Не удалось установить affinity: {e}")
            return False
    
    @staticmethod
    def apply_priority(pid: int, priority: int):
        """Устанавливает приоритет процесса (nice)"""
        try:
            process = psutil.Process(pid)
            process.nice(priority)
            return True
        except Exception as e:
            print(f"[ResourceMonitor] Не удалось установить priority: {e}")
            return False
    
    @staticmethod
    def get_env_for_cpu_limits(cores: int) -> dict:
        """Возвращает переменные окружения для ограничения CPU"""
        return {
            "OMP_NUM_THREADS": str(cores),
            "OPENBLAS_NUM_THREADS": str(cores),
            "MKL_NUM_THREADS": str(cores),
            "VECLIB_MAXIMUM_THREADS": str(cores),
            "NUMEXPR_NUM_THREADS": str(cores)
        }

    @staticmethod
    def read_pid_file(pid_path: str) -> int:
        """Читает PID из файла. Возвращает 0, если файла нет или он битый."""
        try:
            if not os.path.exists(pid_path):
                return 0
            with open(pid_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            return int(content) if content else 0
        except Exception:
            return 0

    @staticmethod
    def is_process_alive(pid: int) -> bool:
        """Проверяет, жив ли процесс с указанным PID"""
        if pid <= 0:
            return False
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False

    @staticmethod
    def kill_process_by_pid(pid: int, force: bool = False) -> bool:
        """Останавливает процесс по PID. force=True — сразу SIGKILL."""
        if pid <= 0:
            return False
        try:
            process = psutil.Process(pid)
            if force:
                process.kill()
            else:
                process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                pass
            return True
        except psutil.NoSuchProcess:
            return True
        except Exception as e:
            print(f"[ResourceMonitor] Не удалось завершить процесс {pid}: {e}")
            return False
