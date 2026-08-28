"""
Чтение файлов для вставки в промпт (v2.0).
Вложения хранятся как структура, а не как теги в тексте.
"""
import os
from typing import Optional, Dict

class FileReader:
    """Чтение файлов и создание структур вложений"""
    
    def read_file(self, file_path: str) -> Optional[Dict]:
        """Читает файл и возвращает структуру вложения.
        
        Returns:
            Dict с полями:
                - filename: имя файла
                - content: содержимое (строка)
                - source_path: полный путь к исходному файлу
                - size_bytes: размер в байтах
            или None если ошибка
        """
        if not os.path.exists(file_path):
            return None
        
        filename = os.path.basename(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "filename": filename,
                "content": content,
                "source_path": file_path,
                "size_bytes": os.path.getsize(file_path)
            }
        except UnicodeDecodeError:
            print(f"[FileReader] Файл не UTF-8: {file_path}")
            return None
        except Exception as e:
            print(f"[FileReader] Ошибка чтения файла {file_path}: {e}")
            return None
    
    def get_file_size_tokens(self, content: str) -> int:
        """Оценивает размер файла в токенах (символы / 3)."""
        return len(content) // 3
    
    def format_for_prompt(self, attachment: Dict) -> str:
        """Форматирует вложение для отправки в модель.
        
        Args:
            attachment: структура вложения из read_file()
            
        Returns:
            Текст с тегами для вставки в промпт
        """
        filename = attachment["filename"]
        content = attachment["content"]
        return f"[Файл: {filename}]\n{content}\n[/Файл]"
