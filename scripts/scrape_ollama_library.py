#!/usr/bin/env python3
"""
Скрипт сбора описаний моделей со страницы библиотеки.
Парсит карточки моделей, извлекает имя и описание, сохраняет в JSON.

Использование:
    python3 scripts/scrape_ollama_library.py

Результат:
    /tmp/ollama_library_descriptions.json
"""

import json
import re
import sys

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Требуется: pip install requests beautifulsoup4")
    sys.exit(1)

LIBRARY_URL = "https://ollama.com/library"
OUTPUT_FILE = "/tmp/ollama_library_descriptions.json"

def fetch_library_page():
    """Загружает страницу библиотеки."""
    print(f"Загружаю {LIBRARY_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(LIBRARY_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_models(html):
    """Парсит карточки моделей из HTML."""
    soup = BeautifulSoup(html, "html.parser")
    models = []

    # Ищем карточки моделей (обычно это <li> с классом, содержащим имя модели)
    # Структура страницы может меняться, пробуем несколько селекторов

    # Вариант 1: ищем все ссылки на модели вида /library/{model_name}
    links = soup.find_all("a", href=re.compile(r"^/library/[\w.-]+$"))
    seen = set()

    for link in links:
        href = link.get("href", "")
        model_name = href.replace("/library/", "").strip()
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)

        # Пытаемся найти описание рядом со ссылкой
        # Обычно описание в родительском элементе или соседнем <p>
        parent = link.find_parent(["li", "div", "article"])
        description = ""

        if parent:
            # Ищем <p> или текст в родительском элементе
            p_tags = parent.find_all("p")
            for p in p_tags:
                text = p.get_text(strip=True)
                # Пропускаем метаданные (размер, теги)
                if text and not re.match(r"^[\d.]+[KMG]? Pulls", text, re.I):
                    description = text
                    break

            # Если не нашли в <p>, пробуем взять текст напрямую
            if not description:
                text = parent.get_text(separator=" ", strip=True)
                # Извлекаем только осмысленную часть (не метаданные)
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                for line in lines:
                    if len(line) > 20 and not re.search(r"\b\d+[KMG]?\s+Pulls\b", line, re.I):
                        description = line
                        break

        models.append({
            "name": model_name,
            "source": model_name,
            "description_en": description
        })

    return models

def main():
    try:
        html = fetch_library_page()
        models = parse_models(html)

        if not models:
            print("Не удалось найти модели на странице. Структура могла измениться.")
            print("Попробуй открыть страницу вручную и проверить структуру.")
            sys.exit(1)

        print(f"Собрано моделей: {len(models)}")
        print(f"Примеры:")
        for m in models[:5]:
            desc = m["description_en"][:80] + "..." if len(m["description_en"]) > 80 else m["description_en"]
            print(f"  {m['name']}: {desc or '(нет описания)'}")

        # Сохраняем в JSON
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(models, f, ensure_ascii=False, indent=2)

        print(f"\nСохранено в {OUTPUT_FILE}")
        print(f"Теперь посмотри файл и реши, какие модели добавить в каталог.")

    except requests.RequestException as e:
        print(f"Ошибка запроса: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
