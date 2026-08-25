"""
Экспорт чатов в JSON и TXT форматы (архитектура папок).

JSON — для машины (RAG, поиск, точное воспроизведение)
TXT — для человека (чтение, архив)

Структура:
data/ollama/chats/{chat_folder_name}/
 ├── main.json    # Сохранённый чат
 └── main.txt     # Человекочитаемая версия
"""
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

class ChatExporter:
    """Экспорт чата в JSON и/или TXT с поддержкой папок и ветвления"""
    
    def __init__(self, chats_dir: str):
        self.chats_dir = chats_dir
        os.makedirs(chats_dir, exist_ok=True)
    
    def export_chat(
        self,
        chat_folder_name: str,
        title: str,
        messages: List[Dict],
        settings: Dict,
        save_json: bool = True,
        save_txt: bool = True
    ) -> Dict[str, str]:
        safe_folder_name = self._sanitize_filename(chat_folder_name) or "unnamed_chat"
        folder_path = os.path.join(self.chats_dir, safe_folder_name)
        os.makedirs(folder_path, exist_ok=True)

        created_at = datetime.now()
        chat_id = created_at.strftime("chat_%Y-%m-%d_%H-%M-%S")

        result = {"folder": folder_path}

        if save_json:
            # Сохраняем как main.json
            main_path = os.path.join(folder_path, "main.json")
            main_data = {
                "id": chat_id,
                "title": title,
                "created_at": created_at.isoformat(),
                "settings": settings,
                "messages": messages
            }
            with open(main_path, 'w', encoding='utf-8') as f:
                json.dump(main_data, f, ensure_ascii=False, indent=2)
            result["json"] = main_path
            result["main_json"] = main_path

        if save_txt:
            txt_path = os.path.join(folder_path, "main.txt")
            self._save_txt(txt_path, title, created_at, messages, settings)
            result["txt"] = txt_path

        return result

    def _sanitize_filename(self, text: str) -> str:
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r'\s+', '_', text)
        text = re.sub(r'[^\w\-_]', '', text, flags=re.UNICODE)
        text = re.sub(r'_+', '_', text)
        text = text.strip('_')
        return text if text else "chat"
    
    def _save_txt(
        self,
        filepath: str,
        title: str,
        created_at: datetime,
        messages: List[Dict],
        settings: Dict
    ):
        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"Дата: {created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if "model" in settings:
            lines.append(f"Модель: {settings['model']}")
        if "temperature" in settings:
            lines.append(f"Temperature: {settings['temperature']}")
        lines.append("")
        
        for msg in messages:
            role = "Вы" if msg["role"] == "user" else "Модель"
            lines.append(f"== {role} ==")
            lines.append(msg["content"])
            
            if msg["role"] == "assistant" and "stats" in msg:
                stats = msg["stats"]
                stats_parts = []
                if "completion_tokens" in stats:
                    stats_parts.append(f"{stats['completion_tokens']} токенов")
                if "duration_sec" in stats:
                    stats_parts.append(f"{stats['duration_sec']:.1f} сек")
                if stats_parts:
                    lines.append(f"[{{', '.join(stats_parts)}}]")
            lines.append("")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
