from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QInputDialog, QMessageBox
from ui.chat_widget import ChatWidget
from ui.chat_control_panel import ChatControlPanel
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.chat_exporter import ChatExporter
from core.branch_cache import BranchCache
from core.chat_versions import ChatVersions
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal, QTimer
import time
import requests
import json
import os


class OllamaTab(QWidget):
    state_changed = pyqtSignal(dict)

    def __init__(self, config, resource_manager):
        super().__init__()
        self.config = config
        self.resource_manager = resource_manager
        self.chat_manager = ChatManager()
        self.client = None
        self._current_response_text = ""
        self.last_stats = None
        self._had_error = False
        self._last_status_update = 0.0
        
        # Состояние таба: свободное или зафиксированное
        self._chat_locked = False
        self._current_mode = "new"
        self._pending_clear_after_save = False  # Флаг для очистки после сохранения
        self._current_chat_base_path = None     # Путь к загруженному файлу (без расширения)
        self._current_chat_title = "Без названия"
        self._current_branches = {}             # Словарь веток из загруженного JSON
        self._is_branching = False              # Флаг: следующее сохранение — это ветка
        self._branch_from_index = -1            # Индекс user-сообщения, от которого ветвимся"
        self.branch_cache = BranchCache()        # Кэш веток активного чата
        self.chat_versions = None              # Модуль нумерованных чатов (создаётся при первом сообщении)
        self._chat_folder = None               # Путь к папке текущего чата (None = папка ещё не создана)
        self._chat_number = 0                  # Номер текущего чата в папке
        self._pending_branch_tail = None         # Хвост, ждущий отправки новой ветки
        self._is_editing = False                   # Режим правки: кнопка «Изменить» нажата, ждём отправки
        self._edit_backup = None                   # Сохранённый хвост для отмены правки
        self._pending_sync_variants = None         # {fork_index, old_variants} — для синхронизации после сохранения

        self._progress_timer = QTimer()
        self._progress_timer.setInterval(1000)
        self._progress_timer.timeout.connect(self._update_progress)
        self._generation_start_time = None
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "status_color": "green",
            "elapsed_seconds": 0,
            "is_running": False
        }

        layout = QHBoxLayout(self)

        left_layout = QVBoxLayout()
        self.chat_widget = ChatWidget()
        self.chat_widget.set_auto_scroll(self.config.get("chat_auto_scroll", True))
        self.chat_control_panel = ChatControlPanel()
        left_layout.addWidget(self.chat_widget, 1)
        left_layout.addWidget(self.chat_control_panel)

        self.settings_panel = SettingsPanel(self.config)

        timeout_sec = self.settings_panel.timeout_spin.value()
        self._bar_state["progress_total"] = timeout_sec

        layout.addLayout(left_layout, 3)
        layout.addWidget(self.settings_panel, 1)

        # Подключения
        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)
        self.settings_panel.mode_changed.connect(self._on_mode_changed)
        self.settings_panel.chat_selected.connect(self._on_chat_selected)
        
        self.chat_control_panel.new_chat_clicked.connect(self._on_new_chat_clicked)
        self.chat_control_panel.undo_last_clicked.connect(self.undo_last_message)
        self.chat_control_panel.attach_file_clicked.connect(self._on_attach_file)
        self.chat_control_panel.export_chat_clicked.connect(self._on_export_chat)
        
        # Подключение сигналов ветвления из chat_widget
        self.chat_widget.trim_requested.connect(self._on_trim_requested)
        self.chat_widget.branch_requested.connect(self._on_branch_requested)
        self.chat_widget.switch_branch_requested.connect(self._on_switch_branch_requested)
        self.chat_widget.load_chat_requested.connect(self._on_load_chat_requested)

    def _on_timeout_changed(self, value):
        self.state_changed.emit(self._bar_state.copy())

    def get_bar_state(self) -> dict:
        return self._bar_state.copy()

    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())

    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())

    def _set_status(self, message: str, color: str = "#DAA520"):
        self._bar_state["status"] = message
        self._bar_state["status_color"] = color
        self.state_changed.emit(self._bar_state.copy())

    def _update_undo_button_state(self):
        msgs = self.chat_manager.messages
        can_undo = self._bar_state.get("is_running", False) or len(msgs) > 0
        self.chat_control_panel.set_undo_enabled(can_undo)

    def _on_mode_changed(self, mode: str):
        """Обработка смены режима (только в свободном состоянии)"""
        if self._chat_locked:
            return
        
        self._current_mode = mode
        self.settings_panel._update_ui_state(mode, locked=False)
        
        if mode == "new":
            self._set_status("Режим: Новый чат", "green")
        elif mode == "resume":
            self._set_status("Режим: Выберите чат для продолжения", "#DAA520")
        elif mode == "edit":
            self._set_status("Режим: Выберите чат для редактирования", "#DAA520")

    def _on_chat_selected(self, folder_path: str):
        """Загрузка чата из папки (новая модель: нумерованные чаты)"""
        print(f"[DEBUG] _on_chat_selected: папка {folder_path}, mode='{self._current_mode}'")
        if not os.path.isdir(folder_path):
            self._set_status("⚠ Папка чата не найдена", "red")
            return
        
        try:
            if self.chat_versions is None:
                self.chat_versions = ChatVersions(self.config.get_chats_dir())
            
            chat_data = self.chat_versions.load_last(folder_path)
            if chat_data is None:
                self._set_status("⚠ В папке нет чатов", "orange")
                return
            
            self.chat_manager.load_messages(chat_data.get("messages", []))
            
            # Запоминаем папку и номер ДО перерисовки (нужно для навигации по номерам)
            self._chat_folder = folder_path
            self._chat_number = chat_data.get("number", 1)
            self._current_chat_title = os.path.basename(folder_path)
            self._current_chat_base_path = folder_path
            
            if "settings" in chat_data:
                self.settings_panel.apply_settings_from_chat(chat_data["settings"])
            
            self._reload_chat_view()
            
            # Старая логика веток в новой модели не используется
            self._current_branches = {}
            self.branch_cache.clear()
            self._pending_branch_tail = None
            print(f"[DEBUG] _on_chat_selected: папка='{self._chat_folder}', чат №{self._chat_number}")
            
            self._chat_locked = True
            self.settings_panel.set_mode(self._current_mode, locked=True)
            
            self._update_undo_button_state()
            self._set_status(f"💾 Загружен чат №{self._chat_number} из '{os.path.basename(folder_path)}'", "green")
            
        except Exception as e:
            self._set_status(f"❌ Ошибка загрузки чата: {e}", "red")

    def _on_new_chat_clicked(self):
        """Кнопка '+ Новый чат' с защитным вопросом"""
        # Если чат уже сохранён (есть base_path), просто очищаем его без лишних вопросов
        if self._current_chat_base_path and len(self.chat_manager.messages) > 0:
            self._clear_chat_internal()
            return
            
        if len(self.chat_manager.messages) > 0:
            reply = QMessageBox.question(
                self,
                "Новый чат",
                "Текущий чат не сохранён. Сохранить перед очисткой?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Устанавливаем флаг очистки после сохранения
                self._pending_clear_after_save = True
                self._on_export_chat()
            elif reply == QMessageBox.StandardButton.No:
                self._clear_chat_internal()
            else:
                return
        else:
            self._clear_chat_internal()

    def _clear_chat_internal(self):
        """Внутренний метод очистки чата"""
        self.chat_manager.clear()
        self.chat_widget.clear_chat()
        self.settings_panel.chat_file_edit.clear()
        self._chat_locked = False
        self._current_mode = "new"
        self._current_chat_base_path = None
        self._current_chat_title = "Без названия"
        self.branch_cache.clear()
        self._pending_branch_tail = None
        self._chat_folder = None
        self._chat_number = 0
        self._is_editing = False
        self._edit_backup = None
        self._pending_sync_variants = None
        self.settings_panel.set_mode("new", locked=False)
        self._update_undo_button_state()
        self.update_bar_state("prompt", "")
        self._set_status("Чат очищен", "green")

    def handle_prompt(self, text):
        if not text:
            return

        if self._current_mode in ["resume", "edit"] and not self._chat_locked:
            self._set_status("⚠ Загрузите чат через 📂", "orange")
            return

        self.update_bar_state("prompt", text)
        if not self.resource_manager.acquire_resource("ollama"):
            self._set_status("⚠ Ресурс занят другой моделью", "orange")
            self.update_bar_state("is_running", False)
            return
        self.update_bar_state("is_running", True)

        if not self._chat_locked:
            self._chat_locked = True
            self.settings_panel.set_mode(self._current_mode, locked=True)
            # Новая модель: при первом сообщении создаём папку чата
            if self._chat_folder is None:
                if self.chat_versions is None:
                    self.chat_versions = ChatVersions(self.config.get_chats_dir())
                self._chat_folder = self.chat_versions.create_folder(text)
                self._chat_number = 1
                print(f"[DEBUG] Создана папка чата: {self._chat_folder}")

        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)
        self.update_bar_state("progress_current", 0)
        self._generation_start_time = time.time()
        self._progress_timer.start()
        self._set_status("Обработка промпта...", "#DAA520")

        # Режим правки: создаём новый номер чата
        if self._is_editing:
            old_number = self._chat_number
            print(f"[DEBUG] Режим правки: создаём чат №{old_number + 1}")
            self._chat_number = self.chat_versions.next_number(self._chat_folder)
            self._is_editing = False
            self._edit_backup = None
            self.chat_manager.add_user_message(text)
            # Новое сообщение переиспользует индекс отредактированного — это и есть точка ветвления
            fork_index = self.chat_manager.messages[-1].get("user_msg_index", -1)
            if fork_index >= 0 and self.chat_versions is not None and self._chat_folder is not None:
                # Кто уже есть в этой точке: читаем из сохранённого исходного чата
                old_variants = self.chat_versions.get_message_variants(self._chat_folder, old_number, fork_index)
                if not old_variants:
                    old_variants = [old_number]
                new_variants = list(old_variants) + [self._chat_number]
                # Ставим варианты новому сообщению в памяти
                self.chat_manager.set_variants_for(fork_index, new_variants)
                # Запоминаем, кого синхронизировать после сохранения
                self._pending_sync_variants = {"fork_index": fork_index, "old_variants": old_variants}
        else:
            self.chat_manager.add_user_message(text)
        
        # Получаем индекс нового сообщения и количество веток для него (диск + кэш)
        user_msg_index = self.chat_manager.messages[-1].get("user_msg_index", -1)
        branches_count = self._branches_count_for(user_msg_index)
        self.chat_widget.append_user_message(text, user_msg_index, branches_count)

        self._current_response_text = ""
        self.last_stats = None
        self._had_error = False
        self._last_status_update = 0.0
        self._update_undo_button_state()

        sys_prompt = self.settings_panel.sys_prompt.toPlainText()
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.extend(self.chat_manager.get_messages())

        options = {
            "temperature": self.settings_panel.temp_spin.value(),
            "top_p": self.settings_panel.top_p_spin.value(),
            "num_predict": self.settings_panel.max_tokens_spin.value()
        }

        self.client = OllamaClient(
            url=self.config.get("url", "http://localhost:11434"),
            model=self.settings_panel.model_combo.currentText(),
            messages=messages,
            options=options,
            timeout=self.settings_panel.timeout_spin.value(),
            stream=self.settings_panel.stream_check.isChecked()
        )

        self.client.token_received.connect(self.on_token)
        self.client.generation_finished.connect(self.on_finished)
        self.client.error_occurred.connect(self.on_error)
        self.client.stats_received.connect(self.on_stats)

        self.client.start()
        self.update_bar_state("prompt", "")

    def _on_trim_requested(self, user_msg_index: int):
        """Обрезает чат до указанного сообщения пользователя (включительно)"""
        # Находим индекс этого сообщения в списке
        target_idx = -1
        for i, msg in enumerate(self.chat_manager.messages):
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                target_idx = i
                break
        
        if target_idx != -1:
            # Удаляем ВСЁ начиная с указанного user-сообщения (включительно)
            self.chat_manager.messages = self.chat_manager.messages[:target_idx]
            self._reload_chat_view()
            self._set_status("🗑 Удалено", "green")

    def _on_branch_requested(self, user_msg_index: int):
        """Изменить: входит в режим правки, сохраняет хвост, обрезает чат, возвращает текст в промпт"""
        # Находим позицию сообщения
        target_idx = -1
        msg_text = ""
        for i, msg in enumerate(self.chat_manager.messages):
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                target_idx = i
                msg_text = msg.get("content", "")
                break
        
        if target_idx == -1:
            return
        
        # Сохраняем хвост (сообщение N и всё после) для отмены
        self._edit_backup = [m.copy() for m in self.chat_manager.messages[target_idx:]]
        self._is_editing = True
        
        # Обрезаем чат до N (не включая N)
        self.chat_manager.messages = self.chat_manager.messages[:target_idx]
        # Новое сообщение переиспользует индекс отредактированного
        self.chat_manager.set_next_index(user_msg_index)
        self._reload_chat_view()
        
        # Возвращаем текст в промпт
        if msg_text:
            self.update_bar_state("prompt", msg_text)
        self._set_status("✏ Режим правки: отредактируйте промпт и отправьте (или ↶ для отмены)", "#DAA520")

    def _on_switch_branch_requested(self, user_msg_index: int):
        """Диалог выбора ветки: все ветки (кэш + диск) для данного сообщения."""
        idx_str = str(user_msg_index)
        print(f"[DEBUG] 📂 клик: idx={user_msg_index}, кэш={[(b['id'], b['parent_user_msg_index']) for b in self.branch_cache.get_all()]}, диск={self._current_branches.get(idx_str, [])}")
        options = []  # (label, source_type, ref)

        for b in self.branch_cache.get_for_index(user_msg_index):
            preview = self._branch_preview(b["messages"], user_msg_index)
            options.append((f"🗂 Кэш: {preview}", "cache", b["id"]))

        for filename in self._current_branches.get(idx_str, []):
            preview = filename.replace("branch_", "").replace(".json", "").replace("_", " ")
            options.append((f"💾 {preview}", "disk", filename))

        if not options:
            self._set_status("⚠ Нет доступных веток для этого сообщения", "orange")
            return

        labels = [o[0] for o in options]
        from PyQt6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(
            self, "Выбор ветки",
            f"Варианты от сообщения #{user_msg_index}:",
            labels, 0, False
        )
        if ok and choice:
            selected = options[labels.index(choice)]
            self._switch_to_branch(user_msg_index, selected[1], selected[2])

    def _switch_to_branch(self, user_msg_index: int, source_type: str, ref):
        """Своп: текущая последовательность уходит в кэш, выбранная становится активной."""
        print(f"[DEBUG] своп НАЧАЛО: source={source_type}, ref={ref}, кэш до={[(b['id'], b['parent_user_msg_index']) for b in self.branch_cache.get_all()]}")
        self.branch_cache.add(user_msg_index, self.chat_manager.messages, self._current_settings())
        print(f"[DEBUG] своп: заархивировали текущее, кэш={[(b['id'], b['parent_user_msg_index']) for b in self.branch_cache.get_all()]}")

        settings_to_apply = None
        if source_type == "cache":
            branch = self.branch_cache.get_by_id(ref)
            if not branch:
                self._set_status("❌ Ветка в кэше не найдена", "red")
                return
            messages = branch["messages"]
            settings_to_apply = branch.get("settings")
            self.branch_cache.remove_by_id(ref)
            print(f"[DEBUG] своп: удалили выбранную, кэш={[(b['id'], b['parent_user_msg_index']) for b in self.branch_cache.get_all()]}")
        else:
            messages, settings_to_apply = self._read_disk_branch(ref)
            if messages is None:
                return
            idx_str = str(user_msg_index)
            if ref in self._current_branches.get(idx_str, []):
                self._current_branches[idx_str].remove(ref)

        self.chat_manager.load_messages(messages)
        if settings_to_apply:
            self.settings_panel.apply_settings_from_chat(settings_to_apply)
        self._reload_chat_view()
        self._set_status("🌿 Ветка переключена (предыдущая сохранена в кэш)", "green")

    def _branch_preview(self, messages: list, user_msg_index: int) -> str:
        """Короткое превью: текст сообщения пользователя в точке ветвления."""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("user_msg_index") == user_msg_index:
                text = msg.get("content", "").replace("\n", " ")
                return text[:40] + ("…" if len(text) > 40 else "")
        return "без превью"

    def _read_disk_branch(self, branch_filename: str):
        """Читает ветку с диска. Возвращает (messages, settings) или (None, None)."""
        try:
            if self._current_chat_base_path:
                folder = os.path.dirname(self._current_chat_base_path)
            else:
                folder = self.config.get_chats_dir()
            file_path = os.path.join(folder, branch_filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("messages", []), data.get("settings")
        except Exception as e:
            self._set_status(f"❌ Ошибка чтения ветки: {e}", "red")
            return None, None

    def _reload_chat_view(self):
        """Перерисовывает чат на основе текущих сообщений в chat_manager"""
        self.chat_widget.clear_chat()
        # Функция навигации: берём готовые варианты прямо из сообщения
        def find_alts(user_idx):
            for msg in self.chat_manager.messages:
                if msg.get("role") == "user" and msg.get("user_msg_index") == user_idx:
                    variants = msg.get("variants", [])
                    if len(variants) > 1:
                        return variants
                    return None
            return None
        self.chat_widget.load_chat(self.chat_manager.messages, alternatives_func=find_alts, current_chat_number=self._chat_number)
        self._update_undo_button_state()

    def _autosave_current(self):
        """Сохраняет текущий чат в его папку под текущим номером (новая модель)."""
        if self.chat_versions is None or self._chat_folder is None:
            return
        try:
            self.chat_versions.save(self._chat_folder, self._chat_number,
                                    self.chat_manager.messages, self._current_settings())
            self.chat_versions.set_last_number(self._chat_folder, self._chat_number)
            # Синхронизация вариантов после ветвления
            if self._pending_sync_variants:
                fork_index = self._pending_sync_variants["fork_index"]
                old_variants = self._pending_sync_variants["old_variants"]
                new_variants = self.chat_versions.sync_variants_on_branch(
                    self._chat_folder, fork_index, old_variants, self._chat_number
                )
                print(f"[DEBUG] Синхронизация вариантов: узел {fork_index}, новые варианты {new_variants}")
                self._pending_sync_variants = None
        except Exception as e:
            print(f"[DEBUG] Ошибка автосохранения: {e}")

    def _current_settings(self) -> dict:
        """Снимок текущих настроек чата (для веток и сохранения)."""
        return {
            "model": self.settings_panel.model_combo.currentText(),
            "temperature": self.settings_panel.temp_spin.value(),
            "top_p": self.settings_panel.top_p_spin.value(),
            "max_tokens": self.settings_panel.max_tokens_spin.value(),
            "system_prompt": self.settings_panel.sys_prompt.toPlainText(),
            "timeout": self.settings_panel.timeout_spin.value(),
            "stream": self.settings_panel.stream_check.isChecked()
        }

    def _merged_branches(self) -> dict:
        """Сводный словарь веток: на диске (_current_branches) + в кэше."""
        merged = {k: list(v) for k, v in self._current_branches.items()}
        for b in self.branch_cache.get_all():
            key = str(b["parent_user_msg_index"])
            merged.setdefault(key, []).append(f"__cache_{b['id']}__")
        return merged

    def _branches_count_for(self, user_msg_index: int) -> int:
        """Общее число веток для сообщения: диск + кэш."""
        return len(self._merged_branches().get(str(user_msg_index), []))

    def on_token(self, token):
        self._current_response_text += token
        now = time.time()
        if now - self._last_status_update >= 0.1:
            self._last_status_update = now
            last_line = self._current_response_text.split('\n')[-1]
            display = last_line if len(last_line) <= 100 else last_line[:97] + "..."
            self._set_status(display, "gray")

    def _update_progress(self):
        if self._generation_start_time:
            elapsed = int(time.time() - self._generation_start_time)
            self.update_bar_state("progress_current", elapsed)
            self.update_bar_state("elapsed_seconds", elapsed)

    def on_finished(self):
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self.chat_manager.add_assistant_message(self._current_response_text, self.last_stats)
        self.settings_panel.save_settings()

        self.chat_widget.append_assistant_message(self._current_response_text, self.last_stats)
        self._update_undo_button_state()
        self._autosave_current()

        self.resource_manager.release_resource()
        self.update_bar_state("is_running", False)
        if not self._had_error:
            self._set_status("Готово", "green")

        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def on_stats(self, stats_dict):
        self.last_stats = stats_dict

    def on_error(self, error_msg):
        self._progress_timer.stop()
        self._generation_start_time = None
        self.update_bar_state("progress_current", 0)
        timeout_sec = self.settings_panel.timeout_spin.value()
        self.update_bar_state("progress_total", timeout_sec)

        self._had_error = True
        self._current_response_text += f"\n\n⚠ Ошибка: {error_msg}"

        self.update_bar_state("is_running", False)
        self._set_status(f"Ошибка: {error_msg}", "red")

        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.reset_action_state()

    def stop_generation(self):
        self._progress_timer.stop()
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            main_window.shared_bar.set_stopping_state()
        if self.client and self.client.isRunning():
            self.client.stop()

    def clear_chat(self):
        """Публичный метод очистки (используется извне)"""
        self._clear_chat_internal()

    def undo_last_message(self):
        # Если в режиме правки — отменяем правку (возвращаем хвост)
        if self._is_editing and self._edit_backup:
            self.chat_manager.messages.extend(self._edit_backup)
            self.chat_manager.recalc_counter()
            self._reload_chat_view()
            self.update_bar_state("prompt", "")
            self._is_editing = False
            self._edit_backup = None
            self._set_status("↶ Правка отменена, возвращён исходный чат", "green")
            return
        
        # Старая логика: удалить последнее сообщение
        if self._bar_state.get("is_running", False):
            self.stop_generation()
            self._current_response_text = ""
            self._had_error = False
        
        last_user_text = self.chat_manager.remove_last_message()
        if last_user_text:
            self.chat_widget.remove_last_message()
            self.update_bar_state("prompt", last_user_text)
            self._update_undo_button_state()
            self._set_status("Действие отменено, текст возвращён в промпт", "#DAA520")

    def _on_attach_file(self):
        self._set_status("📎 Загрузка файлов пока в разработке", "#DAA520")

    def _on_export_chat(self):
        print(f"[DEBUG] _on_export_chat: mode='{self._current_mode}', base_path='{self._current_chat_base_path}', title='{self._current_chat_title}', is_branching={self._is_branching}")
        if not self.chat_manager.messages:
            self._set_status("⚠ Нечего сохранять — чат пуст", "orange")
            return
        
        # Если мы в режиме ветвления — сохраняем как ветку
        if self._is_branching and self._current_chat_base_path:
            print(f"[DEBUG] Сохраняем как ветку от индекса {self._branch_from_index}")
            self._save_chat(self._current_chat_title, is_branch=True, parent_user_msg_index=self._branch_from_index)
            # Сбрасываем флаги
            self._is_branching = False
            self._branch_from_index = -1
            return
        
        # Логика сохранения в зависимости от режима и наличия исходного файла
        if self._current_mode == "resume" and self._current_chat_base_path:
            # Режим "Продолжить": обновляем main.json (is_branch=False)
            self._save_chat(self._current_chat_title, is_branch=False)
            return
        
        if self._current_mode == "edit" and self._current_chat_base_path:
            # Режим "Изменить": создаём ветку от последнего user-сообщения
            last_user_idx = -1
            for msg in reversed(self.chat_manager.messages):
                if msg.get("role") == "user":
                    last_user_idx = msg.get("user_msg_index", -1)
                    break
            self._save_chat(self._current_chat_title, is_branch=True, parent_user_msg_index=last_user_idx)
            return
        
        # Стандартное поведение для нового чата или если путь неизвестен
        if self.config.get("chat_auto_title", True):
            self._set_status("🤖 Генерация названия...", "#DAA520")
            self._generate_title_async()
        else:
            self._show_save_dialog("")

    def _generate_title_async(self):
        context_messages = []
        for msg in self.chat_manager.messages[:6]:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            content = msg["content"][:200]
            context_messages.append(f"{role}: {content}")
        
        prompt = (
            "Придумай короткий заголовок (максимум 3 слова) для этого диалога. "
            "Заголовок должен отражать основную тему. "
            "Отвечай ТОЛЬКО самим заголовком, без кавычек и пояснений.\n\n"
            + "\n".join(context_messages)
        )

        self._title_buffer = ""
        self._title_client = OllamaClient(
            url=self.config.get("url", "http://localhost:11434"),
            model=self.settings_panel.model_combo.currentText(),
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 30},
            timeout=30,
            stream=False
        )
        self._title_client.token_received.connect(self._on_title_token)
        self._title_client.generation_finished.connect(self._on_title_finished)
        self._title_client.error_occurred.connect(self._on_title_error)
        self._title_client.start()

    def _on_title_token(self, token):
        self._title_buffer += token

    def _on_title_finished(self):
        title = self._title_buffer.strip().replace('\n', ' ')[:50]
        title = title.strip('"\'')
        self._show_save_dialog(title)

    def _on_title_error(self, error_msg):
        self._set_status(f"⚠ Не удалось сгенерировать название: {error_msg}", "orange")
        self._show_save_dialog("")

    def _show_save_dialog(self, default_title: str):
        title, ok = QInputDialog.getText(
            self, "Сохранить чат", "Название чата:", text=default_title
        )
        if ok and title.strip():
            self._save_chat(title.strip())
        elif ok:
            self._set_status("⚠ Сохранение отменено: название не указано", "orange")
            # Сбрасываем флаг, если пользователь отменил ввод названия
            self._pending_clear_after_save = False

    def _save_chat(self, title: str, is_branch: bool = False, parent_user_msg_index: int = -1):
        try:
            settings = {
                "model": self.settings_panel.model_combo.currentText(),
                "temperature": self.settings_panel.temp_spin.value(),
                "top_p": self.settings_panel.top_p_spin.value(),
                "max_tokens": self.settings_panel.max_tokens_spin.value(),
                "system_prompt": self.settings_panel.sys_prompt.toPlainText(),
                "timeout": self.settings_panel.timeout_spin.value(),
                "stream": self.settings_panel.stream_check.isChecked()
            }
            
            chats_dir = self.config.get_chats_dir()
            exporter = ChatExporter(chats_dir)
            
            # Имя папки: используем сгенерированный title, если чат новый
            folder_name = title if self._current_chat_title == "Без названия" else self._current_chat_title
            
            result = exporter.export_chat(
                chat_folder_name=folder_name,
                title=title,
                messages=self.chat_manager.messages,
                settings=settings,
                save_json=self.config.get("chat_save_json", True),
                save_txt=self.config.get("chat_save_txt", True),
                is_branch=is_branch,
                parent_user_msg_index=parent_user_msg_index if is_branch else None
            )
            
            saved_files = []
            if "json" in result: saved_files.append("JSON")
            if "txt" in result: saved_files.append("TXT")
            
            # НЕ размораживаем UI после сохранения — пользователь может продолжить писать
            # self._chat_locked = False
            # self.settings_panel.set_mode(self._current_mode, locked=False)
            
            display_name = folder_name
            branch_note = " (новая ветка)" if is_branch else ""
            self._set_status(f"💾 Чат '{display_name}' сохранён{branch_note} ({', '.join(saved_files)})", "green")
            
            # Обновляем базовый путь, чтобы система знала, что чат сохранён
            if "main_json" in result:
                self._current_chat_base_path = os.path.splitext(result["main_json"])[0]
                self._current_chat_title = title
            
            # Обновляем _current_branches после сохранения
            if is_branch and "json" in result and parent_user_msg_index != -1:
                branch_filename = os.path.basename(result["json"])
                idx_str = str(parent_user_msg_index)
                if idx_str not in self._current_branches:
                    self._current_branches[idx_str] = []
                if branch_filename not in self._current_branches[idx_str]:
                    self._current_branches[idx_str].append(branch_filename)
                # Перерисовываем чат с обновлёнными кнопками
                self._reload_chat_view()
            
            # Проверяем флаг и очищаем чат, если нужно
            if self._pending_clear_after_save:
                self._pending_clear_after_save = False
                self._clear_chat_internal()
            
        except Exception as e:
            self._set_status(f"❌ Ошибка сохранения: {e}", "red")
            # Сбрасываем флаг при ошибке
            self._pending_clear_after_save = False

    def _on_load_chat_requested(self, chat_number: int):
        """Загрузка чата по номеру (переключение между вариантами)"""
        if self.chat_versions is None or self._chat_folder is None:
            return
        data = self.chat_versions.load(self._chat_folder, chat_number)
        if data is None:
            self._set_status(f"⚠ Чат №{chat_number} не найден", "red")
            return
        self.chat_manager.load_messages(data.get("messages", []))
        if "settings" in data:
            self.settings_panel.apply_settings_from_chat(data["settings"])
        self._chat_number = chat_number
        self.chat_versions.set_last_number(self._chat_folder, chat_number)
        self._reload_chat_view()
        self._set_status(f"💾 Загружен чат №{chat_number}", "green")

    def unload(self):
        try:
            requests.post(f"{self.config.get_ollama_url()}/api/generate",
                         json={"model": self.settings_panel.model_combo.currentText(),
                               "keep_alive": 0},
                         timeout=5)
        except Exception:
            pass
