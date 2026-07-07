# === LOCAL AI LITE - FULL CONTEXT ===
# Generated: Вт 07 июл 2026 14:47:06 MSK
# Usage: grep 'def method_name' full_context.py


# ════════════════════════════════════════════════════════════
# FILE: core/chat_manager.py
# ════════════════════════════════════════════════════════════

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

# ════════════════════════════════════════════════════════════
# FILE: core/checkpoint_manager.py
# ════════════════════════════════════════════════════════════

"""
Менеджер чекпоинтов для Resume генерации.
Сохраняет состояние генерации (latents, scheduler, generator) и метаданные.

Примечание: torch импортируется лениво внутри функций, которые работают с PT-файлами.
Функции, работающие только с JSON (load_archived_metadata, list_archived_checkpoints,
archive_checkpoint и т.д.), не требуют torch и могут вызываться из UI.
"""
import os
import json
from datetime import datetime

# Путь к папке чекпоинтов: data/checkpoints/ относительно корня проекта
CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "checkpoints"
)


def save_checkpoint(latents, scheduler, generator, params, current_step, remaining_timesteps, actual_seed=None, last_preview_path=""):
    """
    Сохраняет чекпоинт генерации.
    
    Args:
        latents: torch.Tensor - текущее состояние латентов
        scheduler: scheduler объект - для сохранения внутреннего состояния
        generator: torch.Generator - для восстановления детерминированности
        params: dict - параметры генерации (prompt, model, seed, etc.)
        current_step: int - текущий шаг (сколько шагов уже сделано)
        remaining_timesteps: list - оставшиеся timesteps для продолжения
        actual_seed: int - реальный seed (если был сгенерирован случайный)
    """
    import torch  # ленивый импорт — нужен только здесь
    
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    
    # JSON с метаданными (читаемый формат)
    json_data = {
        "prompt": params["prompt"],
        "negative_prompt": params.get("negative_prompt", ""),
        "model": params["model"],
        "scheduler": params["scheduler"],
        "seed": actual_seed if actual_seed is not None else params["seed"],
        "total_steps": params["total_steps"],
        "current_step": current_step,
        "width": params["width"],
        "height": params["height"],
        "cfg": params["cfg"],
        "device": params["device"],
        "remaining_timesteps": [
            t.item() if torch.is_tensor(t) else t
            for t in remaining_timesteps
        ],
        "preview_every": params.get("preview_every", 0),
        "preview_start": params.get("preview_start", 1),
        "last_preview_path": last_preview_path
    }
    
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # PT с torch-объектами (бинарный формат)
    torch_data = {
        "latents": latents.cpu(),
        "scheduler_state": scheduler.__dict__.copy(),
        "generator_state": generator.get_state()
    }
    
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    torch.save(torch_data, pt_path)


def load_checkpoint():
    """
    Загружает активный чекпоинт (JSON + PT).
    Используется в generate_diffusers.py при resume.
    
    Returns:
        tuple: (json_data, torch_data) или (None, None) если чекпоинт не найден
    """
    import torch  # ленивый импорт
    
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    
    if not os.path.exists(json_path) or not os.path.exists(pt_path):
        return None, None
    
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    # ИСПРАВЛЕНО: weights_only=False для PyTorch 2.6+
    torch_data = torch.load(pt_path, map_location="cpu", weights_only=False)
    
    return json_data, torch_data


def checkpoint_exists():
    """
    Проверяет наличие активного чекпоинта.
    
    Returns:
        bool: True если чекпоинт существует
    """
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    return os.path.exists(json_path) and os.path.exists(pt_path)


def delete_checkpoint():
    """Удаляет активный чекпоинт (после успешного завершения генерации)"""
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_path = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    
    if os.path.exists(json_path):
        os.remove(json_path)
    if os.path.exists(pt_path):
        os.remove(pt_path)


def get_checkpoint_info():
    """
    Возвращает краткую информацию об активном чекпоинте (для UI).
    
    Returns:
        dict или None
    """
    json_path = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    
    if not os.path.exists(json_path):
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "prompt": data.get("prompt", "")[:50] + "..." if len(data.get("prompt", "")) > 50 else data.get("prompt", ""),
            "model": os.path.basename(data.get("model", "")),
            "current_step": data.get("current_step", 0),
            "total_steps": data.get("total_steps", 0),
            "seed": data.get("seed", -1),
            "width": data.get("width", 0),
            "height": data.get("height", 0)
        }
    except Exception:
        return None


