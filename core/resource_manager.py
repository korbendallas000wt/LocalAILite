"""
Менеджер ресурсов приложения.
Отвечает за:
1. Переключение активного модуля (выгрузка неактивных)
2. Управление ресурсом (GPU/RAM) — только один модуль может генерировать
"""
from PyQt6.QtCore import QObject, pyqtSignal


class ResourceManager(QObject):
    """Управление ресурсами и модулями приложения"""
    
    # Сигналы для UI
    resource_acquired = pyqtSignal(str)    # "diffusers" занял ресурс
    resource_released = pyqtSignal()       # ресурс освобождён
    
    def __init__(self):
        super().__init__()
        self.active_module = None
        self.modules = {}  # {"ollama": ollama_tab, "diffusers": diffusers_tab}
        self._resource_owner = None  # Кто сейчас владеет ресурсом (генерирует)
    
    # === Управление модулями ===
    
    def register_module(self, name, module):
        """Регистрирует модуль для управления ресурсами"""
        self.modules[name] = module
    
    def on_tab_changed(self, index):
        """Вызывается при переключении таба — выгружает неактивные модули"""
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
    
    # === Управление ресурсом (генерация) ===
    
    def acquire_resource(self, module_name: str) -> bool:
        """
        Пытается захватить ресурс для генерации.
        Возвращает True если успешно, False если ресурс уже занят.
        """
        if self._resource_owner is not None:
            return False  # Ресурс уже занят другим модулем
        
        self._resource_owner = module_name
        self.resource_acquired.emit(module_name)
        print(f"Ресурс захвачен: {module_name}")
        return True
    
    def release_resource(self):
        """Освобождает ресурс после завершения генерации"""
        if self._resource_owner:
            print(f"Ресурс освобождён: {self._resource_owner}")
            self._resource_owner = None
            self.resource_released.emit()
    
    def is_resource_busy(self) -> bool:
        """Проверяет, занят ли ресурс генерацией"""
        return self._resource_owner is not None
    
    def get_resource_owner(self) -> str:
        """Возвращает имя модуля, который владеет ресурсом (или None)"""
        return self._resource_owner
