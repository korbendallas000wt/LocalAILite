"""
Экспорт чатов в JSON и TXT форматы.

JSON — для машины (RAG, поиск, точное воспроизведение)
TXT — для человека (чтение, архив)
"""
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional


class ChatExporter:
    """Экспорт чата в JSON и/или TXT"""
    
    def __init__(self, chats_dir: str):
        self.chats_dir = chats_dir
        os.makedirs(chats_dir, exist_ok=True)
    
    def export_chat(
        self,
        title: str,
        messages: List[Dict],
        settings: Dict,
        save_json: bool = True,
        save_txt: bool = True,
        target_base_path: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Экспортирует чат в JSON и/или TXT.
        Если target_base_path указан, сохраняет туда (перезапись).
        Иначе генерирует новое уникальное имя файла.
        """
        if target_base_path:
            base_filename = target_base_path
            json_path = base_filename + ".json"
            if os.path.exists(json_path):
                try:
                    created_at = datetime.fromtimestamp(os.path.getmtime(json_path))
                except Exception:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()
            chat_id = self._get_chat_id(json_path)
        else:
            created_at = datetime.now()
            chat_id = created_at.strftime("chat_%Y-%m-%d_%H-%M-%S")
            base_filename = self._generate_filename(created_at, title)
            sample_path = os.path.join(self.chats_dir, base_filename + ".json")
            unique_path = self._ensure_unique(sample_path)
            base_filename = os.path.splitext(unique_path)[0]
        
        result = {}
        if save_json:
            json_path = base_filename + ".json"
            self._save_json(json_path, chat_id, title, created_at, messages, settings)
            result["json"] = json_path
        
        if save_txt:
            txt_path = base_filename + ".txt"
            self._save_txt(txt_path, title, created_at, messages, settings)
            result["txt"] = txt_path
        
        return result

    def _get_chat_id(self, json_path: str) -> str:
        """Извлекает ID из существующего JSON или генерирует новый"""
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("id", "unknown")
            except Exception:
                pass
        return datetime.now().strftime("chat_%Y-%m-%d_%H-%M-%S")
    
    def _generate_filename(self, created_at: datetime, title: str) -> str:
        """
        Генерирует имя файла: дата + заголовок (санитизированный).
        
        Примеры:
        - "2026-08-20_Обсуждение_RAG"
        - "2026-08-20_14-32-15" (если заголовок пустой)
        """
        date_str = created_at.strftime("%Y-%m-%d")
        
        if not title or not title.strip():
            # Пустой заголовок — используем timestamp
            time_str = created_at.strftime("%H-%M-%S")
            return f"{date_str}_{time_str}"
        
        # Санитизируем заголовок
        sanitized = self._sanitize_filename(title)
        # Ограничиваем длину
        max_title_len = 40
        if len(sanitized) > max_title_len:
            sanitized = sanitized[:max_title_len]
        
        return f"{date_str}_{sanitized}"
    
    def _sanitize_filename(self, text: str) -> str:
        """
        Санитизирует строку для использования в имени файла.
        
        - Заменяет пробелы на _
        - Убирает спецсимволы
        - Заменяет переносы строк на пробелы
        """
        # Заменяем переносы строк на пробелы
        text = text.replace('\n', ' ').replace('\r', ' ')
        # Заменяем пробелы на _
        text = re.sub(r'\s+', '_', text)
        # Убираем спецсимволы (оставляем буквы, цифры, _, -)
        text = re.sub(r'[^\w\-_]', '', text, flags=re.UNICODE)
        # Убираем повторяющиеся _
        text = re.sub(r'_+', '_', text)
        # Убираем _ в начале и конце
        text = text.strip('_')
        
        return text if text else "chat"
    
    def _ensure_unique(self, filepath: str) -> str:
        """
        Если файл уже существует, добавляет суффикс _1, _2, etc.
        """
        if not os.path.exists(filepath):
            return filepath
        
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1
        
        return f"{base}_{counter}{ext}"
    
    def _save_json(
        self,
        filepath: str,
        chat_id: str,
        title: str,
        created_at: datetime,
        messages: List[Dict],
        settings: Dict
    ):
        """Сохраняет чат в JSON"""
        data = {
            "id": chat_id,
            "title": title,
            "created_at": created_at.isoformat(),
            "settings": settings,
            "messages": messages
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _save_txt(
        self,
        filepath: str,
        title: str,
        created_at: datetime,
        messages: List[Dict],
        settings: Dict
    ):
        """Сохраняет чат в TXT (markdown)"""
        lines = []
        
        # Заголовок
        lines.append(f"# {title}")
        lines.append("")
        
        # Метаданные
        lines.append(f"Дата: {created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if "model" in settings:
            lines.append(f"Модель: {settings['model']}")
        if "temperature" in settings:
            lines.append(f"Temperature: {settings['temperature']}")
        lines.append("")
        
        # Сообщения
        for msg in messages:
            role = "Вы" if msg["role"] == "user" else "Модель"
            lines.append(f"== {role} ==")
            lines.append(msg["content"])
            
            # Метеданные ответа (если есть stats)
            if msg["role"] == "assistant" and "stats" in msg:
                stats = msg["stats"]
                stats_parts = []
                if "completion_tokens" in stats:
                    stats_parts.append(f"{stats['completion_tokens']} токенов")
                if "duration_sec" in stats:
                    stats_parts.append(f"{stats['duration_sec']:.1f} сек")
                if stats_parts:
                    lines.append(f"\n[{', '.join(stats_parts)}]")
            
            lines.append("")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