def archive_checkpoint():
    """
    Переименовывает активный чекпоинт в архивный с timestamp.
    Вызывается после завершения или остановки генерации.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_src = os.path.join(CHECKPOINT_DIR, "checkpoint.json")
    pt_src = os.path.join(CHECKPOINT_DIR, "checkpoint.pt")
    json_dst = os.path.join(CHECKPOINT_DIR, f"{timestamp}.json")
    pt_dst = os.path.join(CHECKPOINT_DIR, f"{timestamp}.pt")
    
    if os.path.exists(json_src):
        os.rename(json_src, json_dst)
    if os.path.exists(pt_src):
        os.rename(pt_src, pt_dst)


def list_archived_checkpoints():
    """
    Возвращает список архивных чекпоинтов (отсортированных по времени, новые первыми).
    
    Returns:
        list[dict]: [{"timestamp": str, "filename": str, "display_name": str}, ...]
    """
    checkpoints = []
    
    if not os.path.exists(CHECKPOINT_DIR):
        return checkpoints
    
    for filename in os.listdir(CHECKPOINT_DIR):
        if filename.endswith('.json') and filename != 'checkpoint.json':
            timestamp = filename[:-5]  # убираем .json
            # Формат: 2026-07-05_14-30-45 → 2026-07-05 14:30:45
            display_name = timestamp.replace('_', ' ').replace('-', ':', 2)
            checkpoints.append({
                "timestamp": timestamp,
                "filename": filename,
                "display_name": display_name
            })
    
    # Сортируем по timestamp (новые первыми)
    return sorted(checkpoints, key=lambda x: x["timestamp"], reverse=True)


def load_archived_metadata(filename):
    """
    Загружает ТОЛЬКО метаданные (JSON) из архивного чекпоинта.
    НЕ требует torch — безопасна для вызова из UI.
    
    Args:
        filename: имя файла (например, "2026-07-05_14-30-45.json")
    
    Returns:
        dict или None
    """
    json_path = os.path.join(CHECKPOINT_DIR, filename)
    
    if not os.path.exists(json_path):
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_archived_checkpoint(filename):
    """
    Загружает полный архивный чекпоинт (JSON + PT).
    ТРЕБУЕТ torch — используется только в generate_diffusers.py.
    
    Args:
        filename: имя файла (например, "2026-07-05_14-30-45.json")
    
    Returns:
        tuple: (json_data, torch_data) или (None, None) если не найден
    """
    import torch  # ленивый импорт
    
    json_path = os.path.join(CHECKPOINT_DIR, filename)
    pt_path = json_path.replace('.json', '.pt')
    
    if not os.path.exists(json_path) or not os.path.exists(pt_path):
        return None, None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        
        # ИСПРАВЛЕНО: weights_only=False для PyTorch 2.6+
        torch_data = torch.load(pt_path, map_location="cpu", weights_only=False)
        
        return json_data, torch_data
    except Exception:
        return None, None

# ════════════════════════════════════════════════════════════
# FILE: core/diffusers_worker.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtCore import QObject, QProcess, pyqtSignal
import json
import os
from datetime import datetime


class DiffusersWorker(QObject):
    step_updated = pyqtSignal(int, int, str)      # step, total, image_path
    generation_finished = pyqtSignal(str, int)    # final_path, seed
    error_occurred = pyqtSignal(str)
    status_message = pyqtSignal(str)              # статусное сообщение для UI
    log_line = pyqtSignal(str)                    # каждая строка вывода

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self._stopped_by_user = False
        self._log_file = None
        self._log_path = None

    def start(self, prompt, negative_prompt, params, resume=False, checkpoint_file=None):
        """Запускает процесс генерации"""
        self._stopped_by_user = False

        # === Открываем файл лога ===
        # ИСПРАВЛЕНО: логи теперь в data/logs/, а не в output_dir/logs/
        from utils.config import Config
        config = Config()
        log_dir = config.get_logs_dir()
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = os.path.join(log_dir, f"diffusers_{timestamp}.log")
        try:
            self._log_file = open(self._log_path, "w", encoding="utf-8")
            self._log_file.write(f"=== Diffusers Generation Log ===\n")
            self._log_file.write(f"Prompt: {prompt}\n")
            self._log_file.write(f"Negative: {negative_prompt}\n")
            self._log_file.write(f"Model: {params.get('model', '')}\n")
            self._log_file.write(f"Scheduler: {params.get('scheduler', '')}\n")
            self._log_file.write(f"Steps: {params.get('steps', 0)}\n")
            self._log_file.write(f"CFG: {params.get('cfg', 0)}\n")
            self._log_file.write(f"Size: {params.get('width', 0)}x{params.get('height', 0)}\n")
            self._log_file.write(f"Seed: {params.get('seed', -1)}\n")
            self._log_file.write(f"Device: {self.config.get('sdxl/device', 'cuda')}\n")
            self._log_file.write(f"Resume: {resume}\n")
            self._log_file.write(f"Checkpoint file: {checkpoint_file}\n")
            self._log_file.write(f"Preview every: {params.get('preview_every', 0)}\n")
            self._log_file.write(f"Preview start: {params.get('preview_start', 1)}\n")
            self._log_file.write(f"Output dir: {self.config.get_sdxl_output_dir()}\n")
            self._log_file.write("=" * 40 + "\n\n")
            self._log_file.flush()
        except Exception as e:
            print(f"[DiffusersWorker] Не удалось открыть файл лога: {e}")
            self._log_file = None

        venv_path = self.config.get_sdxl_venv_path()
        if not venv_path:
            self.error_occurred.emit("Не указан путь к venv для Diffusers")
            self._close_log_file()
            return

        python_path = os.path.join(venv_path, "bin", "python")
        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_diffusers.py")
        script_path = os.path.abspath(script_path)

        if not os.path.exists(script_path):
            self.error_occurred.emit(f"Скрипт не найден: {script_path}")
            self._close_log_file()
            return

        # Определяем полный путь к модели
        model_name = params["model"]
        models_path = self.config.get_sdxl_models_path()

        safetensors_path = os.path.join(models_path, f"{model_name}.safetensors")
        ckpt_path = os.path.join(models_path, f"{model_name}.ckpt")

        if os.path.isfile(safetensors_path):
            model_path = safetensors_path
        elif os.path.isfile(ckpt_path):
            model_path = ckpt_path
        else:
            model_path = model_name

        args = [
            script_path,
            "--prompt", prompt,
            "--negative", negative_prompt,
            "--model", model_path,
            "--scheduler", params["scheduler"],
            "--steps", str(params["steps"]),
            "--cfg", str(params["cfg"]),
            "--width", str(params["width"]),
            "--height", str(params["height"]),
            "--seed", str(params["seed"]),
            "--device", self.config.get("sdxl/device", "cuda"),
            "--preview-every", str(params.get("preview_every", 0)),
            "--preview-start", str(params.get("preview_start", 1)),
            "--output_dir", self.config.get_sdxl_output_dir(),
            "--preview-dir", self.config.get_previews_dir(),
            "--cache_dir", models_path
        ]

        if self.config.get("sdxl/no_safety_checker", "false") == "true":
            args.append("--no-safety-checker")

        if resume:
            args.append("--resume")
            if checkpoint_file:
                args.extend(["--checkpoint-file", checkpoint_file])

        self.process = QProcess()
        self.process.setProgram(python_path)
        self.process.setArguments(args)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.start()

    def stop(self):
        """Останавливает процесс (ручная остановка пользователем)"""
        self._stopped_by_user = True
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()

        self._close_log_file()
        self.generation_finished.emit("", -1)

    def _close_log_file(self):
        """Закрывает файл лога"""
        if self._log_file:
            try:
                self._log_file.write("\n=== Generation finished ===\n")
                self._log_file.write(f"Log saved to: {self._log_path}\n")
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _on_output(self):
        """Обрабатывает ВСЕ строки вывода процесса"""
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 1. Пишем в файл лога
            if self._log_file:
                try:
                    self._log_file.write(line + '\n')
                    self._log_file.flush()
                except Exception:
                    pass

            # 2. Эмитим сигнал для бегущей строки в UI
            self.log_line.emit(line)

            # 3. Пытаемся распарсить JSON (для UI)
            try:
                msg = json.loads(line)
                msg_type = msg.get("type")

                if msg_type == "step":
                    step = msg.get("step", 0)
                    total = msg.get("total_steps", 0)
                    image_path = msg.get("image_path", "")
                    self.step_updated.emit(step, total, image_path)

                elif msg_type == "done":
                    final_path = msg.get("final_path", "")
                    seed = msg.get("seed", -1)
                    self.generation_finished.emit(final_path, seed)

                elif msg_type == "error":
                    error_msg = msg.get("message", "Неизвестная ошибка")
                    self.error_occurred.emit(error_msg)

                elif msg_type == "status":
                    status_msg = msg.get("message", "")
                    self.status_message.emit(status_msg)

                elif msg_type == "warning":
                    warning_msg = msg.get("message", "")
                    self.status_message.emit(f"⚠ {warning_msg}")

            except json.JSONDecodeError:
                pass

    def _on_finished(self, exit_code, exit_status):
        """Процесс завершён"""
        self._close_log_file()

        if self._stopped_by_user:
            return

        # Дочитываем оставшийся вывод
        remaining = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        if remaining.strip():
            for line in remaining.split('\n'):
                if line.strip():
                    self.log_line.emit(line.strip())

                    try:
                        msg = json.loads(line.strip())
                        msg_type = msg.get("type")

                        if msg_type == "done":
                            self.generation_finished.emit(
                                msg.get("final_path", ""),
                                msg.get("seed", -1)
                            )
                        elif msg_type == "error":
                            self.error_occurred.emit(msg.get("message", "Неизвестная ошибка"))
                        elif msg_type == "status":
                            self.status_message.emit(msg.get("message", ""))

                    except json.JSONDecodeError:
                        pass

        # Игнорируем код 15 (SIGTERM — нормальная остановка)
        if exit_code != 0 and exit_code != 15:
            self.error_occurred.emit(f"Процесс завершился с кодом {exit_code}")

    def _on_process_error(self, error):
        """Ошибка запуска процесса"""
        if self._stopped_by_user:
            return

        if error == QProcess.ProcessError.Crashed:
            return

        self.error_occurred.emit(f"Ошибка запуска: {error}")

# ════════════════════════════════════════════════════════════
# FILE: core/__init__.py
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# FILE: core/markdown_parser.py
# ════════════════════════════════════════════════════════════

# /home/lin/Scripts/OLLAMA/core/markdown_parser.py

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QTextCursor
import re
import base64


class MarkdownParser:
    def __init__(self):
        pass

    def _get_colors(self):
        """Берёт актуальные системные цвета при каждом вызове"""
        palette = QApplication.palette()
        return {
            'text': palette.color(QPalette.ColorRole.WindowText).name(),
            'base': palette.color(QPalette.ColorRole.Base).name(),
            'alt_base': palette.color(QPalette.ColorRole.AlternateBase).name(),
            'link': palette.color(QPalette.ColorRole.Link).name(),
            'highlight': palette.color(QPalette.ColorRole.Highlight).name(),
        }

    def _escape_html(self, text):
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))

    def _format_inline(self, text, colors):
        """Обработка инлайн-элементов"""
        text = self._escape_html(text)
        # Инлайн-код
        text = re.sub(
            r'`([^`]+)`',
            lambda m: f'<code style="background:{colors["alt_base"]};padding:2px 5px;'
                      f'font-family:Consolas,monospace;">{m.group(1)}</code>',
            text
        )
        # Жирный + курсив
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
        # Жирный
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Курсив
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        # Ссылки
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{m.group(2)}" style="color:{colors["link"]};">{m.group(1)}</a>',
            text
        )
        return text

    def _render_code_block(self, code_text, lang, colors, is_open=False,
                           msg_index=-1, code_block_index=-1):
        """Рендерит блок кода: серый фон у ячейки с кодом, тонкая рамка, фиолетовый монохромный код"""

        # Экранируем код без подсветки
        escaped_code = self._escape_html(code_text)

        # Тонкая рамка цветом текста
        border = f'border:1px solid {colors["text"]};' if not is_open \
            else f'border:2px dashed {colors["text"]};'

        bg = colors['alt_base']
        text_dim = f'{colors["text"]}99'
        code_color = '#9370DB'  # medium purple

        # --- Header (язык + кнопка копирования) ---
        header_row = ''
        if lang or code_block_index >= 0:
            header_cells = []
            if lang:
                header_cells.append(
                    f'<span style="font-size:10px;color:{text_dim};'
                    f'font-family:sans-serif;">{self._escape_html(lang)}</span>'
                )
            if code_block_index >= 0:
                encoded = base64.b64encode(code_text.encode('utf-8')).decode('ascii')
                header_cells.append(
                    f'<a href="#copycode:{encoded}" style="font-size:10px;'
                    f'color:{text_dim};text-decoration:none;float:right;">📋</a>'
                )
            header_content = ' &nbsp;·&nbsp; '.join(header_cells)
            header_row = (
                f'<tr><td style="padding:4px 8px;'
                f'border-bottom:1px solid {colors["text"]};'
                f'font-family:sans-serif;">{header_content}</td></tr>'
            )

        # --- Footer (кнопка копирования внизу) ---
        footer_row = ''
        if code_block_index >= 0 and not is_open:
            encoded = base64.b64encode(code_text.encode('utf-8')).decode('ascii')
            footer_row = (
                f'<tr><td style="padding:4px 8px;'
                f'border-top:1px solid {colors["text"]};'
                f'font-family:sans-serif;text-align:left;">'
                f'<a href="#copycode:{encoded}" style="font-size:10px;'
                f'color:{text_dim};text-decoration:none;">Копировать код 📋</a>'
                f'</td></tr>'
            )

        # --- Таблица-обёртка (фон у ячейки с кодом) ---
        return (
            f'<table cellpadding="0" cellspacing="0" '
            f'style="{border}'
            f'margin:8px 0;border-collapse:collapse;width:100%;">'
            f'{header_row}'
            f'<tr><td style="padding:10px;background:{bg};">'
            f'<pre style="margin:0;font-family:Consolas,&quot;Courier New&quot;,monospace;'
            f'font-size:13px;color:{code_color};'
            f'white-space:pre-wrap;word-wrap:break-word;'
            f'line-height:1.4;">{escaped_code}</pre>'
            f'</td></tr>'
            f'{footer_row}'
            f'</table>'
        )

    def render_user_message(self, text):
        colors = self._get_colors()
        escaped = self._escape_html(text)
        return (
            f'<div style="background:{colors["highlight"]}20;'
            f'border-left:3px solid {colors["highlight"]};'
            f'padding:8px 12px;margin:10px 0;">'
            f'<div style="font-weight:bold;color:{colors["link"]};'
            f'margin-bottom:4px;">Вы:</div>'
            f'<div style="white-space:pre-wrap;">{escaped}</div>'
            f'</div>'
        )

    def render_assistant_message(self, markdown_text, msg_index=-1):
        """Парсит Markdown в HTML"""
        colors = self._get_colors()
        lines = markdown_text.split('\n')
        html_parts = []
        i = 0
        paragraph_buffer = []
        code_block_counter = 0

        def flush_paragraph():
            if paragraph_buffer:
                text = ' '.join(paragraph_buffer)
                html_parts.append(
                    f'<p style="margin:0.5em 0;">'
                    f'{self._format_inline(text, colors)}</p>')
                paragraph_buffer.clear()

        in_code_block = False
        code_buffer = []
        code_lang = ""
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            if in_ol:
                html_parts.append('</ol>')
                in_ol = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Блок кода (2-5 символов ` или ~)
            code_fence_match = re.match(r'^([`~]{2,5})(\w*)\s*$', stripped)
            if code_fence_match:
                if not in_code_block:
                    flush_paragraph()
                    close_lists()
                    in_code_block = True
                    code_lang = code_fence_match.group(2)
                    code_buffer = []
                else:
                    in_code_block = False
                    code_text = '\n'.join(code_buffer)
                    html_parts.append(self._render_code_block(
                        code_text, code_lang, colors,
                        is_open=False, msg_index=msg_index,
                        code_block_index=code_block_counter))
                    code_block_counter += 1
                i += 1
                continue

            if in_code_block:
                code_buffer.append(line)
                i += 1
                continue

            # Горизонтальная линия
            if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
                flush_paragraph()
                close_lists()
                html_parts.append(
                    f'<hr style="border:none;'
                    f'border-top:1px solid {colors["text"]}40;'
                    f'margin:12px 0;">')
                i += 1
                continue

            # Заголовки
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                flush_paragraph()
                close_lists()
                level = len(m.group(1))
                html_parts.append(
                    f'<h{level} style="color:{colors["link"]};'
                    f'margin:0.8em 0 0.4em 0;">'
                    f'{self._format_inline(m.group(2), colors)}</h{level}>')
                i += 1
                continue

            # Цитата
            if line.startswith('> '):
                flush_paragraph()
                close_lists()
                html_parts.append(
                    f'<blockquote style="border-left:3px solid '
                    f'{colors["text"]}40;margin:8px 0;padding:4px 12px;'
                    f'color:{colors["text"]}cc;">'
                    f'{self._format_inline(line[2:], colors)}</blockquote>')
                i += 1
                continue

            # Маркированный список
            m = re.match(r'^[\s]*[-*]\s+(.+)$', line)
            if m:
                flush_paragraph()
                if in_ol:
                    html_parts.append('</ol>')
                    in_ol = False
                if not in_ul:
                    html_parts.append(
                        '<ul style="margin:0.5em 0;padding-left:25px;">')
                    in_ul = True
                html_parts.append(
                    f'<li>{self._format_inline(m.group(1), colors)}</li>')
                i += 1
                continue

            # Нумерованный список
            m = re.match(r'^[\s]*(\d+)\.\s+(.+)$', line)
            if m:
                flush_paragraph()
                if in_ul:
                    html_parts.append('</ul>')
                    in_ul = False
                if not in_ol:
                    html_parts.append(
                        '<ol style="margin:0.5em 0;padding-left:25px;">')
                    in_ol = True
                html_parts.append(
                    f'<li>{self._format_inline(m.group(2), colors)}</li>')
                i += 1
                continue

            # Пустая строка
            if not stripped:
                flush_paragraph()
                close_lists()
                i += 1
                continue

            # Обычный текст
            paragraph_buffer.append(stripped)
            i += 1

        # Незакрытый блок кода
        if in_code_block:
            code_text = '\n'.join(code_buffer)
            html_parts.append(self._render_code_block(
                code_text, code_lang, colors,
                is_open=True, msg_index=msg_index,
                code_block_index=code_block_counter))

        flush_paragraph()
        close_lists()

        wrapper_style = (
            f'color:{colors["text"]};'
            f'padding:8px 12px;'
            f'margin:10px 0;'
            f'border-left:3px solid {colors["text"]}40;'
        )
        return f'<div style="{wrapper_style}">{"".join(html_parts)}</div>'

    def render_stats(self, stats, response_text="", msg_index=-1):
        colors = self._get_colors()
        dur = stats.get('duration_sec', 0)
        pt = stats.get('prompt_tokens', 0)
        ct = stats.get('completion_tokens', 0)
        tps = stats.get('tokens_per_sec', 0)
        dur_str = f'{dur:.1f}с' if dur > 0 else '—'
        tps_str = f'{tps:.0f}' if tps > 0 else '—'

        copy_btn = ''
        if response_text and msg_index >= 0:
            copy_btn = (
                f'<a href="#copy:{msg_index}" style="color:{colors["text"]}99;'
                f'text-decoration:none;font-size:10px;padding:0 4px;'
                f'opacity:0.7;"> · 📋 копия</a>'
            )

        return (
            f'<div style="font-size:11px;color:{colors["text"]}99;'
            f'margin-top:6px;padding:4px 8px;'
            f'border-top:1px solid {colors["text"]}20;">'
            f'⏱ {dur_str} · 📥 {pt} ток · 📤 {ct} ток · ⚡ {tps_str} ток/с'
            f'{copy_btn}'
            f'</div>'
        )

    def wrap_document(self, body_html):
        colors = self._get_colors()
        return (
            f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
            f'<style>'
            f'body {{ font-family: sans-serif; line-height: 1.6; '
            f'color: {colors["text"]}; background: transparent; '
            f'margin: 0; padding: 5px; }}'
            f'a {{ color: {colors["link"]}; }}'
            f'</style></head><body>{body_html}</body></html>'
        )

    def get_code_at_cursor(self, cursor: QTextCursor):
        """Возвращает текст блока кода, если курсор внутри него"""
        block = cursor.block()
        font_family = block.charFormat().font().family()
        if font_family not in ('Consolas', 'Courier New', 'Monospace', 'Courier'):
            return None

        code_lines = [block.text()]

        check_block = block.previous()
        while check_block.isValid():
            if check_block.charFormat().font().family() in \
               ('Consolas', 'Courier New', 'Monospace', 'Courier'):
                code_lines.insert(0, check_block.text())
            else:
                break
            check_block = check_block.previous()

        check_block = block.next()
        while check_block.isValid():
            if check_block.charFormat().font().family() in \
               ('Consolas', 'Courier New', 'Monospace', 'Courier'):
                code_lines.append(check_block.text())
            else:
                break
            check_block = check_block.next()

        return '\n'.join(code_lines) if code_lines else None

# ════════════════════════════════════════════════════════════
# FILE: core/ollama_client.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtCore import QThread, pyqtSignal
import requests
import json
import time


class OllamaClient(QThread):
    token_received = pyqtSignal(str)
    generation_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    stats_received = pyqtSignal(dict)

    def __init__(self, url, model, messages, options, timeout=600, stream=True):
        super().__init__()
        self.url = f"{url}/api/chat"
        self.model = model
        self.messages = messages
        self.options = options
        self.timeout = timeout
        self.stream = stream
        self._is_running = True
        self.response = None
        self._start_time = None

    def run(self):
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": self.stream,
            "options": self.options
        }
        self._start_time = time.time()

        try:
            # timeout=(connect_timeout, read_timeout)
            self.response = requests.post(self.url, json=payload,
                                         stream=self.stream,
                                         timeout=(10, self.timeout))
            self.response.raise_for_status()

            if self.stream:
                for line in self.response.iter_lines():
                    if not self._is_running:
                        break

                    # Проверяем общее время
                    elapsed = time.time() - self._start_time
                    if elapsed > self.timeout:
                        self.error_occurred.emit(f"Превышено общее время ожидания ({self.timeout}с)")
                        break

                    if line:
                        try:
                            data = json.loads(line)
                            if 'message' in data and 'content' in data['message']:
                                self.token_received.emit(data['message']['content'])

                            if data.get('done', False):
                                stats = self._extract_stats(data)
                                if stats:
                                    self.stats_received.emit(stats)
                        except json.JSONDecodeError:
                            continue
            else:
                result = self.response.json()
                if 'message' in result and 'content' in result['message']:
                    self.token_received.emit(result['message']['content'])

                stats = self._extract_stats(result)
                if stats:
                    self.stats_received.emit(stats)

        except requests.exceptions.Timeout:
            self.error_occurred.emit(f"Таймаут соединения ({self.timeout}с)")
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if self.response:
                self.response.close()
            self.generation_finished.emit()

    def _extract_stats(self, data):
        try:
            prompt_tokens = data.get('prompt_eval_count', 0)
            completion_tokens = data.get('eval_count', 0)
            total_duration_ns = data.get('total_duration', 0)

            duration_sec = total_duration_ns / 1e9 if total_duration_ns > 0 else 0
            tokens_per_sec = completion_tokens / duration_sec if duration_sec > 0 else 0

            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_sec": duration_sec,
                "tokens_per_sec": tokens_per_sec
            }
        except Exception:
            return None

    def stop(self):
        self._is_running = False
        if self.response:
            self.response.close()

# ════════════════════════════════════════════════════════════
# FILE: core/ollama_manager.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal
import os
import socket
import time


class OllamaManager(QObject):
    """Управляет процессом Ollama-сервера"""

    # Сигналы
    started = pyqtSignal()           # Сервер запущен и готов
    stopped = pyqtSignal()           # Сервер остановлен
    error = pyqtSignal(str)          # Ошибка
    log_line = pyqtSignal(str)       # Строка лога
    needs_install = pyqtSignal()     # Требуется установка Ollama
    conflict_detected = pyqtSignal() # Обнаружен конфликт (Ollama уже запущен)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self._is_our_process = False  # Наш ли это процесс
        self._log_file = None
        self._log_path = None
        self._pid_path = None

    def start(self):
        """Запускает Ollama-сервер"""
        # 1. Проверяем, не запущен ли уже
        if self._is_port_busy():
            # Порт занят — спрашиваем пользователя
            self.conflict_detected.emit()
            return

        # 2. Проверяем наличие бинарника
        ollama_bin = self._get_ollama_binary()
        if not ollama_bin:
            self.needs_install.emit()
            return

        # 3. Запускаем свой процесс
        self._start_process(ollama_bin)

    def use_existing(self):
        """Использует существующий Ollama-сервер (не наш процесс)"""
        self._is_our_process = False
        self.started.emit()

    def kill_existing_and_start(self):
        """Убивает существующий Ollama и запускает свой"""
        import subprocess
        try:
            subprocess.run(["pkill", "-9", "ollama"], timeout=5)
            time.sleep(1)  # Ждём освобождения порта
        except Exception as e:
            self.error.emit(f"Не удалось убить Ollama: {e}")
            return

        # Проверяем, что порт освободился
        if self._is_port_busy():
            self.error.emit("Порт 11434 всё ещё занят")
            return

        # Запускаем свой процесс
        ollama_bin = self._get_ollama_binary()
        if ollama_bin:
            self._start_process(ollama_bin)
        else:
            self.needs_install.emit()

    def stop(self):
        """Останавливает Ollama-сервер (только если это наш процесс)"""
        if not self._is_our_process:
            return  # Не наш процесс — не трогаем

        if self.process:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(1000)

        # Удаляем PID-файл
        if self._pid_path and os.path.exists(self._pid_path):
            try:
                os.remove(self._pid_path)
            except Exception:
                pass

        # Закрываем лог
        self._close_log_file()

        self._is_our_process = False
        self.stopped.emit()

    def is_running(self) -> bool:
        """Проверяет, запущен ли Ollama (по порту)"""
        return self._is_port_busy()

    def is_our_process(self) -> bool:
        """Возвращает True, если это наш процесс"""
        return self._is_our_process

    def _get_ollama_binary(self) -> str:
        """Возвращает путь к бинарнику Ollama"""
        # 1. Локальный бинарник (из конфига)
        local_bin = self.config.get_ollama_binary_path()
        if os.path.exists(local_bin):
            return local_bin
        # 2. Системный путь
        import shutil
        system_bin = shutil.which("ollama")
        if system_bin:
            return system_bin
        return None

    def _start_process(self, ollama_bin: str):
        """Запускает QProcess с ollama serve"""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Открываем файл лога
        log_dir = os.path.join(app_dir, "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._log_path = os.path.join(log_dir, "ollama.log")

        try:
            self._log_file = open(self._log_path, "a", encoding="utf-8")
            self._log_file.write(
                f"\n=== Ollama started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )
            self._log_file.flush()
        except Exception as e:
            print(f"[OllamaManager] Не удалось открыть файл лога: {e}")
            self._log_file = None

        # Создаём PID-файл
        pid_dir = os.path.join(app_dir, "data", "pids")
        os.makedirs(pid_dir, exist_ok=True)
        self._pid_path = os.path.join(pid_dir, "ollama.pid")

        # Запускаем процесс
        self.process = QProcess()
        self.process.setProgram(ollama_bin)
        self.process.setArguments(["serve"])

        # Передаём переменные окружения
        env = QProcessEnvironment.systemEnvironment()
        models_path = self.config.get(
            "ollama/models_path",
            "/run/media/lin/DATA/Program Files/Ollama/"
        )
        env.insert("OLLAMA_MODELS", models_path)
        env.insert("OLLAMA_HOST", "127.0.0.1:11434")
        
        # Данные Ollama (ключи, история) — в data/ollama/
        ollama_data_dir = self.config.get_ollama_data_dir()
        os.makedirs(ollama_data_dir, exist_ok=True)
        env.insert("OLLAMA_DATA_DIR", ollama_data_dir)
        
        # Библиотеки (CUDA, ROCm) — в bin/ollama/lib/ollama/
        lib_dir = self.config.get_ollama_lib_dir()
        if os.path.exists(lib_dir):
            current_ld_path = env.value("LD_LIBRARY_PATH", "")
            if current_ld_path:
                env.insert("LD_LIBRARY_PATH", f"{lib_dir}:{current_ld_path}")
            else:
                env.insert("LD_LIBRARY_PATH", lib_dir)
        self.process.setProcessEnvironment(env)

        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.start()

        # Записываем PID
        pid = self.process.processId()
        try:
            with open(self._pid_path, "w") as f:
                f.write(str(pid))
        except Exception:
            pass

        self._is_our_process = True

        # Ждём готовности
        self._wait_ready()

    def _on_output(self):
        """Обрабатывает вывод процесса"""
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Пишем в лог
            if self._log_file:
                try:
                    self._log_file.write(line + '\n')
                    self._log_file.flush()
                except Exception:
                    pass

            # Эмитим сигнал
            self.log_line.emit(line)

    def _on_finished(self, exit_code, exit_status):
        """Процесс завершён"""
        self._close_log_file()

        if exit_code != 0 and exit_code != 15:  # 15 = SIGTERM
            self.error.emit(f"Ollama завершился с кодом {exit_code}")

        self._is_our_process = False
        self.stopped.emit()

    def _on_process_error(self, error):
        """Ошибка запуска процесса"""
        self.error.emit(f"Ошибка запуска Ollama: {error}")

    def _close_log_file(self):
        """Закрывает файл лога"""
        if self._log_file:
            try:
                self._log_file.write(
                    f"\n=== Ollama stopped at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _is_port_busy(self) -> bool:
        """Проверяет, занят ли порт 11434"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 11434))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _wait_ready(self, timeout=30):
        """Ждёт, пока Ollama станет доступен"""
        start = time.time()
        while time.time() - start < timeout:
            if self._is_port_busy():
                # Записываем PID (на случай, если процесс ещё не записал)
                if self.process:
                    pid = self.process.processId()
                    try:
                        with open(self._pid_path, "w") as f:
                            f.write(str(pid))
                    except Exception:
                        pass
                self.started.emit()
                return
            time.sleep(0.5)
        self.error.emit("Ollama не запустился за 30 секунд")

