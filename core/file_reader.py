"""
Чтение файлов для вставки в промпт (v1.0).
Поддерживает только UTF-8 текст (txt, md, csv, json, код).
"""
import os
import re
from typing import Optional, Tuple

class FileReader:
    """Чтение файлов и форматирование для вставки в промпт"""
    
    FILE_TAG_START = "[Файл: {filename}]"
    FILE_TAG_END = "[/Файл]"
    
    def read_file(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Читает файл и возвращает (содержимое, имя_файла).
        
        Returns:
            Tuple (содержимое, имя_файла) или (None, None) если ошибка
        """
        if not os.path.exists(file_path):
            return None, None
        
        filename = os.path.basename(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, filename
        except UnicodeDecodeError:
            return None, None
        except Exception as e:
            print(f"[FileReader] Ошибка чтения файла {file_path}: {e}")
            return None, None
    
    def format_for_prompt(self, filename: str, content: str) -> str:
        """Форматирует содержимое файла для вставки в промпт.
        
        Args:
            filename: Имя файла
            content: Содержимое файла
            
        Returns:
            Отформатированный текст с тегами
        """
        return f"{self.FILE_TAG_START.format(filename=filename)}\n{content}\n{self.FILE_TAG_END}"
    
    def replace_file_in_text(self, text: str, filename: str, content: str) -> str:
        """Заменяет существующий блок файла в тексте или добавляет новый.
        
        Ищет блок [Файл: имя]...[/Файл] и заменяет. Если не найден — добавляет в начало.
        
        Args:
            text: Исходный текст
            filename: Имя файла
            content: Новое содержимое
            
        Returns:
            Текст с обновлённым блоком файла
        """
        # Паттерн для поиска блока файла
        pattern = rf'\[Файл: [^\]]+\]\n.*?\n\[/Файл\]'
        
        formatted = self.format_for_prompt(filename, content)
        
        # Пробуем заменить существующий блок
        new_text = re.sub(pattern, formatted, text, count=1, flags=re.DOTALL)
        
        # Если замена не сработала — добавляем в начало
        if new_text == text:
            new_text = f"{formatted}\n\n{text}"
        
        return new_text
    
    def get_file_size_tokens(self, content: str) -> int:
        """Оценивает размер файла в токенах (символы / 3)."""
        return len(content) // 3
