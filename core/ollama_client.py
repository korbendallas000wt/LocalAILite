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