# ════════════════════════════════════════════════════════════
# FILE: core/path_validator.py
# ════════════════════════════════════════════════════════════

import os
import subprocess
import requests

class PathValidator:
    def validate_venv(self, path: str) -> dict:
        """Проверка venv"""
        if not path:
            return {"valid": False, "error": "Путь не указан"}

        if not os.path.exists(path):
            return {"valid": False, "error": "Папка не существует"}

        python_path = os.path.join(path, "bin", "python")
        if not os.path.exists(python_path):
            return {"valid": False, "error": "bin/python не найден"}

        # Проверяем запуск Python
        try:
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return {"valid": True, "error": ""}
            else:
                return {"valid": False, "error": f"Python вернул ошибку: {result.stderr}"}
        except subprocess.TimeoutExpired:
            return {"valid": False, "error": "Таймаут при запуске Python"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_models_path(self, path: str) -> dict:
        """Проверка папки моделей"""
        if not path:
            return {"valid": False, "error": "Путь не указан", "count": 0}
        if not os.path.exists(path):
            return {"valid": False, "error": "Папка не существует", "count": 0}
        if not os.path.isdir(path):
            return {"valid": False, "error": "Это не папка", "count": 0}

        models_count = 0

        for item in os.listdir(path):
            item_path = os.path.join(path, item)

            # 1. Одиночные файлы
            if os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    models_count += 1

            # 2. HF cache папки (models--org--model-name)
            elif os.path.isdir(item_path) and item.startswith("models--"):
                models_count += 1

            # 3. Распакованные модели (папки с model_index.json)
            elif os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    models_count += 1

        if models_count == 0:
            return {"valid": False, "error": "Модели не найдены", "count": 0}

        return {"valid": True, "error": "", "count": models_count}

    def validate_output_dir(self, path: str) -> dict:
        """Проверка папки сохранения"""
        if not path:
            return {"valid": False, "error": "Путь не указан"}

        # Пытаемся создать если не существует
        try:
            os.makedirs(path, exist_ok=True)

            # Проверяем права на запись
            test_file = os.path.join(path, ".test_write")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)

            return {"valid": True, "error": ""}
        except PermissionError:
            return {"valid": False, "error": "Нет прав на запись"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_ollama_url(self, url: str) -> dict:
        """Проверка Ollama"""
        if not url:
            return {"valid": False, "error": "URL не указан", "models_count": 0}

        try:
            res = requests.get(f"{url}/api/tags", timeout=5)
            if res.status_code == 200:
                models = res.json().get('models', [])
                return {"valid": True, "error": "", "models_count": len(models)}
            else:
                return {"valid": False, "error": f"HTTP {res.status_code}", "models_count": 0}
        except requests.exceptions.ConnectionError:
            return {"valid": False, "error": "Не удалось подключиться", "models_count": 0}
        except requests.exceptions.Timeout:
            return {"valid": False, "error": "Таймаут соединения", "models_count": 0}
        except Exception as e:
            return {"valid": False, "error": str(e), "models_count": 0}

    def validate_all(self, config) -> dict:
        """Проверка всех путей"""
        result = {
            "venv": self.validate_venv(config.get_sdxl_venv_path()),
            "models": self.validate_models_path(config.get_sdxl_models_path()),
            "output": self.validate_output_dir(config.get_sdxl_output_dir()),
            "ollama": self.validate_ollama_url(config.get_ollama_url())
        }

        # Проверяем, все ли критичные пути валидны
        result["all_valid"] = (
            result["venv"]["valid"] and
            result["models"]["valid"] and
            result["output"]["valid"] and
            result["ollama"]["valid"]
        )

        return result

# ════════════════════════════════════════════════════════════
# FILE: core/resource_manager.py
# ════════════════════════════════════════════════════════════

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

# ════════════════════════════════════════════════════════════
# FILE: core/resource_monitor.py
# ════════════════════════════════════════════════════════════

"""
Монитор ресурсов и применение ограничений.
Используется перед запуском генерации для проверки доступных ресурсов
и применения лимитов CPU/RAM к процессам.
"""
import os
import psutil


class ResourceMonitor:
    """Мониторинг и управление ресурсами системы"""
    
    def __init__(self, config):
        self.config = config
    
    def get_limits(self) -> dict:
        """Возвращает текущие лимиты из конфига"""
        return {
            "max_ram_percent": int(self.config.get("resources/max_ram_percent", 80)),
            "cpu_cores": int(self.config.get("resources/cpu_cores", 3)),
            "cpu_priority": int(self.config.get("resources/cpu_priority", 0))
        }
    
    def get_system_info(self) -> dict:
        """Возвращает информацию о системе"""
        mem = psutil.virtual_memory()
        return {
            "ram_total_gb": mem.total / (1024**3),
            "ram_available_gb": mem.available / (1024**3),
            "ram_used_gb": mem.used / (1024**3),
            "ram_percent": mem.percent,
            "cpu_count": os.cpu_count() or 4,
            "cpu_percent": psutil.cpu_percent(interval=0.1)
        }
    
    def check_ram_available(self, required_gb: float) -> dict:
        """
        Проверяет, достаточно ли RAM для задачи.
        Args:
            required_gb: требуемая память в GB
        Returns:
            dict: {"ok": bool, "available_gb": float, "required_gb": float, "message": str}
        """
        limits = self.get_limits()
        sys_info = self.get_system_info()
        
        # Максимум RAM, который может использовать приложение
        max_ram_gb = sys_info["ram_total_gb"] * limits["max_ram_percent"] / 100
        
        # Уже занято приложением (примерно)
        current_process = psutil.Process()
        app_used_gb = current_process.memory_info().rss / (1024**3)
        
        # Свободно для новой задачи
        available_for_task = max_ram_gb - app_used_gb
        
        if required_gb > available_for_task:
            return {
                "ok": False,
                "available_gb": available_for_task,
                "required_gb": required_gb,
                "message": (
                    f"Недостаточно RAM. "
                    f"Требуется: {required_gb:.1f} GB, "
                    f"доступно: {available_for_task:.1f} GB "
                    f"(лимит {limits['max_ram_percent']}% от {sys_info['ram_total_gb']:.1f} GB)"
                )
            }
        
        return {
            "ok": True,
            "available_gb": available_for_task,
            "required_gb": required_gb,
            "message": f"Достаточно RAM: {available_for_task:.1f} GB"
        }
    
    def estimate_diffusers_ram(self, width: int, height: int, model: str) -> float:
        """
        Оценивает требуемую RAM для Diffusers.
        SDXL: ~6-8 GB для 1024x1024
        SD 1.5: ~4 GB для 512x512
        """
        # Базовая оценка по размеру изображения
        pixels = width * height
        base_gb = 4.0  # базовое потребление
        
        # SDXL требует больше
        if "xl" in model.lower() or pixels > 512*512:
            base_gb = 6.0
        
        # Масштабирование по размеру
        if pixels > 1024*1024:
            base_gb *= 1.3
        elif pixels < 512*512:
            base_gb *= 0.7
        
        return base_gb
    
    def estimate_ollama_ram(self, model: str) -> float:
        """
        Оценивает требуемую RAM для Ollama модели.
        Примерные размеры:
        - 3B параметров: ~2 GB
        - 7B параметров: ~4-5 GB
        - 13B параметров: ~8 GB
        """
        model_lower = model.lower()
        
        if "3b" in model_lower or "1.5b" in model_lower:
            return 2.0
        elif "7b" in model_lower or "8b" in model_lower:
            return 5.0
        elif "13b" in model_lower:
            return 8.0
        elif "70b" in model_lower:
            return 40.0
        else:
            # По умолчанию — средняя модель
            return 4.0
    
    @staticmethod
    def apply_cpu_affinity(pid: int, cores: int):
        """Привязывает процесс к указанным ядрам CPU"""
        try:
            process = psutil.Process(pid)
            available_cores = list(range(os.cpu_count() or 4))
            # Берём первые N ядер
            affinity = available_cores[:cores]
            process.cpu_affinity(affinity)
            return True
        except Exception as e:
            print(f"[ResourceMonitor] Не удалось установить affinity: {e}")
            return False
    
    @staticmethod
    def apply_priority(pid: int, priority: int):
        """Устанавливает приоритет процесса (nice)"""
        try:
            process = psutil.Process(pid)
            process.nice(priority)
            return True
        except Exception as e:
            print(f"[ResourceMonitor] Не удалось установить priority: {e}")
            return False
    
    @staticmethod
    def get_env_for_cpu_limits(cores: int) -> dict:
        """Возвращает переменные окружения для ограничения CPU"""
        return {
            "OMP_NUM_THREADS": str(cores),
            "OPENBLAS_NUM_THREADS": str(cores),
            "MKL_NUM_THREADS": str(cores),
            "VECLIB_MAXIMUM_THREADS": str(cores),
            "NUMEXPR_NUM_THREADS": str(cores)
        }

# ════════════════════════════════════════════════════════════
# FILE: main.py
# ════════════════════════════════════════════════════════════

import sys
from PyQt6.QtWidgets import QApplication, QStyleFactory, QMessageBox
from ui.main_window import MainWindow
from ui.dialogs.paths_dialog import PathsDialog
from ui.dialogs.settings.settings_dialog import SettingsDialog
from utils.config import Config
from core.path_validator import PathValidator

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Применение системного стиля (если доступен)
    system_styles = ["Breeze", "Adwaita", "Fusion"]
    for style_name in system_styles:
        if style_name in QStyleFactory.keys():
            app.setStyle(QStyleFactory.create(style_name))
            break
    
    # Создаём конфиг
    config = Config()
    
    # Проверяем пути при старте
    validator = PathValidator()
    result = validator.validate_all(config)
    
    window = MainWindow()
    
    # Если пути не настроены, показываем диалог настроек
    if not result["all_valid"]:
        dialog = SettingsDialog(config, window)
        dialog.tabs.setCurrentIndex(0)  # Открываем на вкладке "Общие"
        if not dialog.exec():
            QMessageBox.warning(
                window,
                "Настройка путей",
                "Настройка путей отменена.\n"
                "Некоторые функции будут недоступны.\n\n"
                "Вы можете настроить пути позже через меню Настройки → Настройки..."
            )
    
    window.show()
    sys.exit(app.exec())

# ════════════════════════════════════════════════════════════
# FILE: scripts/generate_diffusers.py
# ════════════════════════════════════════════════════════════

#!/usr/bin/env python3
import argparse
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
import numpy as np
from PIL import Image
from diffusers import (
    StableDiffusionXLPipeline,
    EulerDiscreteScheduler,
    EulerAncestralDiscreteScheduler,
    DPMSolverMultistepScheduler,
    DDIMScheduler,
    PNDMScheduler
)
from core import checkpoint_manager


def emit(msg):
    """Выводит JSON-сообщение в stdout + plain text для лога"""
    print(json.dumps(msg, ensure_ascii=False), flush=True)

    # Дополнительный plain text вывод для лога
    msg_type = msg.get("type")
    if msg_type == "step":
        step = msg.get("step", 0)
        total = msg.get("total_steps", 0)
        print(f"[STEP] {step}/{total}", flush=True)
    elif msg_type == "status":
        message = msg.get("message", "")
        print(f"[STATUS] {message}", flush=True)
    elif msg_type == "done":
        final_path = msg.get("final_path", "")
        print(f"[DONE] {final_path}", flush=True)
    elif msg_type == "error":
        message = msg.get("message", "")
        print(f"[ERROR] {message}", flush=True)
    elif msg_type == "warning":
        message = msg.get("message", "")
        print(f"[WARNING] {message}", flush=True)


def decode_and_save(pipe, latents, step, output_dir, seed, preview_dir):
    """
    Декодирует latents через VAE, сохраняет PNG в preview_dir,
    возвращает путь.
    preview_dir передаётся из CLI — без импорта PyQt6.
    """
    try:
        os.makedirs(preview_dir, exist_ok=True)

        with torch.no_grad():
            latents_scaled = latents / pipe.vae.config.scaling_factor
            decoded = pipe.vae.decode(latents_scaled, return_dict=False)[0]

        images = (decoded / 2 + 0.5).clamp(0, 1)
        images = images.cpu().permute(0, 2, 3, 1).numpy()
        image_np = (images[0] * 255).astype(np.uint8)

        filename = f"sdxl_{seed}_step{step:04d}.png"
        path = os.path.join(preview_dir, filename)
        Image.fromarray(image_np).save(path)
        return path
    except Exception as e:
        emit({"type": "warning", "message": f"Не удалось сохранить превью шага {step}: {e}"})
        return ""


def main():
    last_preview_path = ""  # НОВОЕ: трекер последнего превью
    
    parser = argparse.ArgumentParser(description="SDXL Image Generator")
    parser.add_argument("--prompt", required=True, help="Positive prompt")
    parser.add_argument("--negative", default="", help="Negative prompt")
    parser.add_argument("--model", required=True, help="Model name or path")
    parser.add_argument("--scheduler", default="EulerDiscreteScheduler")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg", type=float, default=7.5)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    parser.add_argument("--preview-every", type=int, default=0,
                        help="Сохранять превью каждые N шагов (0 = выключено)")
    parser.add_argument("--preview-start", type=int, default=1,
                        help="Начинать сохранение превью с этого шага")
    parser.add_argument("--no-safety-checker", action="store_true", help="Disable NSFW filter")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument("--preview-dir", default=None,
                        help="Папка для превью (технические файлы)")
    parser.add_argument("--cache_dir", default=None, help="Cache directory for models")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--checkpoint-file", default=None,
                        help="Имя файла архивного чекпоинта (для resume из архива)")
    args = parser.parse_args()

    print(f"[INFO] Script started. Args: {vars(args)}", flush=True)

    # Режим Resume
    if args.resume:
        print(f"[INFO] Resume mode enabled", flush=True)
        if args.checkpoint_file:
            print(f"[INFO] Loading archived checkpoint: {args.checkpoint_file}", flush=True)
            emit({"type": "status", "message": f"Загрузка архивного чекпоинта: {args.checkpoint_file}..."})
            json_data, torch_data = checkpoint_manager.load_archived_checkpoint(args.checkpoint_file)
        else:
            print(f"[INFO] Loading active checkpoint", flush=True)
            if not checkpoint_manager.checkpoint_exists():
                emit({"type": "error", "message": "Чекпоинт не найден"})
                sys.exit(1)
            emit({"type": "status", "message": "Загрузка чекпоинта..."})
            json_data, torch_data = checkpoint_manager.load_checkpoint()

        if not json_data or not torch_data:
            emit({"type": "error", "message": "Не удалось загрузить чекпоинт"})
            sys.exit(1)

        print(f"[INFO] Checkpoint loaded successfully", flush=True)

        # Восстанавливаем параметры из чекпоинта
        args.prompt = json_data["prompt"]
        args.negative = json_data.get("negative_prompt", "")
        args.model = json_data["model"]
        args.scheduler = json_data["scheduler"]
        args.steps = json_data["total_steps"]
        args.cfg = json_data["cfg"]
        args.width = json_data["width"]
        args.height = json_data["height"]
        args.seed = json_data["seed"]
        args.device = json_data["device"]
        args.preview_every = json_data.get("preview_every", 0)
        args.preview_start = json_data.get("preview_start", 1)

        current_step = json_data["current_step"]
        resume_start_step = current_step  # НОВОЕ: запоминаем базу
        remaining_timesteps = json_data["remaining_timesteps"]

        latents = torch_data["latents"].to(args.device)
        scheduler_state = torch_data["scheduler_state"]
        generator_state = torch_data["generator_state"]

        emit({"type": "status", "message": f"Продолжение с шага {current_step}/{args.steps}..."})
    else:
        current_step = 0
        resume_start_step = 0  # НОВОЕ: база для callback
        remaining_timesteps = None
        latents = None
        scheduler_state = None
        generator_state = None

    # Генерация seed
    if args.seed == -1:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()
    else:
        seed = args.seed

    generator = torch.Generator(device=args.device).manual_seed(seed)

    if args.resume and generator_state is not None:
        generator.set_state(generator_state)

    # Загрузка модели
    try:
        emit({"type": "status", "message": "Загрузка модели..."})
        print(f"[INFO] Loading model: {args.model}", flush=True)
        dtype = torch.float16 if args.device == "cuda" else torch.float32

        if os.path.isfile(args.model) and (args.model.endswith('.safetensors') or args.model.endswith('.ckpt')):
            emit({"type": "status", "message": "Загрузка одиночного файла модели..."})
            print(f"[INFO] Single file model detected", flush=True)
            pipe = StableDiffusionXLPipeline.from_single_file(
                args.model,
                torch_dtype=dtype,
                use_safetensors=args.model.endswith('.safetensors')
            )
        else:
            print(f"[INFO] HF model or folder: {args.model}", flush=True)
            pipe = StableDiffusionXLPipeline.from_pretrained(
                args.model,
                torch_dtype=dtype,
                cache_dir=args.cache_dir,
                use_safetensors=True
            )

        print(f"[INFO] Moving model to device: {args.device}", flush=True)
        pipe.to(args.device)

        if args.no_safety_checker:
            try:
                pipe.safety_checker = None
                emit({"type": "status", "message": "Safety Checker отключён"})
                print(f"[INFO] Safety Checker disabled", flush=True)
            except AttributeError:
                pass

        # Настройка scheduler
        scheduler_map = {
            "EulerDiscreteScheduler": EulerDiscreteScheduler,
            "EulerAncestralDiscreteScheduler": EulerAncestralDiscreteScheduler,
            "DPMSolverMultistepScheduler": DPMSolverMultistepScheduler,
            "DDIMScheduler": DDIMScheduler,
            "PNDMScheduler": PNDMScheduler
        }

        if args.scheduler in scheduler_map:
            pipe.scheduler = scheduler_map[args.scheduler].from_config(pipe.scheduler.config)
            print(f"[INFO] Scheduler set to: {args.scheduler}", flush=True)

        if args.resume and scheduler_state is not None:
            pipe.scheduler.__dict__.update(scheduler_state)
            print(f"[INFO] Scheduler state restored", flush=True)

    except Exception as e:
        print(f"[ERROR] Model loading failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        emit({"type": "error", "message": f"Ошибка загрузки модели: {str(e)}"})
        sys.exit(1)

    # Callback для прогресса и чекпоинтов
    def callback_fn(step, timestep, latents):
        nonlocal current_step, last_preview_path
        current_step = resume_start_step + step + 1  # ИСПРАВЛЕНО: с учётом базы

        print(f"[STEP] {current_step}/{args.steps}", flush=True)

        msg = {
            "type": "step",
            "step": current_step,
            "total_steps": args.steps,
            "image_path": ""
        }

        if (args.preview_every > 0
                and current_step >= args.preview_start
                and (current_step - args.preview_start) % args.preview_every == 0):
            preview_path = decode_and_save(pipe, latents, current_step, args.output_dir, args.seed, args.preview_dir)
            msg["image_path"] = preview_path

            if current_step < args.steps:
                try:
                    remaining = pipe.scheduler.timesteps[step + 1:].tolist()
                    params = {
                        "prompt": args.prompt,
                        "negative_prompt": args.negative,
                        "model": args.model,
                        "scheduler": args.scheduler,
                        "seed": args.seed,
                        "total_steps": args.steps,
                        "width": args.width,
                        "height": args.height,
                        "cfg": args.cfg,
                        "device": args.device,
                        "preview_every": args.preview_every,
                        "preview_start": args.preview_start
                    }
                    checkpoint_manager.save_checkpoint(
                        latents=latents,
                        scheduler=pipe.scheduler,
                        generator=generator,
                        params=params,
                        current_step=current_step,
                        remaining_timesteps=remaining,
                        actual_seed=seed  # ИСПРАВЛЕНО: передаём реальный seed
                    )
                    emit({"type": "status", "message": f"💾 Чекпоинт сохранён (шаг {current_step}/{args.steps})"})
                except Exception as e:
                    emit({"type": "warning", "message": f"Не удалось сохранить чекпоинт: {e}"})

        emit(msg)

    # Генерация
    try:
        emit({"type": "status", "message": "Генерация..."})
        print(f"[INFO] Starting generation: {args.width}x{args.height}, seed={args.seed}, steps={args.steps}", flush=True)

        if args.resume:
            image = pipe(
                prompt=args.prompt,
                negative_prompt=args.negative if args.negative else None,
                width=args.width,
                height=args.height,
                num_inference_steps=args.steps,
                guidance_scale=args.cfg,
                generator=generator,
                latents=latents,
                timesteps=remaining_timesteps,
                callback=callback_fn,
                callback_steps=1
            ).images[0]
        else:
            image = pipe(
                prompt=args.prompt,
                negative_prompt=args.negative if args.negative else None,
                width=args.width,
                height=args.height,
                num_inference_steps=args.steps,
                guidance_scale=args.cfg,
                generator=generator,
                callback=callback_fn,
                callback_steps=1
            ).images[0]

    except Exception as e:
        print(f"[ERROR] Generation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        emit({"type": "error", "message": f"Ошибка генерации: {str(e)}"})
        sys.exit(1)

    # Удаление активного чекпоинта после успешного завершения
    if checkpoint_manager.checkpoint_exists():
        checkpoint_manager.delete_checkpoint()

    # Сохранение финальной картинки
    try:
        os.makedirs(args.output_dir, exist_ok=True)
        filename = f"sdxl_{seed}.png"
        output_path = os.path.join(args.output_dir, filename)
        image.save(output_path)

        emit({
            "type": "done",
            "final_path": output_path,
            "seed": args.seed
        })
        print(f"[INFO] Generation completed successfully", flush=True)
    except Exception as e:
        print(f"[ERROR] Save failed: {e}", flush=True)
        emit({"type": "error", "message": f"Ошибка сохранения: {str(e)}"})
        sys.exit(1)


if __name__ == "__main__":
    main()

# ════════════════════════════════════════════════════════════
# FILE: ui/chat_widget.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextBrowser, QApplication, QMenu)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor
from core.markdown_parser import MarkdownParser

class ChatWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Единый QTextBrowser для всей истории + стриминга
        self.chat_browser = QTextBrowser()
        self.chat_browser.anchorClicked.connect(self._on_anchor_clicked)
        self._message_responses = []  # Храним тексты ответов для копирования
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_browser.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.chat_browser, 1)
        
        # Парсер и буферы
        self.parser = MarkdownParser()
        self._history_html = []          # Список отрендеренных сообщений [(role, html), ...]
        self._current_buffer = ""        # Буфер текущего ответа (plain markdown)
        self._current_role = None        # "user" или "assistant"
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._render_current)
    
    def append_user_message(self, text):
        """Добавляет сообщение пользователя в историю"""
        html = self.parser.render_user_message(text)
        self._history_html.append(("user", html))
        self._rerender_all()
    
    def start_assistant_message(self):
        """Начинает стриминг нового ответа"""
        self._current_buffer = ""
        self._current_role = "assistant"
    
    def append_token(self, token):
        """Добавляет токен в буфер текущего ответа"""
        self._current_buffer += token
        if not self._update_timer.isActive():
            self._update_timer.start(200)
    
    def _render_current(self):
        """Рендерит текущий буфер и обновляет браузер"""
        if not self._current_buffer:
            return
        current_html = self.parser.render_assistant_message(self._current_buffer)
        self._rerender_all(current_html_override=current_html)
    
    def finalize_response(self, stats_dict):
        self._update_timer.stop()
        msg_index = len(self._message_responses)
        self._message_responses.append(self._current_buffer)
        
        html = self.parser.render_assistant_message(self._current_buffer, msg_index)
        if stats_dict and (stats_dict.get('completion_tokens', 0) > 0
                           or stats_dict.get('duration_sec', 0) > 0):
            html += self.parser.render_stats(stats_dict, self._current_buffer, msg_index)
        
        self._history_html.append(("assistant", html))
        self._current_buffer = ""
        self._current_role = None
        self._rerender_all()
    
    def _on_anchor_clicked(self, url):
        """Обработка клика по якорю (копирование)"""
        anchor = url.toString()
        
        # Копирование ответа по индексу
        if anchor.startswith('#copy:'):
            try:
                msg_index = int(anchor.split(':')[1])
                if 0 <= msg_index < len(self._message_responses):
                    QApplication.clipboard().setText(self._message_responses[msg_index])
            except (ValueError, IndexError):
                pass
        
        # Копирование блока кода (текст в base64)
        elif anchor.startswith('#copycode:'):
            try:
                encoded = anchor.split(':', 1)[1]
                import base64
                code_text = base64.b64decode(encoded).decode('utf-8')
                QApplication.clipboard().setText(code_text)
            except Exception:
                pass
    
    def _rerender_all(self, current_html_override=None):
        """Перерисовывает весь чат: история + текущий ответ"""
        parts = []
        for role, html in self._history_html:
            parts.append(html)
        
        if current_html_override:
            parts.append(current_html_override)
        elif self._current_buffer:
            parts.append(self.parser.render_assistant_message(self._current_buffer))
        
        full_html = self.parser.wrap_document('\n'.join(parts))
        self.chat_browser.setHtml(full_html)
        
        # Скролл вниз
        sb = self.chat_browser.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def _show_context_menu(self, pos):
        """Контекстное меню с копированием кода"""
        menu = QMenu(self)
        cursor = self.chat_browser.cursorForPosition(pos)
        
        # Проверяем, находится ли курсор в блоке кода
        code_text = self.parser.get_code_at_cursor(cursor)
        
        if code_text is not None:
            copy_code = menu.addAction("Копировать код")
            menu.addSeparator()
            copy_all = menu.addAction("Копировать всё")
            
            action = menu.exec(self.chat_browser.mapToGlobal(pos))
            if action == copy_code:
                QApplication.clipboard().setText(code_text)
            elif action == copy_all:
                self.chat_browser.selectAll()
                self.chat_browser.copy()
                self.chat_browser.textCursor().clearSelection()
        else:
            menu.addAction("Копировать", self.chat_browser.copy)
            menu.addSeparator()
            menu.addAction("Копировать всё", lambda: (
                self.chat_browser.selectAll(),
                self.chat_browser.copy(),
                self.chat_browser.textCursor().clearSelection()
            ))
            menu.exec(self.chat_browser.mapToGlobal(pos))
    
    def clear_chat(self):
        self.chat_browser.clear()
        self._history_html = []
        self._current_buffer = ""
        self._current_role = None
        self._message_responses = []
        self._update_timer.stop()

