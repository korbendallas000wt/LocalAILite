class ChatManager:
    def __init__(self):
        self.messages = []

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})

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

    def clear(self):
        self.messages = []

    def remove_last_message(self):
        """Удаляет последнее сообщение (или пару) и возвращает текст пользователя."""
        if not self.messages:
            return None
        
        last_msg = self.messages.pop()
        if last_msg["role"] == "user":
            return last_msg["content"]
        
        # Если это ассистент, удаляем и его, и предшествующий пользовательский
        if last_msg["role"] == "assistant" and len(self.messages) >= 1 and self.messages[-1]["role"] == "user":
            user_msg = self.messages.pop()
            return user_msg["content"]
            
        return None
