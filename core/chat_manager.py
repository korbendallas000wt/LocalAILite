

class ChatManager:
    def __init__(self):
        self.messages = []
        self._user_msg_counter = 0  # Счётчик для уникальных индексов сообщений пользователя

    def add_user_message(self, content, user_msg_index=None, attachments=None):
        if user_msg_index is None:
            user_msg_index = self._user_msg_counter
            self._user_msg_counter += 1
        elif user_msg_index >= self._user_msg_counter:
            # Переиспользование индекса при ветвлении: сдвигаем счётчик
            self._user_msg_counter = user_msg_index + 1
        msg = {
            "role": "user", 
            "content": content, 
            "user_msg_index": user_msg_index,
            "variants": []
        }
        if attachments:
            msg["attachments"] = attachments
        self.messages.append(msg)

    def add_assistant_message(self, content, stats=None):
        msg = {"role": "assistant", "content": content}
        if stats:
            msg["stats"] = stats
        self.messages.append(msg)

    def get_messages(self):
        return self.messages.copy()

    def get_full_history_markdown(self):
        md_parts = []
        for msg in self.messages:
            if msg["role"] == "user":
                md_parts.append(f"## Вы\n\n{msg['content']}\n")
            elif msg["role"] == "assistant":
                md_parts.append(f"## Модель\n\n{msg['content']}\n")
        return "\n".join(md_parts)

    def recalc_counter(self):
        """Пересчитывает счётчик на основе максимального user_msg_index."""
        max_index = -1
        for msg in self.messages:
            if msg.get("role") == "user":
                idx = msg.get("user_msg_index", -1)
                if idx > max_index:
                    max_index = idx
        self._user_msg_counter = max_index + 1

    def set_next_index(self, n: int):
        """Задаёт индекс для следующего нового сообщения (режим правки)."""
        self._user_msg_counter = n

    def get_variants_for(self, user_msg_index: int):
        """Возвращает список вариантов для пользовательского сообщения с заданным индексом."""
        for msg in self.messages:
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                return msg.get("variants", [])
        return None

    def set_variants_for(self, user_msg_index: int, variants):
        """Устанавливает список вариантов для пользовательского сообщения."""
        for msg in self.messages:
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                msg["variants"] = list(variants)
                return True
        return False

    def clear(self):
        self.messages = []

    def remove_last_message(self):
        """Удаляет последнее сообщение (или пару) и возвращает текст пользователя."""
        if not self.messages:
            return None
        
        last_msg = self.messages.pop()
        if last_msg["role"] == "user":
            return last_msg["content"]
        
        if last_msg["role"] == "assistant" and len(self.messages) >= 1 and self.messages[-1]["role"] == "user":
            user_msg = self.messages.pop()
            return user_msg["content"]
            
        return None

    def load_messages(self, messages: list):
        """Загружает историю сообщений из JSON (заменяет текущую)"""
        self.messages = messages.copy()

        # Восстанавливаем счётчик user_msg_index для совместимости со старыми чатами
        max_index = -1
        for msg in self.messages:
            if msg.get("role") == "user":
                idx = msg.get("user_msg_index", -1)
                if idx > max_index:
                    max_index = idx
        
        # Если индексов не было (старый формат), назначаем их заново
        if max_index == -1:
            current_idx = 0
            for msg in self.messages:
                if msg.get("role") == "user":
                    msg["user_msg_index"] = current_idx
                    current_idx += 1
            max_index = current_idx - 1
            
        self._user_msg_counter = max_index + 1