# ════════════════════════════════════════════════════════════
# FILE: ui/cleanup_dialog.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar,
                             QPushButton, QApplication)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtCore import QProcess


class CleanupThread(QThread):
    """Поток для выполнения очистки ресурсов"""
    step_started = pyqtSignal(str)         # название шага
    step_finished = pyqtSignal(bool, str)  # успех, сообщение
    all_done = pyqtSignal()                # всё завершено

    def __init__(self, ollama_tab, diffusers_tab, config, ollama_manager):
        super().__init__()
        self.ollama_tab = ollama_tab
        self.diffusers_tab = diffusers_tab
        self.config = config
        self.ollama_manager = ollama_manager

    def run(self):
        """Выполняет все шаги очистки"""
        # === Шаг 1: Остановка DiffusersWorker ===
        self.step_started.emit("Остановка Diffusers...")
        try:
            if self.diffusers_tab.worker:
                if self.diffusers_tab.worker.process:
                    state = self.diffusers_tab.worker.process.state()
                    if state == QProcess.ProcessState.Running:
                        self.diffusers_tab.worker.process.terminate()
                        if not self.diffusers_tab.worker.process.waitForFinished(2000):
                            self.diffusers_tab.worker.process.kill()
                            self.diffusers_tab.worker.process.waitForFinished(1000)
                # Закрываем файл лога
                self.diffusers_tab.worker._close_log_file()
                self.diffusers_tab.worker = None
                self.step_finished.emit(True, "Diffusers остановлен")
            else:
                self.step_finished.emit(True, "Diffusers не запущен")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 2: Выгрузка модели Ollama (через API) ===
        self.step_started.emit("Выгрузка модели Ollama...")
        try:
            # Останавливаем клиент, если работает
            if self.ollama_tab.client and self.ollama_tab.client.isRunning():
                self.ollama_tab.client.stop()
                if not self.ollama_tab.client.wait(1000):
                    self.ollama_tab.client.terminate()
                    self.ollama_tab.client.wait(500)

            # Выгружаем модель из Ollama (keep_alive=0)
            import requests
            model = self.ollama_tab.settings_panel.model_combo.currentText()
            if model:
                requests.post(
                    f"{self.config.get_ollama_url()}/api/generate",
                    json={"model": model, "keep_alive": 0},
                    timeout=2
                )

            # Проверяем, что модель выгружена
            res = requests.get(f"{self.config.get_ollama_url()}/api/ps", timeout=2)
            if res.status_code == 200:
                running_models = res.json().get('models', [])
                if len(running_models) == 0:
                    self.step_finished.emit(True, "Ollama: модель выгружена")
                else:
                    self.step_finished.emit(
                        True,
                        f"Ollama: моделей в памяти — {len(running_models)}"
                    )
            else:
                self.step_finished.emit(True, "Ollama: модель выгружена")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 3: Остановка Ollama-сервера (только если наш процесс) ===
        self.step_started.emit("Остановка Ollama-сервера...")
        try:
            if self.ollama_manager and self.ollama_manager.is_our_process():
                self.ollama_manager.stop()
                self.step_finished.emit(True, "Ollama-сервер остановлен")
            else:
                self.step_finished.emit(True, "Ollama-сервер: внешний (не трогаем)")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 4: Очистка памяти ===
        self.step_started.emit("Очистка памяти...")
        try:
            import gc
            gc.collect()

            try:
                import psutil
                mem = psutil.virtual_memory()
                available_gb = mem.available / (1024**3)
                self.step_finished.emit(
                    True,
                    f"Освобождено. Доступно: {available_gb:.1f} GB"
                )
            except ImportError:
                self.step_finished.emit(True, "Память очищена")
        except Exception as e:
            self.step_finished.emit(False, f"Ошибка: {str(e)}")
        self.msleep(300)

        # === Шаг 5: Завершение ===
        self.step_started.emit("Завершение...")
        self.step_finished.emit(True, "Готово")
        self.all_done.emit()


class CleanupDialog(QDialog):
    """Диалог очистки ресурсов при закрытии"""
    def __init__(self, ollama_tab, diffusers_tab, config, ollama_manager, parent=None):
        super().__init__(parent)
        self.ollama_tab = ollama_tab
        self.diffusers_tab = diffusers_tab
        self.config = config
        self.ollama_manager = ollama_manager

        self.setWindowTitle("Закрытие приложения")
        self.setFixedSize(400, 240)

        layout = QVBoxLayout(self)

        # Заголовок
        self.title_label = QLabel("Освобождение ресурсов...")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Прогресс-бар (5 шагов)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 5)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m")
        layout.addWidget(self.progress_bar)

        # Статус текущего шага
        self.status_label = QLabel("Подготовка...")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Список выполненных шагов
        self.steps_label = QLabel("")
        self.steps_label.setStyleSheet("font-size: 11px;")
        self.steps_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.steps_label)

        layout.addStretch()

        # Создаём поток очистки
        self.cleanup_thread = CleanupThread(
            ollama_tab, diffusers_tab, config, ollama_manager
        )
        self.cleanup_thread.step_started.connect(self._on_step_started)
        self.cleanup_thread.step_finished.connect(self._on_step_finished)
        self.cleanup_thread.all_done.connect(self._on_all_done)

        # Запускаем поток
        self.cleanup_thread.start()
        self._completed_steps = []

    def _on_step_started(self, step_name):
        """Начало шага"""
        self.status_label.setText(step_name)
        self.status_label.setStyleSheet("color: blue; font-size: 12px;")

    def _on_step_finished(self, success, message):
        """Шаг завершён"""
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        icon = "✅" if success else "❌"
        self._completed_steps.append(f"{icon} {message}")
        self.steps_label.setText("\n".join(self._completed_steps))

        if success:
            self.status_label.setStyleSheet("color: green; font-size: 12px;")
        else:
            self.status_label.setStyleSheet("color: red; font-size: 12px;")

    def _on_all_done(self):
        """Все шаги завершены"""
        self.title_label.setText("Завершено")
        self.status_label.setText("Все ресурсы освобождены")
        self.status_label.setStyleSheet(
            "color: green; font-size: 12px; font-weight: bold;"
        )
        # Автоматически закрываем через 1 секунду
        QTimer.singleShot(1000, self.accept)

    def closeEvent(self, event):
        """Блокируем закрытие диалога до завершения"""
        if self.cleanup_thread.isRunning():
            event.ignore()
        else:
            event.accept()

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/diffusers_models_dialog.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QPushButton, QListWidget,
                              QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
