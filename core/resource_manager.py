from PyQt6.QtCore import QObject

class ResourceManager(QObject):
    def __init__(self):
        super().__init__()
        self.active_module = None
        self.modules = {}  # {"ollama": ollama_tab, "diffusers": diffusers_tab}
    
    def register_module(self, name, module):
        """Регистрирует модуль для управления ресурсами"""
        self.modules[name] = module
    
    def on_tab_changed(self, index):
        """Вызывается при переключении таба"""
        # Определяем имя модуля по индексу (предполагаем порядок добавления)
        module_names = list(self.modules.keys())
        if 0 <= index < len(module_names):
            module_name = module_names[index]
            
            if self.active_module and self.active_module != module_name:
                # Выгружаем предыдущий модуль
                prev_module = self.modules.get(self.active_module)
                if prev_module and hasattr(prev_module, 'unload'):
                    print(f"Выгрузка модуля: {self.active_module}")
                    prev_module.unload()
            
            self.active_module = module_name
            print(f"Активный модуль: {self.active_module}")
