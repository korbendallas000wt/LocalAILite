from PyQt6.QtCore import QSettings
import json


class Config:
    def __init__(self):
        self.settings = QSettings("LocalAILite", "LocalAILite")
        self._migrate_from_old()

    def _migrate_from_old(self):
        """Миграция настроек из старой версии OllamaChat"""
        old_settings = QSettings("OllamaChat", "OllamaChat")
        if not old_settings.contains("migrated"):
            for key in old_settings.allKeys():
                if not self.settings.contains(key):
                    self.settings.setValue(key, old_settings.value(key))
            old_settings.setValue("migrated", "true")

    def get(self, key, default=None):
        return self.settings.value(key, default)

    def set(self, key, value):
        self.settings.setValue(key, value)

    def get_json(self, key, default=None):
        """Получить значение из конфига и десериализовать из JSON"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    def set_json(self, key, value):
        """Сериализовать значение в JSON и сохранить в конфиг"""
        self.set(key, json.dumps(value, ensure_ascii=False))

    # === Ollama ===
    def get_ollama_url(self):
        return self.get("url", "http://localhost:11434")

    # === SDXL ===
    def get_sdxl_venv_path(self):
        return self.get("sdxl/venv_path", "")

    def set_sdxl_venv_path(self, path):
        self.set("sdxl/venv_path", path)

    def get_sdxl_models_path(self):
        return self.get("sdxl/models_path", "")

    def set_sdxl_models_path(self, path):
        self.set("sdxl/models_path", path)

    def get_sdxl_scheduler(self):
        return self.get("sdxl/scheduler", "EulerDiscreteScheduler")

    def set_sdxl_scheduler(self, scheduler):
        self.set("sdxl/scheduler", scheduler)

    def get_sdxl_default_steps(self):
        return int(self.get("sdxl/steps", 30))

    def get_sdxl_default_cfg(self):
        return float(self.get("sdxl/cfg", 7.5))

    def get_sdxl_output_dir(self):
        return self.get("sdxl/output_dir", "/home/lin/Pictures/LocalAILite")

    def get_sdxl_device(self):
        return self.get("sdxl/device", "cuda")

    def set_sdxl_device(self, device):
        self.set("sdxl/device", device)

    def set_sdxl_output_dir(self, path):
        self.set("sdxl/output_dir", path)

    def get_data_dir(self):
        """Возвращает путь к внутренней папке data/ проекта"""
        import os
        return os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data"
        ))

    def get_previews_dir(self):
        """Папка для промежуточных превью (технические файлы)"""
        import os
        return os.path.join(self.get_data_dir(), "previews")

    def get_history_dir(self):
        """Папка для истории генерации (PNG на каждом шаге)"""
        import os
        return os.path.join(self.get_data_dir(), "history")

    def get_logs_dir(self):
        """Папка для логов (технические файлы)"""
        import os
        return os.path.join(self.get_data_dir(), "logs")

    # === Ollama (локальный бинарник) ===
    def get_ollama_binary_path(self):
        """Путь к локальному бинарнику Ollama"""
        import os
        return os.path.join(self.get_data_dir(), "..", "bin", "ollama", "bin", "ollama")
    
    def get_ollama_data_dir(self):
        """Папка для данных Ollama (ключи, история)"""
        import os
        return os.path.join(self.get_data_dir(), "ollama")
    
    def get_ollama_lib_dir(self):
        """Папка с библиотеками Ollama (CUDA, ROCm)"""
        import os
        return os.path.join(self.get_data_dir(), "..", "bin", "ollama", "lib", "ollama")

    # === Image Prep ===
    def get_init_images_dir(self):
        """Папка для подготовленных изображений"""
        import os
        return os.path.join(self.get_data_dir(), "init_images")