import os
import shutil
import subprocess


class DiffusersModelsDialog(QDialog):
    """Диалог управления моделями Diffusers"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.models_path = config.get_sdxl_models_path()

        self.setWindowTitle("Управление моделями Diffusers")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)

        # Группа ссылок на ресурсы
        links_group = QGroupBox("Где найти модели")
        links_layout = QVBoxLayout()

        links = [
            ("🌐 HuggingFace Diffusers", "https://huggingface.co/models?pipeline_tag=text-to-image&sort=downloads"),
            ("🎨 CivitAI (SDXL модели)", "https://civitai.com/model-versions?baseModel=SDXL%201.0"),
            ("📦 HuggingFace SDXL Base", "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0"),
            ("📦 HuggingFace SDXL Refiner", "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0")
        ]

        for text, url in links:
            link_btn = QPushButton(text)
            link_btn.setStyleSheet("text-align: left; padding: 5px;")
            link_btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_layout.addWidget(link_btn)

        links_group.setLayout(links_layout)
        layout.addWidget(links_group)

        # Группа списка моделей
        models_group = QGroupBox("Установленные модели")
        models_layout = QVBoxLayout()

        # Список моделей
        self.models_list = QListWidget()
        self.models_list.itemSelectionChanged.connect(self._on_model_selected)
        models_layout.addWidget(self.models_list, 1)

        # Кнопки управления
        buttons_layout = QHBoxLayout()

        self.open_folder_btn = QPushButton("📂 Открыть папку")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        buttons_layout.addWidget(self.open_folder_btn)

        self.delete_btn = QPushButton("🗑 Удалить")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        buttons_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self._load_models)
        buttons_layout.addWidget(self.refresh_btn)

        models_layout.addLayout(buttons_layout)

        models_group.setLayout(models_layout)
        layout.addWidget(models_group)

        # Загружаем список моделей
        self._load_models()

    def _load_models(self):
        """Загружает список установленных моделей"""
        self.models_list.clear()

        if not self.models_path or not os.path.exists(self.models_path):
            return

        for item in os.listdir(self.models_path):
            item_path = os.path.join(self.models_path, item)

            # HF cache формат
            if os.path.isdir(item_path) and item.startswith("models--"):
                model_id = item[len("models--"):].replace("--", "/")
                list_item = QListWidgetItem(f"📦 {model_id}")
                list_item.setData(Qt.ItemDataRole.UserRole, item_path)
                self.models_list.addItem(list_item)

            # Одиночные файлы
            elif os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    name = os.path.splitext(item)[0]
                    list_item = QListWidgetItem(f"📄 {name}")
                    list_item.setData(Qt.ItemDataRole.UserRole, item_path)
                    self.models_list.addItem(list_item)

            # Распакованные модели
            elif os.path.isdir(item_path) and not item.startswith("models--"):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    list_item = QListWidgetItem(f"📁 {item}")
                    list_item.setData(Qt.ItemDataRole.UserRole, item_path)
                    self.models_list.addItem(list_item)

    def _on_model_selected(self):
        """Обновляет доступность кнопки удаления"""
        self.delete_btn.setEnabled(len(self.models_list.selectedItems()) > 0)

    def _on_open_folder(self):
        """Открывает папку моделей в файловом менеджере"""
        if self.models_path and os.path.exists(self.models_path):
            subprocess.run(['xdg-open', self.models_path])

    def _on_delete(self):
        """Удаляет выбранную модель"""
        selected_items = self.models_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        model_path = item.data(Qt.ItemDataRole.UserRole)
        model_name = item.text()

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить модель:\n{model_name}?\n\nПуть: {model_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(model_path):
                    shutil.rmtree(model_path)
                else:
                    os.remove(model_path)

                self._load_models()
                QMessageBox.information(self, "Готово", "Модель удалена")

            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить:\n{str(e)}")

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/__init__.py
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/paths_dialog.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QLineEdit, QPushButton, QDialogButtonBox,
                              QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
from core.path_validator import PathValidator

class PathsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.validator = PathValidator()
        
        self.setWindowTitle("Настройка путей к компонентам")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout(self)
        
        # Diffusers
        diffusers_group = QGroupBox("Diffusers")
        diffusers_layout = QVBoxLayout()
        
        # venv
        venv_layout = QHBoxLayout()
        venv_layout.addWidget(QLabel("venv:"))
        self.venv_edit = QLineEdit()
        self.venv_edit.setText(config.get_sdxl_venv_path())
        self.venv_edit.textChanged.connect(lambda: self._on_path_changed("venv"))
        venv_layout.addWidget(self.venv_edit, 1)
        
        venv_browse = QPushButton("📁")
        venv_browse.setFixedWidth(40)
        venv_browse.clicked.connect(lambda: self._browse_folder(self.venv_edit))
        venv_layout.addWidget(venv_browse)
        
        self.venv_status = QLabel("")
        venv_layout.addWidget(self.venv_status)
        
        diffusers_layout.addLayout(venv_layout)
        self.venv_error = QLabel("")
        self.venv_error.setStyleSheet("color: red; font-size: 11px;")
        self.venv_error.hide()
        diffusers_layout.addWidget(self.venv_error)
        
        # Models
        models_layout = QHBoxLayout()
        models_layout.addWidget(QLabel("Модели:"))
        self.models_edit = QLineEdit()
        self.models_edit.setText(config.get_sdxl_models_path())
        self.models_edit.textChanged.connect(lambda: self._on_path_changed("models"))
        models_layout.addWidget(self.models_edit, 1)
        
        models_browse = QPushButton("📁")
        models_browse.setFixedWidth(40)
        models_browse.clicked.connect(lambda: self._browse_folder(self.models_edit))
        models_layout.addWidget(models_browse)
        
        self.models_status = QLabel("")
        models_layout.addWidget(self.models_status)
        
        diffusers_layout.addLayout(models_layout)
        self.models_error = QLabel("")
        self.models_error.setStyleSheet("color: red; font-size: 11px;")
        self.models_error.hide()
        diffusers_layout.addWidget(self.models_error)
        
        diffusers_group.setLayout(diffusers_layout)
        layout.addWidget(diffusers_group)
        
        # Сохранение
        output_group = QGroupBox("Сохранение")
        output_layout = QVBoxLayout()
        
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("Папка для изображений:"))
        self.output_edit = QLineEdit()
        self.output_edit.setText(config.get_sdxl_output_dir())
        self.output_edit.textChanged.connect(lambda: self._on_path_changed("output"))
        output_path_layout.addWidget(self.output_edit, 1)
        
        output_browse = QPushButton("📁")
        output_browse.setFixedWidth(40)
        output_browse.clicked.connect(lambda: self._browse_folder(self.output_edit))
        output_path_layout.addWidget(output_browse)
        
        self.output_status = QLabel("")
        output_path_layout.addWidget(self.output_status)
        
        output_layout.addLayout(output_path_layout)
        self.output_error = QLabel("")
        self.output_error.setStyleSheet("color: red; font-size: 11px;")
        self.output_error.hide()
        output_layout.addWidget(self.output_error)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # Ollama
        ollama_group = QGroupBox("Ollama")
        ollama_layout = QVBoxLayout()
        
        ollama_url_layout = QHBoxLayout()
        ollama_url_layout.addWidget(QLabel("URL:"))
        self.ollama_edit = QLineEdit()
        self.ollama_edit.setText(config.get_ollama_url())
        self.ollama_edit.textChanged.connect(lambda: self._on_path_changed("ollama"))
        ollama_url_layout.addWidget(self.ollama_edit, 1)
        
        self.ollama_status = QLabel("")
        ollama_url_layout.addWidget(self.ollama_status)
        
        ollama_layout.addLayout(ollama_url_layout)
        self.ollama_error = QLabel("")
        self.ollama_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_error.hide()
        ollama_layout.addWidget(self.ollama_error)
        
        ollama_group.setLayout(ollama_layout)
        layout.addWidget(ollama_group)
        
        # Кнопки
        validate_btn = QPushButton("Проверить всё")
        validate_btn.clicked.connect(self._on_validate_all)
        layout.addWidget(validate_btn)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        
        # Первоначальная валидация
        self._on_validate_all()
    
    def _on_path_changed(self, field_name):
        """Валидация одного поля"""
        if field_name == "venv":
            result = self.validator.validate_venv(self.venv_edit.text())
            self._update_status(self.venv_status, self.venv_error, result)
        elif field_name == "models":
            result = self.validator.validate_models_path(self.models_edit.text())
            self._update_status(self.models_status, self.models_error, result)
        elif field_name == "output":
            result = self.validator.validate_output_dir(self.output_edit.text())
            self._update_status(self.output_status, self.output_error, result)
        elif field_name == "ollama":
            result = self.validator.validate_ollama_url(self.ollama_edit.text())
            self._update_status(self.ollama_status, self.ollama_error, result)
        
        self._update_ok_button()
    
    def _update_status(self, status_label, error_label, result):
        """Обновляет индикатор статуса"""
        if result["valid"]:
            status_label.setText("✅")
            error_label.hide()
        else:
            status_label.setText("❌")
            error_label.setText(result.get("error", ""))
            error_label.show()
    
    def _update_ok_button(self):
        """Обновляет доступность кнопки OK"""
        venv_valid = self.validator.validate_venv(self.venv_edit.text())["valid"]
        models_valid = self.validator.validate_models_path(self.models_edit.text())["valid"]
        output_valid = self.validator.validate_output_dir(self.output_edit.text())["valid"]
        
        self.ok_button.setEnabled(venv_valid and models_valid and output_valid)
    
    def _on_validate_all(self):
        """Проверка всех путей"""
        self._on_path_changed("venv")
        self._on_path_changed("models")
        self._on_path_changed("output")
        self._on_path_changed("ollama")
    
    def _on_accept(self):
        """Сохранение и закрытие"""
        self.config.set_sdxl_venv_path(self.venv_edit.text())
        self.config.set_sdxl_models_path(self.models_edit.text())
        self.config.set_sdxl_output_dir(self.output_edit.text())
        self.config.set("url", self.ollama_edit.text())
        self.accept()
    
    def _browse_folder(self, line_edit):
        """Открытие диалога выбора папки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку",
            line_edit.text()
        )
        if folder:
            line_edit.setText(folder)

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/settings/diffusers_settings_widget.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                              QCheckBox, QPushButton, QLabel)
from PyQt6.QtCore import Qt

