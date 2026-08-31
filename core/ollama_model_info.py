"""
Информация о моделях Ollama (v1.0).
Получает и кэширует метаданные моделей из /api/show.
"""
import requests
import time
from typing import Optional, Dict

class OllamaModelInfo:
    """Кэш информации о моделях Ollama"""
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Dict] = {}
        self._ttl = ttl_seconds
    
    def _fetch_model_info(self, url: str, model_name: str) -> Optional[Dict]:
        """Получает информацию о модели из /api/show"""
        try:
            response = requests.post(
                f"{url}/api/show",
                json={"name": model_name},
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[OllamaModelInfo] Ошибка получения информации о модели {model_name}: {e}")
            return None
    
    def _get_context_length_from_info(self, info: Dict) -> Optional[int]:
        """Извлекает context_length из model_info.
        Ищет ключ, заканчивающийся на .context_length
        """
        if not info or "model_info" not in info:
            return None
        
        for key, value in info["model_info"].items():
            if key.endswith(".context_length"):
                return value
        
        return None
    
    def get_context_length(self, url: str, model_name: str) -> Optional[int]:
        """Возвращает context_length для модели.
        Использует кэш, если данные свежие (TTL 5 минут).
        """
        cache_key = f"{url}:{model_name}"
        
        # Проверяем кэш
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            age = time.time() - cached_data["timestamp"]
            if age < self._ttl:
                return cached_data["context_length"]
        
        # Получаем новые данные
        info = self._fetch_model_info(url, model_name)
        if info is None:
            return None
        
        context_length = self._get_context_length_from_info(info)
        
        # Кэшируем
        self._cache[cache_key] = {
            "context_length": context_length,
            "timestamp": time.time(),
            "info": info
        }
        
        return context_length
    
    def clear_cache(self):
        """Очищает весь кэш"""
        self._cache.clear()
    
    def clear_model_cache(self, url: str, model_name: str):
        """Очищает кэш для конкретной модели"""
        cache_key = f"{url}:{model_name}"
        if cache_key in self._cache:
            del self._cache[cache_key]
