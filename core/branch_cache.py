"""
Кэш веток текущего активного чата.

Хранит "отложенные" варианты сообщений в памяти.
- Когда пользователь жмёт "Изменить" и отправляет новую версию,
  старая версия + хвост диалога уходит сюда.
- При сохранении чата — переносится в папку как branch_*.json.
- При закрытии чата без сохранения — очищается вместе с чатом.

Кэш всегда один: чатов одновременно больше одного не бывает.
"""
from datetime import datetime


class BranchCache:
    def __init__(self):
        self._branches = []
        self._next_id = 0
    
    def add(self, parent_user_msg_index: int, messages: list, settings: dict = None) -> int:
        """Добавляет ветку в кэш. Возвращает id (порядковый номер) ветки."""
        branch = {
            "id": self._next_id,
            "parent_user_msg_index": parent_user_msg_index,
            "messages": [m.copy() for m in messages],
            "settings": (settings or {}).copy(),
            "created_at": datetime.now().isoformat()
        }
        self._branches.append(branch)
        self._next_id += 1
        return branch["id"]
    
    def clear(self):
        """Очищает весь кэш (при смене/закрытии чата)."""
        self._branches = []
    
    def get_by_id(self, branch_id: int):
        """Возвращает ветку по id или None."""
        for b in self._branches:
            if b["id"] == branch_id:
                return b
        return None

    def remove_by_id(self, branch_id: int):
        """Удаляет ветку по id (когда она становится main)."""
        self._branches = [b for b in self._branches if b["id"] != branch_id]

    def count_for_index(self, parent_user_msg_index: int) -> int:
        """Сколько веток привязано к данному user_msg_index."""
        return sum(1 for b in self._branches 
                   if b["parent_user_msg_index"] == parent_user_msg_index)
    
    def get_for_index(self, parent_user_msg_index: int) -> list:
        """Все ветки для данного user_msg_index."""
        return [b for b in self._branches 
                if b["parent_user_msg_index"] == parent_user_msg_index]
    
    def get_all(self) -> list:
        """Все ветки (для переноса в папку при сохранении)."""
        return self._branches.copy()
    
    def is_empty(self) -> bool:
        return len(self._branches) == 0