class DiffusersSettingsWidget(QWidget):
    """Виджет настроек Diffusers для меню"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Device (CPU/GPU)
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setToolTip(
            "Устройство для генерации. CPU — медленно, но работает без видеокарты. "
            "CUDA — быстро, но требует NVIDIA GPU с драйвером."
        )
        form.addRow("Устройство:", self.device_combo)

        # Safety Checker
        self.safety_check = QCheckBox("Отключить цензуру (NSFW filter)")
        self.safety_check.setToolTip(
            "Safety Checker блокирует изображения с NSFW-контентом. "
            "Отключение позволяет генерировать любые изображения, но может привести к артефактам."
        )
        form.addRow("", self.safety_check)

        layout.addLayout(form)

        # Кнопка управления моделями
        layout.addSpacing(20)
        self.models_btn = QPushButton("📦 Управление моделями...")
        self.models_btn.setToolTip("Скачать, удалить или обновить модели Diffusers")
        self.models_btn.clicked.connect(self._on_manage_models)
        layout.addWidget(self.models_btn)

        layout.addStretch()

        # Загружаем настройки
        self.load_settings()

    def load_settings(self):
        """Загружает настройки из конфига в UI"""
        self.device_combo.setCurrentText(self.config.get("sdxl/device", "cuda"))
        self.safety_check.setChecked(self.config.get("sdxl/no_safety_checker", "false") == "true")

    def save_settings(self):
        """Сохраняет настройки из UI в конфиг"""
        self.config.set("sdxl/device", self.device_combo.currentText())
        self.config.set("sdxl/no_safety_checker", str(self.safety_check.isChecked()).lower())

    def _on_manage_models(self):
        """Открывает диалог управления моделями"""
        from ui.dialogs.diffusers_models_dialog import DiffusersModelsDialog
        dialog = DiffusersModelsDialog(self.config, self)
        dialog.exec()

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/settings/__init__.py
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/settings/paths_settings_widget.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                              QLabel, QLineEdit, QPushButton, QFileDialog)
from PyQt6.QtCore import Qt
from core.path_validator import PathValidator

class PathsSettingsWidget(QWidget):
    """Виджет общих настроек путей"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.validator = PathValidator()
        layout = QVBoxLayout(self)

        # Diffusers
        diffusers_group = QGroupBox("Diffusers")
        diffusers_layout = QVBoxLayout()

        # venv
        venv_layout = QHBoxLayout()
        venv_layout.addWidget(QLabel("venv:"))
        self.venv_edit = QLineEdit()
        self.venv_edit.setText(config.get_sdxl_venv_path())
        self.venv_edit.textChanged.connect(lambda: self._on_path_changed("venv"))
        venv_layout.addWidget(self.venv_edit, 1)
        venv_browse = QPushButton("📁")
        venv_browse.setFixedWidth(40)
        venv_browse.clicked.connect(lambda: self._browse_folder(self.venv_edit))
        venv_layout.addWidget(venv_browse)
        self.venv_status = QLabel("")
        venv_layout.addWidget(self.venv_status)
        diffusers_layout.addLayout(venv_layout)

        self.venv_error = QLabel("")
        self.venv_error.setStyleSheet("color: red; font-size: 11px;")
        self.venv_error.hide()
        diffusers_layout.addWidget(self.venv_error)

        # Models
        models_layout = QHBoxLayout()
        models_layout.addWidget(QLabel("Модели:"))
        self.models_edit = QLineEdit()
        self.models_edit.setText(config.get_sdxl_models_path())
        self.models_edit.textChanged.connect(lambda: self._on_path_changed("models"))
        models_layout.addWidget(self.models_edit, 1)
        models_browse = QPushButton("📁")
        models_browse.setFixedWidth(40)
        models_browse.clicked.connect(lambda: self._browse_folder(self.models_edit))
        models_layout.addWidget(models_browse)
        self.models_status = QLabel("")
        models_layout.addWidget(self.models_status)
        diffusers_layout.addLayout(models_layout)

        self.models_error = QLabel("")
        self.models_error.setStyleSheet("color: red; font-size: 11px;")
        self.models_error.hide()
        diffusers_layout.addWidget(self.models_error)

        diffusers_group.setLayout(diffusers_layout)
        layout.addWidget(diffusers_group)

        # Сохранение
        output_group = QGroupBox("Сохранение")
        output_layout = QVBoxLayout()

        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("Папка для изображений:"))
        self.output_edit = QLineEdit()
        self.output_edit.setText(config.get_sdxl_output_dir())
        self.output_edit.textChanged.connect(lambda: self._on_path_changed("output"))
        output_path_layout.addWidget(self.output_edit, 1)
        output_browse = QPushButton("📁")
        output_browse.setFixedWidth(40)
        output_browse.clicked.connect(lambda: self._browse_folder(self.output_edit))
        output_path_layout.addWidget(output_browse)
        self.output_status = QLabel("")
        output_path_layout.addWidget(self.output_status)
        output_layout.addLayout(output_path_layout)

        self.output_error = QLabel("")
        self.output_error.setStyleSheet("color: red; font-size: 11px;")
        self.output_error.hide()
        output_layout.addWidget(self.output_error)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Ollama
        ollama_group = QGroupBox("Ollama")
        ollama_layout = QVBoxLayout()

        ollama_url_layout = QHBoxLayout()
        ollama_url_layout.addWidget(QLabel("URL:"))
        self.ollama_edit = QLineEdit()
        self.ollama_edit.setText(config.get_ollama_url())
        self.ollama_edit.textChanged.connect(lambda: self._on_path_changed("ollama"))
        ollama_url_layout.addWidget(self.ollama_edit, 1)
        self.ollama_refresh = QPushButton("🔄")
        self.ollama_refresh.setFixedWidth(40)
        self.ollama_refresh.setToolTip("Перепроверить связь с Ollama")
        self.ollama_refresh.clicked.connect(lambda: self._on_path_changed("ollama"))
        ollama_url_layout.addWidget(self.ollama_refresh)
        self.ollama_status = QLabel("")
        ollama_url_layout.addWidget(self.ollama_status)
        ollama_layout.addLayout(ollama_url_layout)

        self.ollama_error = QLabel("")
        self.ollama_error.setStyleSheet("color: red; font-size: 11px;")
        self.ollama_error.hide()
        ollama_layout.addWidget(self.ollama_error)

        ollama_group.setLayout(ollama_layout)
        layout.addWidget(ollama_group)

        layout.addStretch()

        # Первоначальная валидация
        self._on_validate_all()

    def load_settings(self):
        """Загружает настройки из конфига в UI"""
        self.venv_edit.setText(self.config.get_sdxl_venv_path())
        self.models_edit.setText(self.config.get_sdxl_models_path())
        self.output_edit.setText(self.config.get_sdxl_output_dir())
        self.ollama_edit.setText(self.config.get_ollama_url())
        self._on_validate_all()

    def save_settings(self):
        """Сохраняет настройки из UI в конфиг"""
        self.config.set_sdxl_venv_path(self.venv_edit.text())
        self.config.set_sdxl_models_path(self.models_edit.text())
        self.config.set_sdxl_output_dir(self.output_edit.text())
        self.config.set("url", self.ollama_edit.text())

    def _on_path_changed(self, field_name):
        """Валидация одного поля"""
        if field_name == "venv":
            result = self.validator.validate_venv(self.venv_edit.text())
            self._update_status(self.venv_status, self.venv_error, result)
        elif field_name == "models":
            result = self.validator.validate_models_path(self.models_edit.text())
            self._update_status(self.models_status, self.models_error, result)
        elif field_name == "output":
            result = self.validator.validate_output_dir(self.output_edit.text())
            self._update_status(self.output_status, self.output_error, result)
        elif field_name == "ollama":
            result = self.validator.validate_ollama_url(self.ollama_edit.text())
            self._update_status(self.ollama_status, self.ollama_error, result)
        # Пробрасываем статус в главное окно
        try:
            p = self.parent()
            while p and not hasattr(p, 'shared_bar'):
                p = p.parent()
            if p and hasattr(p, 'shared_bar'):
                p.shared_bar.set_status(
                    "✅ Ollama подключён" if result["valid"] else "❌ Не удалось подключиться",
                    "green" if result["valid"] else "red"
                )
        except Exception:
            pass

    def _update_status(self, status_label, error_label, result):
        """Обновляет индикатор статуса"""
        if result["valid"]:
            status_label.setText("✅")
            error_label.hide()
        else:
            status_label.setText("❌")
            error_label.setText(result.get("error", ""))
            error_label.show()

    def _on_validate_all(self):
        """Проверка всех путей"""
        self._on_path_changed("venv")
        self._on_path_changed("models")
        self._on_path_changed("output")
        self._on_path_changed("ollama")

    def _browse_folder(self, line_edit):
        """Открытие диалога выбора папки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку",
            line_edit.text()
        )
        if folder:
            line_edit.setText(folder)

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/settings/resources_settings_widget.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QSpinBox,
                              QDoubleSpinBox, QLabel, QGroupBox)
from PyQt6.QtCore import Qt

class ResourcesSettingsWidget(QWidget):
    """Виджет настроек ресурсов (RAM, CPU)"""
    def __init__(self, config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)
        
        # === Память ===
        memory_group = QGroupBox("Память (RAM)")
        memory_layout = QFormLayout()
        
        self.max_ram_spin = QSpinBox()
        self.max_ram_spin.setRange(50, 95)
        self.max_ram_spin.setValue(int(self.config.get("resources/max_ram_percent", 80)))
        self.max_ram_spin.setSuffix(" %")
        self.max_ram_spin.setToolTip(
            "Максимальный процент RAM, который может использовать приложение. "
            "Остальное оставляем для системы."
        )
        memory_layout.addRow("Максимум RAM:", self.max_ram_spin)
        
        # Информация о доступной памяти
        import psutil
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        self.memory_info = QLabel(
            f"Всего: {total_gb:.1f} GB | Доступно: {available_gb:.1f} GB"
        )
        self.memory_info.setStyleSheet("color: gray; font-size: 11px;")
        memory_layout.addRow("", self.memory_info)
        
        memory_group.setLayout(memory_layout)
        layout.addWidget(memory_group)
        
        # === Процессор ===
        cpu_group = QGroupBox("Процессор (CPU)")
        cpu_layout = QFormLayout()
        
        self.cpu_cores_spin = QSpinBox()
        self.cpu_cores_spin.setRange(1, 4)  # У тебя 4 ядра
        self.cpu_cores_spin.setValue(int(self.config.get("resources/cpu_cores", 3)))
        self.cpu_cores_spin.setToolTip(
            "Количество ядер CPU для приложения. "
            "Оставляем 1-2 ядра свободными для системы."
        )
        cpu_layout.addRow("Ядер CPU:", self.cpu_cores_spin)
        
        self.cpu_priority_spin = QSpinBox()
        self.cpu_priority_spin.setRange(-20, 19)
        self.cpu_priority_spin.setValue(int(self.config.get("resources/cpu_priority", 0)))
        self.cpu_priority_spin.setToolTip(
            "Приоритет процесса (nice). "
            "0 = нормальный, 10 = низкий (система отзывчивее), -10 = высокий."
        )
        cpu_layout.addRow("Приоритет (nice):", self.cpu_priority_spin)
        
        # Информация о CPU
        import os
        cpu_count = os.cpu_count() or 4
        self.cpu_info = QLabel(f"Всего ядер: {cpu_count}")
        self.cpu_info.setStyleSheet("color: gray; font-size: 11px;")
        cpu_layout.addRow("", self.cpu_info)
        
        cpu_group.setLayout(cpu_layout)
        layout.addWidget(cpu_group)
        
        layout.addStretch()
    
    def load_settings(self):
        """Загружает настройки из конфига в UI"""
        self.max_ram_spin.setValue(int(self.config.get("resources/max_ram_percent", 80)))
        self.cpu_cores_spin.setValue(int(self.config.get("resources/cpu_cores", 3)))
        self.cpu_priority_spin.setValue(int(self.config.get("resources/cpu_priority", 0)))
    
    def save_settings(self):
        """Сохраняет настройки из UI в конфиг"""
        self.config.set("resources/max_ram_percent", self.max_ram_spin.value())
        self.config.set("resources/cpu_cores", self.cpu_cores_spin.value())
        self.config.set("resources/cpu_priority", self.cpu_priority_spin.value())

# ════════════════════════════════════════════════════════════
# FILE: ui/dialogs/settings/settings_dialog.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox
from PyQt6.QtCore import Qt
from ui.dialogs.settings.paths_settings_widget import PathsSettingsWidget
from ui.dialogs.settings.diffusers_settings_widget import DiffusersSettingsWidget
from ui.dialogs.settings.resources_settings_widget import ResourcesSettingsWidget

class SettingsDialog(QDialog):
    """Главный диалог настроек приложения"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки")
        self.setMinimumSize(500, 500)

        layout = QVBoxLayout(self)

        # Вкладки
        self.tabs = QTabWidget()

        # Вкладка Общие (пути)
        self.paths_widget = PathsSettingsWidget(config)
        self.tabs.addTab(self.paths_widget, "📁 Общие")

        # Вкладка Diffusers
        self.diffusers_widget = DiffusersSettingsWidget(config)
        self.tabs.addTab(self.diffusers_widget, "🎨 Diffusers")
        
        # Вкладка Ресурсы
        self.resources_widget = ResourcesSettingsWidget(config)
        self.tabs.addTab(self.resources_widget, "⚙️ Ресурсы")

        # Будущие вкладки:
        # self.ollama_widget = OllamaSettingsWidget(config)
        # self.tabs.addTab(self.ollama_widget, "💬 Ollama")

        layout.addWidget(self.tabs, 1)

        # Кнопки OK/Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        """Сохраняет все настройки и закрывает диалог"""
        self.paths_widget.save_settings()
        self.diffusers_widget.save_settings()
        self.resources_widget.save_settings()
        # self.ollama_widget.save_settings()  # будущее
        self.accept()

