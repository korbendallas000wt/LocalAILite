"""
Нумерованные версии чата (модель без веток и свопа).

Каждый чат = папка в data/ollama/chats/{имя}/
Внутри:
    chat_1.json, chat_2.json, ... — нумерованные версии
    meta.json — служебные данные (номер последнего чата)

Правила:
- Папка создаётся при первом сообщении, имя = первые 40 символов этого сообщения.
- Продолжение (дописывание) = перезапись текущего номера.
- Правка через «Изменить» = создание нового номера.
- Переключение между вариантами = загрузка нужного номера, без свопа.
"""

import json
import os
import re
import shutil
from datetime import datetime
from typing import List, Dict, Optional


class ChatVersions:
    def __init__(self, chats_dir: str):
        self.chats_dir = chats_dir
        os.makedirs(chats_dir, exist_ok=True)

    # ---------- Папка ----------

    def folder_name_from_message(self, first_message: str) -> str:
        """Имя папки: первые 40 символов первого сообщения, безопасно для ФС."""
        text = first_message.strip().replace('\n', ' ')[:40].strip()
        text = re.sub(r'[\\/:*?"<>|]', '_', text)
        text = re.sub(r'\s+', ' ', text)
        return text or 'chat'

    def create_folder(self, first_message: str) -> str:
        """Создать папку чата по первому сообщению. Возвращает путь."""
        name = self.folder_name_from_message(first_message)
        folder = os.path.join(self.chats_dir, name)
        counter = 1
        base = folder
        while os.path.exists(folder):
            folder = f"{base}_{counter}"
            counter += 1
        os.makedirs(folder, exist_ok=True)
        return folder

    # ---------- Номера ----------

    def list_numbers(self, folder: str) -> List[int]:
        """Все номера чатов в папке, по возрастанию."""
        numbers = []
        if not os.path.isdir(folder):
            return numbers
        for fname in os.listdir(folder):
            m = re.match(r'^chat_(\d+)\.json$', fname)
            if m:
                numbers.append(int(m.group(1)))
        return sorted(numbers)

    def next_number(self, folder: str) -> int:
        numbers = self.list_numbers(folder)
        return (numbers[-1] + 1) if numbers else 1

    def chat_path(self, folder: str, number: int) -> str:
        return os.path.join(folder, f"chat_{number}.json")

    # ---------- Чтение/запись ----------

    def save(self, folder: str, number: int, messages: List[Dict], settings: Dict) -> str:
        """Сохранить чат под номером. Возвращает путь к файлу."""
        data = {
            "number": number,
            "created_at": datetime.now().isoformat(),
            "messages": messages,
            "settings": settings,
        }
        path = self.chat_path(folder, number)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def load(self, folder: str, number: int) -> Optional[Dict]:
        path = self.chat_path(folder, number)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    # ---------- Варианты в сообщении (быстрая навигация) ----------

    def get_message_variants(self, folder: str, number: int, user_msg_index: int):
        """Номера чатов-вариантов для пользовательского сообщения. None, если сообщения нет."""
        data = self.load(folder, number)
        if data is None:
            return None
        for msg in data.get("messages", []):
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                return msg.get("variants")
        return None

    def set_message_variants(self, folder: str, number: int, user_msg_index: int, variants) -> bool:
        """Записывает список вариантов в пользовательское сообщение и сохраняет файл."""
        path = self.chat_path(folder, number)
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            changed = False
            for msg in data.get("messages", []):
                if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                    msg["variants"] = list(variants)
                    changed = True
                    break
            if changed:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            return changed
        except Exception:
            return False

    def sync_variants_on_branch(self, folder: str, fork_user_msg_index: int, old_variants, new_chat_number: int):
        """При ветвлении добавляет новый номер в варианты всем существующим альтернативам."""
        new_variants = list(old_variants) + [new_chat_number]
        for num in old_variants:
            self.set_message_variants(folder, num, fork_user_msg_index, new_variants)
        return new_variants

    # ---------- Последний чат ----------

    def _meta_path(self, folder: str) -> str:
        return os.path.join(folder, 'meta.json')

    def get_last_number(self, folder: str) -> Optional[int]:
        meta_path = self._meta_path(folder)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                last = meta.get('last_chat')
                if last is not None and os.path.exists(self.chat_path(folder, last)):
                    return last
            except Exception:
                pass
        numbers = self.list_numbers(folder)
        return numbers[-1] if numbers else None

    def set_last_number(self, folder: str, number: int):
        with open(self._meta_path(folder), 'w', encoding='utf-8') as f:
            json.dump({"last_chat": number}, f, ensure_ascii=False, indent=2)

    def load_last(self, folder: str) -> Optional[Dict]:
        last = self.get_last_number(folder)
        if last is None:
            return None
        return self.load(folder, last)

    # ---------- Переименование / удаление ----------

    def rename_folder(self, folder: str, new_name: str) -> str:
        safe = re.sub(r'[\\/:*?"<>|]', '_', new_name.strip())
        safe = re.sub(r'\s+', ' ', safe).strip() or 'chat'
        new_folder = os.path.join(self.chats_dir, safe)
        if new_folder == folder:
            return folder
        counter = 1
        base = new_folder
        while os.path.exists(new_folder):
            new_folder = f"{base}_{counter}"
            counter += 1
        os.rename(folder, new_folder)
        return new_folder

    def delete_folder(self, folder: str):
        if os.path.isdir(folder):
            shutil.rmtree(folder)

    def delete_chat(self, folder: str, number: int) -> bool:
        """Удаляет один нумерованный чат. Безопасно: остальные самодостаточны."""
        path = self.chat_path(folder, number)
        if not os.path.exists(path):
            return False
        os.remove(path)
        # Если удалили тот, что помечен последним, — обновляем meta.json
        meta_path = self._meta_path(folder)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                if meta.get('last_chat') == number:
                    remaining = self.list_numbers(folder)
                    if remaining:
                        self.set_last_number(folder, remaining[-1])
                    else:
                        os.remove(meta_path)
            except Exception:
                pass
        return True
