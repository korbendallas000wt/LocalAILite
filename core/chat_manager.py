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
        """Возвращает всю историю в формате markdown"""
        md_parts = []
        for msg in self.messages:
            if msg["role"] == "user":
                md_parts.append(f"## Вы\n\n{msg['content']}\n")
            elif msg["role"] == "assistant":
                md_parts.append(f"## Модель\n\n{msg['content']}\n")
        return "\n".join(md_parts)

    def clear(self):
        self.messages = []

    def remove_last_pair(self):
        """Удаляет последнюю пару сообщений (user + assistant) и возвращает текст пользователя."""
        if len(self.messages) >= 2:
            if self.messages[-1]["role"] == "assistant" and self.messages[-2]["role"] == "user":
                last_user_msg = self.messages.pop(-2)
                self.messages.pop()  # удаляем assistant
                return last_user_msg["content"]
        return None