# ════════════════════════════════════════════════════════════
# FILE: ui/__init__.py
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# FILE: ui/main_window.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget, QMenuBar, QMessageBox
from PyQt6.QtGui import QAction
from ui.tabs.ollama_tab import OllamaTab
from ui.tabs.diffusers_tab import DiffusersTab
from ui.shared_bottom_bar import SharedBottomBar
from ui.dialogs.settings.settings_dialog import SettingsDialog
from utils.config import Config
from core.resource_manager import ResourceManager
from core.path_validator import PathValidator
from core.ollama_manager import OllamaManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalAILite")
        self.resize(1100, 700)

        self.config = Config()
        self.resource_manager = ResourceManager()

        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        self.ollama_tab = OllamaTab(self.config)
        self.tabs.addTab(self.ollama_tab, "💬 Ollama Chat")

        self.diffusers_tab = DiffusersTab(self.config)
        self.tabs.addTab(self.diffusers_tab, "🎨 Diffusers")

        self.shared_bar = SharedBottomBar()
        main_layout.addWidget(self.shared_bar)

        self.setCentralWidget(central_widget)

        self.resource_manager.register_module("ollama", self.ollama_tab)
        self.resource_manager.register_module("diffusers", self.diffusers_tab)

        # === Ollama Manager ===
        self.ollama_manager = OllamaManager(self.config)
        self.ollama_manager.started.connect(self._on_ollama_started)
        self.ollama_manager.stopped.connect(self._on_ollama_stopped)
        self.ollama_manager.error.connect(self._on_ollama_error)
        self.ollama_manager.log_line.connect(self._on_ollama_log)
        self.ollama_manager.needs_install.connect(self._on_ollama_needs_install)
        self.ollama_manager.conflict_detected.connect(self._on_ollama_conflict)

        # === Подключение сигналов ===
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._prev_index = 0

        self.shared_bar.prompt_changed.connect(self._on_prompt_changed)
        self.shared_bar.prompt_submitted.connect(self.on_prompt_submitted)
        self.shared_bar.generation_stopped.connect(self.on_generation_stopped)
        self.shared_bar.blocked_action.connect(self._on_blocked_action)

        # Универсальные сигналы состояния от табов
        self.ollama_tab.state_changed.connect(self._on_tab_state_changed)
        self.diffusers_tab.state_changed.connect(self._on_tab_state_changed)

        self._create_menu()
        self._restore_bar_state()

        # Восстанавливаем состояние первого таба
        first_tab = self.tabs.widget(0)
        if hasattr(first_tab, '_bar_state'):
            state = first_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_end_label(state["end_label"])
            self.shared_bar.set_status(state["status"])

        self._update_status()

        # Запускаем Ollama (после показа окна, чтобы диалоги не блокировали)
        # Используем QTimer.singleShot, чтобы окно успело отрисоваться
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.ollama_manager.start)

    def _create_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Файл")
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("Настройки")
        settings_action = QAction("Настройки...", self)
        settings_action.triggered.connect(self._show_settings_dialog)
        settings_menu.addAction(settings_action)

    def _show_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self._update_status()

    def _update_status(self):
        validator = PathValidator()
        result = validator.validate_all(self.config)
        if not result["all_valid"]:
            errors = []
            if not result["venv"]["valid"]:
                errors.append("venv")
            if not result["models"]["valid"]:
                errors.append("модели")
            if not result["output"]["valid"]:
                errors.append("папка сохранения")
            if not result["ollama"]["valid"]:
                errors.append("Ollama")
            self.shared_bar.set_status(f"⚠ Настройте пути: {', '.join(errors)}", "orange")
        else:
            self.shared_bar.set_status("Готово")

    def _on_tab_changed(self, index):
        """Переключение табов"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state') and active_tab._bar_state["is_running"]:
            self.shared_bar.set_status("⚠ Идёт генерация, дождитесь завершения", "red")
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._prev_index)
            self.tabs.blockSignals(False)
            return

        prev_tab = self.tabs.widget(self._prev_index)
        if hasattr(prev_tab, '_bar_state'):
            prev_tab._bar_state["prompt"] = self.shared_bar.get_prompt()

        self.resource_manager.on_tab_changed(index)

        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            state = active_tab._bar_state
            self.shared_bar.set_prompt(state["prompt"])
            self.shared_bar.set_end_label(state["end_label"])
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
            self.shared_bar.set_status(state["status"])
            if state["is_running"]:
                self.shared_bar.start_timer()
            else:
                self.shared_bar.stop_timer()

        self._prev_index = index

    def _on_prompt_changed(self, text):
        """Изменение промпта"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            active_tab._bar_state["prompt"] = text

    def _on_tab_state_changed(self, state):
        """Изменение состояния таба"""
        sender = self.sender()
        if sender != self.tabs.currentWidget():
            return

        if "prompt" in state:
            self.shared_bar.set_prompt(state["prompt"])
        if "progress_current" in state and "progress_total" in state:
            self.shared_bar.set_progress(state["progress_current"], state["progress_total"])
        if "status" in state:
            self.shared_bar.set_status(state["status"])
        if "end_label" in state:
            self.shared_bar.set_end_label(state["end_label"])

        if state.get("is_running"):
            self.shared_bar.start_timer()
            self.shared_bar.set_running_state(True)
        else:
            self.shared_bar.stop_timer()
            self.shared_bar.set_running_state(False)

    def _on_blocked_action(self, text):
        """Действие заблокировано"""
        self.shared_bar.set_status(text, "red")

    def on_prompt_submitted(self, prompt):
        """Отправляет промпт в активный модуль"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state') and active_tab._bar_state["is_running"]:
            self.shared_bar.set_status("⚠ Дождитесь завершения текущей генерации", "red")
            return

        if hasattr(active_tab, 'handle_prompt'):
            active_tab.handle_prompt(prompt)

    def on_generation_stopped(self):
        """Останавливает генерацию в активном модуле"""
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, 'stop_generation'):
            active_tab.stop_generation()

    def _restore_bar_state(self):
        """Восстановление состояния табов из QSettings"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, '_bar_state'):
                tab_name = "ollama" if i == 0 else "diffusers"
                saved_state = self.config.get_json(f"bar_state/{tab_name}")
                if saved_state:
                    for key in tab._bar_state.keys():
                        if key in saved_state:
                            tab._bar_state[key] = saved_state[key]
                # Сбрасываем is_running при старте — генерация не может продолжаться после перезапуска
                tab._bar_state["is_running"] = False

    def _save_bar_state(self):
        """Сохранение состояния табов в QSettings"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, '_bar_state'):
                tab_name = "ollama" if i == 0 else "diffusers"
                self.config.set_json(f"bar_state/{tab_name}", tab._bar_state)

    # === Ollama Manager handlers ===

    def _on_ollama_started(self):
        """Ollama запущен и готов"""
        if self.ollama_manager.is_our_process():
            self.shared_bar.set_status("✅ Ollama запущен (наш процесс)", "green")
        else:
            self.shared_bar.set_status("✅ Ollama подключён (внешний)", "green")

    def _on_ollama_stopped(self):
        """Ollama остановлен"""
        self.shared_bar.set_status("Ollama остановлен")

    def _on_ollama_error(self, error_msg):
        """Ошибка Ollama"""
        self.shared_bar.set_status(f"⚠ Ollama: {error_msg}", "red")

    def _on_ollama_log(self, line):
        """Строка лога Ollama — добавляем в бегущую строку статуса"""
        # Показываем только важные строки, чтобы не засорять статус
        if any(kw in line.lower() for kw in ["error", "listening", "started", "loaded"]):
            self.shared_bar.set_status(f"Ollama: {line[:80]}", "gray")

    def _on_ollama_needs_install(self):
        """Требуется установка Ollama"""
        reply = QMessageBox.question(
            self,
            "Ollama не найден",
            "Ollama не установлен.\n\n"
            "Скачать и установить? (~1 GB)\n\n"
            "Бинарник будет сохранён в папке приложения (bin/ollama).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_ollama()
        else:
            self.shared_bar.set_status("⚠ Ollama не установлен", "orange")

    def _on_ollama_conflict(self):
        """Обнаружен конфликт — Ollama уже запущен"""
        reply = QMessageBox.question(
            self,
            "Ollama уже запущен",
            "Ollama-сервер уже запущен (возможно, через systemd).\n\n"
            "• Да — использовать существующий сервер\n"
            "• Нет — убить его и запустить свой\n"
            "• Отмена — не использовать Ollama",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.ollama_manager.use_existing()
        elif reply == QMessageBox.StandardButton.No:
            self.shared_bar.set_status("Убиваем существующий Ollama...")
            self.ollama_manager.kill_existing_and_start()
        else:
            self.shared_bar.set_status("⚠ Ollama: конфликт не разрешён", "orange")

    def _download_ollama(self):
        """Скачивает Ollama"""
        # TODO: Реализовать скачивание через QThread + прогрессбар
        self.shared_bar.set_status("⚠ Скачивание Ollama пока не реализовано", "orange")

    def closeEvent(self, event):
        """Показывает диалог очистки при закрытии"""
        # Сохраняем состояние
        active_tab = self.tabs.currentWidget()
        if hasattr(active_tab, '_bar_state'):
            active_tab._bar_state["prompt"] = self.shared_bar.get_prompt()
        self._save_bar_state()

        # Отменяем закрытие и скрываем окно
        event.ignore()
        self.hide()

        # Показываем диалог очистки
        from ui.cleanup_dialog import CleanupDialog
        cleanup_dialog = CleanupDialog(
            self.ollama_tab,
            self.diffusers_tab,
            self.config,
            self.ollama_manager,
            self
        )

        # После закрытия диалога — выходим
        if cleanup_dialog.exec():
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()

# ════════════════════════════════════════════════════════════
# FILE: ui/settings_panel.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox,
                             QDoubleSpinBox, QSpinBox, QTextEdit,
                             QPushButton, QCheckBox)
from utils.config import Config
import requests

class SettingsPanel(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        layout = QVBoxLayout(self)

        # Модель
        layout.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        layout.addWidget(self.model_combo)

        # Temperature
        layout.addWidget(QLabel("Temperature:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        layout.addWidget(self.temp_spin)

        # Top P
        layout.addWidget(QLabel("Top P:"))
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        layout.addWidget(self.top_p_spin)

        # Max Tokens
        layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setSingleStep(64)
        layout.addWidget(self.max_tokens_spin)

        # Timeout
        layout.addWidget(QLabel("Timeout (сек):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 3600)
        self.timeout_spin.setSingleStep(60)
        layout.addWidget(self.timeout_spin)

        # Stream
        self.stream_check = QCheckBox("Stream (потоковый вывод)")
        layout.addWidget(self.stream_check)

        # System Prompt
        layout.addWidget(QLabel("System Prompt:"))
        self.sys_prompt = QTextEdit()
        self.sys_prompt.setMaximumHeight(100)
        layout.addWidget(self.sys_prompt)

        # Очистить чат
        self.clear_btn = QPushButton("Очистить чат")
        layout.addWidget(self.clear_btn)

        layout.addStretch()

        # Кнопка Отправить внизу
        self.send_btn = QPushButton("Отправить")
        layout.addWidget(self.send_btn)

        self.load_settings()
        self.load_models()

    def load_settings(self):
        self.temp_spin.setValue(float(self.config.get("temperature", 0.7)))
        self.top_p_spin.setValue(float(self.config.get("top_p", 0.9)))
        self.max_tokens_spin.setValue(int(self.config.get("max_tokens", 1024)))
        self.timeout_spin.setValue(int(self.config.get("timeout", 600)))
        self.stream_check.setChecked(self.config.get("stream", "true") == "true")
        self.sys_prompt.setPlainText(self.config.get("system_prompt", ""))
        self.model_combo.setCurrentText(self.config.get("model", "qwen2.5-coder:3b"))

    def save_settings(self):
        self.config.set("temperature", self.temp_spin.value())
        self.config.set("top_p", self.top_p_spin.value())
        self.config.set("max_tokens", self.max_tokens_spin.value())
        self.config.set("timeout", self.timeout_spin.value())
        self.config.set("stream", str(self.stream_check.isChecked()).lower())
        self.config.set("system_prompt", self.sys_prompt.toPlainText())
        self.config.set("model", self.model_combo.currentText())

    def load_models(self):
        try:
            url = self.config.get("url", "http://localhost:11434")
            res = requests.get(f"{url}/api/tags", timeout=5)
            models = [m['name'] for m in res.json().get('models', [])]
            self.model_combo.clear()
            self.model_combo.addItems(models)
        except Exception:
            pass

# ════════════════════════════════════════════════════════════
# FILE: ui/shared_bottom_bar.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTextEdit,
                             QPushButton, QProgressBar, QLabel)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer


class SharedBottomBar(QWidget):
    """Общая нижняя панель с полем ввода промпта, прогрессбаром и статусом"""

    prompt_submitted = pyqtSignal(str)
    prompt_changed = pyqtSignal(str)
    generation_stopped = pyqtSignal()
    blocked_action = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # === Бегущая строка статуса ===
        self.status_label = QLabel("Готово")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.status_label.setWordWrap(False)
        self.status_label.setMinimumHeight(20)
        self.status_label.setMaximumHeight(24)
        main_layout.addWidget(self.status_label)

        # === Верхний ряд: Прогрессбар + правый контейнер ===
        progress_row = QWidget()
        progress_row.setMinimumHeight(10)  # Высота = высоте кнопок
        progress_row_layout = QHBoxLayout(progress_row)
        progress_row_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m")  # Показываем "15/30" вместо "50%"
        progress_row_layout.addWidget(self.progress_bar, 3)  # stretch=3

        right_container = QWidget()
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.end_label = QLabel("")
        self.end_label.setFixedWidth(80)
        self.end_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.end_label.setStyleSheet("font-size: 11px; color: red;")
        right_layout.addWidget(self.end_label)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFixedWidth(50)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.timer_label.setStyleSheet("font-size: 11px; color: green;")
        right_layout.addWidget(self.timer_label)
        
        # Индикаторы ресурсов
        self.ram_label = QLabel("RAM: --")
        self.ram_label.setFixedWidth(90)
        self.ram_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ram_label.setStyleSheet("font-size: 11px; color: blue;")
        right_layout.addWidget(self.ram_label)
        
        self.cpu_label = QLabel("CPU: --")
        self.cpu_label.setFixedWidth(70)
        self.cpu_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cpu_label.setStyleSheet("font-size: 11px; color: purple;")
        right_layout.addWidget(self.cpu_label)

        progress_row_layout.addWidget(right_container, 1)  # stretch=1

        main_layout.addWidget(progress_row)

        # === Нижняя часть: Поле ввода и кнопки ===
        bottom_layout = QHBoxLayout()

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText(
            "Введите промпт... (Enter - запустить, Shift+Enter - новая строка)"
        )
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setMinimumHeight(60)
        self.prompt_edit.installEventFilter(self)
        self.prompt_edit.textChanged.connect(self._on_text_changed)
        bottom_layout.addWidget(self.prompt_edit, 3)  # stretch=3

        self.run_btn = QPushButton("Запустить")
        self.run_btn.setMinimumHeight(60)
        self.run_btn.clicked.connect(self._on_run_clicked)
        bottom_layout.addWidget(self.run_btn, 1)  # stretch=1

        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setMinimumHeight(60)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        bottom_layout.addWidget(self.stop_btn, 1)  # stretch=1

        main_layout.addLayout(bottom_layout)

        # === Таймер ===
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_timer)
        self._start_time = None
        self._is_running = False
        
        # === Таймер ресурсов (обновление каждые 2 сек) ===
        self._resources_timer = QTimer()
        self._resources_timer.setInterval(2000)
        self._resources_timer.timeout.connect(self._update_resources)
        self._resources_timer.start()
        self._update_resources()  # Сразу показать

    # ─── Публичные методы ───

    def get_prompt(self):
        return self.prompt_edit.toPlainText().strip()

    def set_prompt(self, text):
        self.prompt_edit.setPlainText(text)

    def set_status(self, text, color=None):
        if color:
            self.status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        else:
            self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.status_label.setText(text)

    def set_progress(self, current, total):
        self.progress_bar.setRange(0, max(total, 0))
        self.progress_bar.setValue(current)

    def set_end_label(self, text):
        self.end_label.setText(text)

    def start_timer(self):
        import time
        self._start_time = time.time()
        self._is_running = True
        self._timer.start()

    def stop_timer(self):
        self._is_running = False
        self._timer.stop()

    def set_running_state(self, running):
        self.run_btn.setVisible(not running)
        self.stop_btn.setVisible(running)
        self.prompt_edit.setEnabled(not running)

    # ─── Внутренние методы ───

    def _on_text_changed(self):
        self.prompt_changed.emit(self.prompt_edit.toPlainText())

    def _on_run_clicked(self):
        text = self.get_prompt()
        if text:
            self.prompt_submitted.emit(text)

    def _on_stop_clicked(self):
        self.generation_stopped.emit()

    def _update_timer(self):
        if self._is_running and self._start_time:
            import time
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            self.timer_label.setText(f"{mins:02d}:{secs:02d}")
    
    def _update_resources(self):
        """Обновляет индикаторы RAM и CPU"""
        try:
            import psutil
            # RAM
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            self.ram_label.setText(f"RAM: {used_gb:.1f}/{total_gb:.0f}G")
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_label.setText(f"CPU: {cpu_percent:.0f}%")
            
            # Цвета по нагрузке
            if cpu_percent > 80:
                self.cpu_label.setStyleSheet("font-size: 11px; color: red;")
            elif cpu_percent > 50:
                self.cpu_label.setStyleSheet("font-size: 11px; color: orange;")
            else:
                self.cpu_label.setStyleSheet("font-size: 11px; color: purple;")
        except ImportError:
            self.ram_label.setText("RAM: N/A")
            self.cpu_label.setText("CPU: N/A")
        except Exception as e:
            self.ram_label.setText(f"RAM: err")
            self.cpu_label.setText(f"CPU: err")

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.prompt_edit and event.type() == QEvent.Type.KeyPress:
            from PyQt6.QtCore import Qt
            key_event = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._on_run_clicked()
                    return True
        return super().eventFilter(obj, event)

# ════════════════════════════════════════════════════════════
# FILE: ui/tabs/diffusers_settings_panel.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                             QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton,
                             QTextEdit, QHBoxLayout, QLabel, QCheckBox)
from PyQt6.QtCore import Qt
import random
import os
from core.checkpoint_manager import list_archived_checkpoints, load_archived_checkpoint


class DiffusersSettingsPanel(QWidget):
    """Панель настроек Diffusers с управлением чекпоинтами"""

    def __init__(self, config):
        super().__init__()
        self.config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # === Чекпоинты (в самом верху) ===
        checkpoint_row = QHBoxLayout()
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setSizePolicy(
            self.checkpoint_combo.sizePolicy().horizontalPolicy(),
            self.checkpoint_combo.sizePolicy().verticalPolicy()
        )
        checkpoint_row.addWidget(self.checkpoint_combo, 1)

        self.load_checkpoint_btn = QPushButton("📥")
        self.load_checkpoint_btn.setFixedWidth(40)
        self.load_checkpoint_btn.setToolTip("Загрузить выбранный чекпоинт")
        checkpoint_row.addWidget(self.load_checkpoint_btn)

        layout.addLayout(checkpoint_row)

        # === Основные настройки ===
        form = QFormLayout()
        form.setSpacing(8)

        # Model + кнопка обновления
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        model_row.addWidget(self.model_combo, 1)

        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedWidth(40)
        self.refresh_models_btn.setToolTip("Обновить список моделей")
        self.refresh_models_btn.clicked.connect(self._load_models)
        model_row.addWidget(self.refresh_models_btn)

        form.addRow("Model:", model_row)

        # Scheduler
        self.scheduler_combo = QComboBox()
        self.scheduler_combo.addItems([
            "EulerDiscreteScheduler",
            "EulerAncestralDiscreteScheduler",
            "DPMSolverMultistepScheduler",
            "DDIMScheduler",
            "PNDMScheduler"
        ])
        self.scheduler_combo.setCurrentText(self.config.get_sdxl_scheduler())
        form.addRow("Scheduler:", self.scheduler_combo)

        # Steps
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 150)
        self.steps_spin.setValue(self.config.get_sdxl_default_steps())
        form.addRow("Steps:", self.steps_spin)

        # CFG Scale
        self.cfg_spin = QDoubleSpinBox()
        self.cfg_spin.setRange(1.0, 30.0)
        self.cfg_spin.setValue(self.config.get_sdxl_default_cfg())
        self.cfg_spin.setSingleStep(0.5)
        self.cfg_spin.setDecimals(1)
        form.addRow("CFG Scale:", self.cfg_spin)

        # Size
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "512×512", "768×768", "1024×1024", "1024×768", "768×1024"
        ])
        form.addRow("Size:", self.size_combo)

        # Seed
        seed_layout = QHBoxLayout()
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("-1 (случайный)")
        self.seed_edit.setText("-1")
        seed_layout.addWidget(self.seed_edit)

        self.random_seed_btn = QPushButton("🎲")
        self.random_seed_btn.setFixedWidth(40)
        self.random_seed_btn.clicked.connect(self._random_seed)
        seed_layout.addWidget(self.random_seed_btn)

        form.addRow("Seed:", seed_layout)

        # Preview Every
        self.preview_every_spin = QSpinBox()
        self.preview_every_spin.setRange(0, 100)
        self.preview_every_spin.setValue(int(self.config.get("sdxl/preview_every", 0)))
        self.preview_every_spin.setToolTip(
            "Сохранять превью каждые N шагов (0 = выключено, 1 = каждый шаг)"
        )
        form.addRow("Превью каждые N шагов:", self.preview_every_spin)

        # Preview Start
        self.preview_start_spin = QSpinBox()
        self.preview_start_spin.setRange(1, 150)
        self.preview_start_spin.setValue(int(self.config.get("sdxl/preview_start", 1)))
        self.preview_start_spin.setToolTip(
            "Начинать сохранение превью с этого шага (ранние шаги = шум)"
        )
        form.addRow("Начальный шаг превью:", self.preview_start_spin)

        layout.addLayout(form)

        # Negative Prompt
        layout.addWidget(QLabel("Negative Prompt:"))
        self.negative_prompt = QTextEdit()
        self.negative_prompt.setPlaceholderText("ugly, blurry, low quality, deformed...")
        self.negative_prompt.setMaximumHeight(120)
        layout.addWidget(self.negative_prompt)

        layout.addStretch()

        # Кнопка очистки
        self.clear_btn = QPushButton("Очистить настройки")
        self.clear_btn.clicked.connect(self._clear_settings)
        layout.addWidget(self.clear_btn)

        # Загружаем модели и чекпоинты при старте
        self._load_models()

    def load_checkpoints_list(self):
        """Загружает список архивных чекпоинтов в ComboBox"""
        self.checkpoint_combo.clear()
        self.checkpoint_combo.addItem("-- Выберите чекпоинт --", None)

        checkpoints = list_archived_checkpoints()
        for cp in checkpoints:
            self.checkpoint_combo.addItem(cp["display_name"], cp["filename"])

    def get_selected_checkpoint(self):
        """Возвращает имя файла выбранного чекпоинта или None"""
        index = self.checkpoint_combo.currentIndex()
        if index <= 0:  # 0 — это placeholder
            return None
        return self.checkpoint_combo.itemData(index)

    def set_params_from_checkpoint(self, json_data: dict):
        """Заполняет поля настроек из JSON чекпоинта"""
        # Model
        model = json_data.get("model", "")
        if model:
            # Проверяем, есть ли такая модель в списке
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                self.model_combo.setEditText(model)

        # Scheduler
        scheduler = json_data.get("scheduler", "")
        if scheduler:
            index = self.scheduler_combo.findText(scheduler)
            if index >= 0:
                self.scheduler_combo.setCurrentIndex(index)

        # Steps
        steps = json_data.get("total_steps", 0)
        if steps > 0:
            self.steps_spin.setValue(steps)

        # CFG
        cfg = json_data.get("cfg", 0)
        if cfg > 0:
            self.cfg_spin.setValue(cfg)

        # Size
        width = json_data.get("width", 0)
        height = json_data.get("height", 0)
        if width > 0 and height > 0:
            size_text = f"{width}×{height}"
            index = self.size_combo.findText(size_text)
            if index >= 0:
                self.size_combo.setCurrentIndex(index)

        # Seed
        seed = json_data.get("seed", -1)
        self.seed_edit.setText(str(seed))

        # Negative prompt
        negative = json_data.get("negative_prompt", "")
        if negative:
            self.negative_prompt.setPlainText(negative)

    def get_end_label(self) -> str:
        """Возвращает текст для end_label (например, '30 шагов')"""
        return f"{self.steps_spin.value()} шагов"

    def _load_models(self):
        """Загружает список моделей из папки"""
        models_path = self.config.get_sdxl_models_path()
        current_text = self.model_combo.currentText()

        self.model_combo.clear()

        if not models_path or not os.path.exists(models_path):
            self.model_combo.addItem("model.safetensors")
            return

        models = set()
        for item in os.listdir(models_path):
            item_path = os.path.join(models_path, item)

            if os.path.isdir(item_path) and item.startswith("models--"):
                model_id = item[len("models--"):].replace("--", "/")
                models.add(model_id)
            elif os.path.isfile(item_path):
                if item.endswith('.safetensors') or item.endswith('.ckpt'):
                    name = os.path.splitext(item)[0]
                    models.add(name)
            elif os.path.isdir(item_path) and not item.startswith("models--"):
                if os.path.exists(os.path.join(item_path, "model_index.json")):
                    models.add(item)

        if models:
            self.model_combo.addItems(sorted(models))
            if current_text and current_text in models:
                self.model_combo.setCurrentText(current_text)
        else:
            self.model_combo.addItem("model.safetensors")

    def _random_seed(self):
        self.seed_edit.setText(str(random.randint(0, 2**32 - 1)))

    def _clear_settings(self):
        self.negative_prompt.clear()
        self.seed_edit.setText("-1")

    def save_settings(self):
        """Сохраняет настройки в конфиг"""
        self.config.set_sdxl_scheduler(self.scheduler_combo.currentText())
        self.config.set("sdxl/steps", self.steps_spin.value())
        self.config.set("sdxl/cfg", self.cfg_spin.value())
        self.config.set("sdxl/preview_every", self.preview_every_spin.value())
        self.config.set("sdxl/preview_start", self.preview_start_spin.value())

    def get_params(self):
        """Возвращает параметры генерации"""
        size_text = self.size_combo.currentText()
        width, height = map(int, size_text.replace('×', 'x').split('x'))

        params = {
            "model": self.model_combo.currentText(),
            "scheduler": self.scheduler_combo.currentText(),
            "steps": self.steps_spin.value(),
            "cfg": self.cfg_spin.value(),
            "width": width,
            "height": height,
            "seed": int(self.seed_edit.text()) if self.seed_edit.text().isdigit() else -1,
            "preview_every": self.preview_every_spin.value(),
            "preview_start": self.preview_start_spin.value()
        }

        return params

# ════════════════════════════════════════════════════════════
# FILE: ui/tabs/diffusers_tab.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QPushButton, QFileDialog, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from ui.tabs.diffusers_settings_panel import DiffusersSettingsPanel
from core.diffusers_worker import DiffusersWorker
from core.checkpoint_manager import (
    archive_checkpoint, checkpoint_exists, delete_checkpoint, load_archived_metadata
)
import os
import json
import subprocess

class DiffusersTab(QWidget):
    """Вкладка Diffusers с состоянием для SharedBottomBar"""
    
    # Сигналы для внутреннего использования
    generation_started = pyqtSignal()
    generation_finished = pyqtSignal()
    generation_error = pyqtSignal(str)
    step_updated = pyqtSignal(int, int, str)
    status_message = pyqtSignal(str)
    
    # Универсальный сигнал для MainWindow
    state_changed = pyqtSignal(dict)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.worker = None
        self._resume_from_archive = False
        self._archive_checkpoint_file = None
        
        # Буфер бегущей строки статуса
        self._status_buffer = ""
        self._status_buffer_max_length = 150
        
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "end_label": "30 шагов",
            "is_running": False
        }
        
        layout = QHBoxLayout(self)
        
        # Левая часть: превью изображения
        left_layout = QVBoxLayout()
        self.image_view = QGraphicsView()
        self.image_view.setRenderHint(self.image_view.renderHints())
        self.scene = QGraphicsScene()
        self.image_view.setScene(self.scene)
        self.image_view.setBackgroundBrush(Qt.GlobalColor.darkGray)
        left_layout.addWidget(self.image_view, 1)
        
        self.open_folder_btn = QPushButton("📂 Открыть папку")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        left_layout.addWidget(self.open_folder_btn)
        
        layout.addLayout(left_layout, 3)
        
        # Правая часть: настройки
        self.settings_panel = DiffusersSettingsPanel(self.config)
        layout.addWidget(self.settings_panel, 1)
        
        self.settings_panel.steps_spin.valueChanged.connect(self._on_steps_changed)
        self.settings_panel.load_checkpoint_btn.clicked.connect(self._on_load_checkpoint)
        self.settings_panel.load_checkpoints_list()
        
        self._bar_state["end_label"] = self.settings_panel.get_end_label()
    
    def _on_steps_changed(self, value):
        """Обновляет end_label при изменении steps"""
        self._bar_state["end_label"] = self.settings_panel.get_end_label()
        self.state_changed.emit(self._bar_state.copy())
    
    def _on_load_checkpoint(self):
        """Загружает метаданные выбранного архивного чекпоинта"""
        filename = self.settings_panel.get_selected_checkpoint()
        if not filename:
            QMessageBox.information(
                self, "Чекпоинт",
                "Выберите чекпоинт из списка"
            )
            return
        
        json_data = load_archived_metadata(filename)
        if not json_data:
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить чекпоинт")
            return
        
        self.settings_panel.set_params_from_checkpoint(json_data)
        self._resume_from_archive = True
        self._archive_checkpoint_file = filename
        
        current_step = json_data.get("current_step", 0)
        total_steps = json_data.get("total_steps", 0)
        
        self._bar_state["prompt"] = json_data.get("prompt", "")
        self._bar_state["progress_current"] = current_step
        self._bar_state["progress_total"] = total_steps
        self._bar_state["end_label"] = f"{current_step}/{total_steps} шагов"
        self._bar_state["status"] = (
            f"💾 Чекпоинт загружен. Нажмите Запустить для продолжения "
            f"с шага {current_step}/{total_steps}"
        )
        self.state_changed.emit(self._bar_state.copy())
    
    def get_bar_state(self) -> dict:
        return self._bar_state.copy()
    
    def set_bar_state(self, state: dict):
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())
    
    def update_bar_state(self, key: str, value):
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())
    
    def _append_to_status_buffer(self, message: str):
        """Добавляет сообщение в буфер бегущей строки (новые слева)"""
        if self._status_buffer:
            self._status_buffer = f"{message} · {self._status_buffer}"
        else:
            self._status_buffer = message
        
        # Обрезаем до максимальной длины
        if len(self._status_buffer) > self._status_buffer_max_length:
            self._status_buffer = self._status_buffer[:self._status_buffer_max_length]
        
        # Обновляем статус
        self.update_bar_state("status", self._status_buffer)
    
    def handle_prompt(self, prompt):
        """Запуск генерации"""
        negative_prompt = self.settings_panel.negative_prompt.toPlainText()
        params = self.settings_panel.get_params()
        
        self.settings_panel.save_settings()
        
        # Сбрасываем буфер бегущей строки
        self._status_buffer = ""
        
        self.update_bar_state("prompt", prompt)
        self.update_bar_state("is_running", True)
        self.update_bar_state("status", "Загрузка модели...")
        self.update_bar_state("progress_total", params["steps"])
        self.update_bar_state("progress_current", 0)
        
        resume = False
        checkpoint_file = None
        
        if self._resume_from_archive:
            resume = True
            checkpoint_file = self._archive_checkpoint_file
            self._resume_from_archive = False
            self._archive_checkpoint_file = None
        else:
            # Проверяем наличие активного чекпоинта
            checkpoint_info = self._check_checkpoint()
            if checkpoint_info:
                msg = (
                    f"Найден чекпоинт от предыдущей генерации:\n\n"
                    f"Промпт: {checkpoint_info['prompt'][:60]}{'...' if len(checkpoint_info['prompt']) > 60 else ''}\n"
                    f"Модель: {checkpoint_info['model']}\n"
                    f"Прогресс: {checkpoint_info['current_step']}/{checkpoint_info['total_steps']} шагов\n"
                    f"Размер: {checkpoint_info['width']}×{checkpoint_info['height']}\n"
                    f"Seed: {checkpoint_info['seed']}\n\n"
                    f"Продолжить генерацию или начать заново?"
                )
                reply = QMessageBox.question(
                    self,
                    "Найден чекпоинт",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                resume = (reply == QMessageBox.StandardButton.Yes)
        
        self._start_generation(prompt, negative_prompt, params,
                               resume=resume, checkpoint_file=checkpoint_file)
    
    def _start_generation(self, prompt, negative_prompt, params,
                          resume=False, checkpoint_file=None):
        """Запускает генерацию (новую или продолжение)"""
        self.worker = DiffusersWorker(self.config)
        self.worker.step_updated.connect(self._on_step_updated)
        self.worker.generation_finished.connect(self._on_generation_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.status_message.connect(self._on_status_message)
        self.worker.log_line.connect(self._on_log_line)
        
        self.worker.start(prompt, negative_prompt, params,
                          resume=resume, checkpoint_file=checkpoint_file)
        
        self.generation_started.emit()
    
    def _on_log_line(self, line: str):
        """Добавляет plain text строку в бегущую строку статуса.
        JSON-строки игнорируются — их обрабатывает _on_status_message()"""
        # Проверяем, является ли строка JSON
        try:
            json.loads(line)
            # Это JSON — не добавляем в буфер
            return
        except (json.JSONDecodeError, ValueError):
            # Это plain text — добавляем в буфер
            pass
        
        self._append_to_status_buffer(line)
    
    def stop_generation(self):
        """Остановка генерации"""
        if self.worker:
            self.worker.stop()
            self._resume_from_archive = False
            self._archive_checkpoint_file = None
            
            # Спрашиваем пользователя о сохранении чекпоинта
            if checkpoint_exists():
                reply = QMessageBox.question(
                    self,
                    "Сохранить прогресс?",
                    "Сохранить прогресс генерации для продолжения позже?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    archive_checkpoint()
                    self.update_bar_state("status", "💾 Чекпоинт сохранён")
                else:
                    delete_checkpoint()
                    self.update_bar_state("status", "Генерация остановлена")
            else:
                self.update_bar_state("status", "Генерация остановлена")
    
    def unload(self):
        """Выгрузка модели"""
        if self.worker:
            self.worker.stop()
            self.worker = None
    
    def _on_step_updated(self, step, total, image_path):
        """Обновление прогресса и превью"""
        if os.path.exists(image_path):
            self._update_preview(image_path)
        
        self.update_bar_state("progress_current", step)
        self.update_bar_state("progress_total", total)
        self.update_bar_state("end_label", f"{step}/{total} шагов")
        
        self.step_updated.emit(step, total, image_path)
    
    def _on_generation_finished(self, final_path, seed):
        """Генерация завершена"""
        if final_path and os.path.exists(final_path):
            self._update_preview(final_path)
        
        self._resume_from_archive = False
        
        # Если был resume из архива — удаляем исходный архивный чекпоинт
        if self._archive_checkpoint_file:
            try:
                checkpoint_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "checkpoints"
                )
                json_path = os.path.join(checkpoint_dir, self._archive_checkpoint_file)
                pt_path = json_path.replace('.json', '.pt')
                
                if os.path.exists(json_path):
                    os.remove(json_path)
                if os.path.exists(pt_path):
                    os.remove(pt_path)
            except Exception:
                pass
            self._archive_checkpoint_file = None
        
        # Обновляем список чекпоинтов
        self.settings_panel.load_checkpoints_list()
        
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", "Готово")
        self.update_bar_state("progress_current", 0)
        self.update_bar_state("end_label", self.settings_panel.get_end_label())
        
        self.generation_finished.emit()
    
    def _on_error(self, error_msg):
        """Ошибка генерации"""
        self._resume_from_archive = False
        self._archive_checkpoint_file = None
        
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", f"Ошибка: {error_msg}")
        
        self.generation_error.emit(error_msg)
    
    def _on_status_message(self, message):
        """Добавляет статусное сообщение в бегущую строку"""
        self._append_to_status_buffer(message)
        
        # Эмитим сигнал для совместимости
        self.status_message.emit(message)
    
    def _check_checkpoint(self):
        """Проверяет наличие активного чекпоинта"""
        checkpoint_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "checkpoints"
        )
        json_path = os.path.join(checkpoint_dir, "checkpoint.json")
        pt_path = os.path.join(checkpoint_dir, "checkpoint.pt")
        
        if not os.path.exists(json_path) or not os.path.exists(pt_path):
            return None
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "prompt": data.get("prompt", ""),
                "model": os.path.basename(data.get("model", "")),
                "current_step": data.get("current_step", 0),
                "total_steps": data.get("total_steps", 0),
                "seed": data.get("seed", -1),
                "width": data.get("width", 0),
                "height": data.get("height", 0)
            }
        except Exception:
            return None
    
    def _update_preview(self, image_path):
        """Загружает изображение в QGraphicsView"""
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.scene.clear()
            item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(item)
            self.image_view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
    
    def _open_output_folder(self):
        """Открывает папку с сохранёнными изображениями"""
        output_dir = self.config.get_sdxl_output_dir()
        if os.path.exists(output_dir):
            subprocess.run(['xdg-open', output_dir])

# ════════════════════════════════════════════════════════════
# FILE: ui/tabs/__init__.py
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# FILE: ui/tabs/ollama_tab.py
# ════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import QWidget, QHBoxLayout
from ui.chat_widget import ChatWidget
from ui.settings_panel import SettingsPanel
from core.chat_manager import ChatManager
from core.ollama_client import OllamaClient
from PyQt6.QtCore import pyqtSignal
import requests


class OllamaTab(QWidget):
    """Вкладка Ollama с состоянием для SharedBottomBar"""

    # Универсальный сигнал для MainWindow
    state_changed = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.chat_manager = ChatManager()
        self.client = None
        self._current_response_text = ""
        self.last_stats = None

        # Состояние для SharedBottomBar
        self._bar_state = {
            "prompt": "",
            "progress_current": 0,
            "progress_total": 0,
            "status": "Готово",
            "end_label": "10 мин",
            "is_running": False
        }

        layout = QHBoxLayout(self)

        self.chat_widget = ChatWidget()
        self.settings_panel = SettingsPanel(self.config)

        layout.addWidget(self.chat_widget, 3)
        layout.addWidget(self.settings_panel, 1)

        self.settings_panel.clear_btn.clicked.connect(self.clear_chat)

        # Подключаем изменение timeout для обновления end_label
        self.settings_panel.timeout_spin.valueChanged.connect(self._on_timeout_changed)

        # Инициализируем end_label
        self._bar_state["end_label"] = self.get_end_label()

    def _on_timeout_changed(self, value):
        """Обновляет end_label при изменении timeout"""
        self._bar_state["end_label"] = self.get_end_label()
        self.state_changed.emit(self._bar_state.copy())

    def get_end_label(self) -> str:
        """Возвращает текст для end_label (например, '10 мин')"""
        timeout_minutes = self.settings_panel.timeout_spin.value() // 60
        return f"{timeout_minutes} мин"

    def get_bar_state(self) -> dict:
        """Возвращает копию состояния"""
        return self._bar_state.copy()

    def set_bar_state(self, state: dict):
        """Устанавливает состояние"""
        self._bar_state.update(state)
        self.state_changed.emit(self._bar_state.copy())

    def update_bar_state(self, key: str, value):
        """Обновляет одно поле и эмитит сигнал"""
        self._bar_state[key] = value
        self.state_changed.emit(self._bar_state.copy())

    def handle_prompt(self, text):
        """Обработка промпта из общей панели"""
        if not text:
            return

        # Обновляем состояние
        self.update_bar_state("prompt", text)
        self.update_bar_state("is_running", True)
        self.update_bar_state("status", "Генерация...")

        self.chat_manager.add_user_message(text)
        self.chat_widget.append_user_message(text)
        self.chat_widget.start_assistant_message()

        self._current_response_text = ""
        self.last_stats = None

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

    def on_token(self, token):
        """Получен токен"""
        self._current_response_text += token
        self.chat_widget.append_token(token)

        # Обновляем статус
        self.update_bar_state("status", f"Генерация... ({len(self._current_response_text)} символов)")

    def on_finished(self):
        """Генерация завершена"""
        self.chat_manager.add_assistant_message(self._current_response_text)
        self.settings_panel.save_settings()

        if self.last_stats:
            self.chat_widget.finalize_response(self.last_stats)
        else:
            self.chat_widget.finalize_response({})

        # Обновляем состояние
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", "Готово")

    def on_stats(self, stats_dict):
        """Получена статистика"""
        self.last_stats = stats_dict

    def on_error(self, error_msg):
        """Ошибка генерации"""
        self.chat_widget.append_token(f"\nОшибка: {error_msg}")

        # Обновляем состояние
        self.update_bar_state("is_running", False)
        self.update_bar_state("status", f"Ошибка: {error_msg}")

    def stop_generation(self):
        """Остановка генерации"""
        if self.client and self.client.isRunning():
            self.client.stop()

    def clear_chat(self):
        """Очистка чата"""
        self.chat_manager.clear()
        self.chat_widget.clear_chat()

    def unload(self):
        """Выгружает модель из памяти Ollama"""
        try:
            requests.post(f"{self.config.get_ollama_url()}/api/generate",
                         json={"model": self.settings_panel.model_combo.currentText(),
                               "keep_alive": 0},
                         timeout=5)
        except Exception:
            pass

# ════════════════════════════════════════════════════════════
# FILE: utils/config.py
# ════════════════════════════════════════════════════════════

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

# ════════════════════════════════════════════════════════════
# FILE: utils/__init__.py
# ════════════════════════════════════════════════════════════

