"""
Подсчёт использования контекста (v1.0).
Приближённый подсчёт токенов для UI-индикатора.

Алгоритм v1 (упрощённый):
    tokens ≈ количество_символов / 3

Это даёт ±20-30% погрешность, что достаточно для индикатора.
В будущем можно заменить на точный токенизатор без изменения интерфейса.
"""
from typing import List, Dict, Optional

class ContextTracker:
    """Подсчёт использования контекста диалога"""
    
    def estimate_tokens(self, text: str) -> int:
        """Оценивает количество токенов в тексте.
        
        Args:
            text: Входной текст
            
        Returns:
            Приблизительное количество токенов
        """
        if not text:
            return 0
        
        # Упрощённый алгоритм: символы / 3
        # Средняя длина токена для смешанных языков ~3 символа
        return len(text) // 3
    
    def calculate_usage(self, messages: List[Dict], system_prompt: Optional[str] = None) -> int:
        """Подсчитывает общее использование контекста диалога.
        
        Args:
            messages: Список сообщений в формате [{"role": str, "content": str}]
            system_prompt: Системный промпт (опционально)
            
        Returns:
            Общее количество токенов
        """
        total_tokens = 0
        
        # Системный промпт
        if system_prompt:
            total_tokens += self.estimate_tokens(system_prompt)
        
        # Все сообщения диалога (текст + вложения)
        for msg in messages:
            content = msg.get("content", "")
            total_tokens += self.estimate_tokens(content)
            
            # Вложения в сообщении
            attachments = msg.get("attachments", [])
            for att in attachments:
                att_content = att.get("content", "")
                total_tokens += self.estimate_tokens(att_content)
        
        return total_tokens
