# START_HERE — LocalAILite

Манифест для LLM-моделей, работающих над проектом.
Если ты новая модель — читай этот файл первым.

## Порядок чтения
1. Этот файл (правила, окружение, ограничения)
2. WORK/HANDOFF.md — что было в прошлой сессии
3. WORK/WORKLOG.md → раздел TODO — что делать
4. docs/STRUCTURE.md — структура проекта
5. Код по raw-ссылкам (см. ниже)

## Ограничения модели (ВАЖНО)
Модель НЕ имеет доступа к терминалу и файловой системе.
- Модель НЕ может выполнить команду, создать файл, сделать git push
- Модель читает файлы (raw-ссылки или загруженные в чат)
- Модель генерирует готовую команду для терминала
- Пользователь выполняет команду и показывает вывод
- Цикл: читаю → даю команду → пользователь выполняет → показывает вывод → анализирую

## Окружение
- Dev-машина: Manjaro Linux (Xeon E5450 без SSE4.2/AVX, 16 GB, Radeon RX 580)
- Путь проекта: /home/lin/Scripts/LocalAILite
- Repo (GitHub): /home/lin/Scripts/LocalAILite/Repo
- GitHub: https://github.com/korbendallas000wt/LocalAILite
- Python: venv на 3.12, системный 3.13
- Общение: неформальное, на "ты", имя пользователя Корбен

## Правила работы
- Все правки — командой замены кода для терминала с проверкой применения
- Бэкапы: /home/lin/Scripts/LocalAILite/Backup
- Коммиты: после каждого логически завершённого изменения
- Формат коммитов: feat: / fix: / refactor: / docs: / chore:

## Workflow разработки
1. Правки в рабочей папке /home/lin/Scripts/LocalAILite/
2. Тестирование (запуск из корня проекта)
3. Синхронизация: ./WORK/sync_repo.sh → копирует в Repo/
4. Коммит: cd Repo && git add . && git commit -m "..." && git push
5. На тестовой машине — скачать ZIP с GitHub

## Чтение файлов проекта
Структура: https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/docs/STRUCTURE.md
Шаблон raw-ссылки:
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/{ПУТЬ_ИЗ_STRUCTURE}
Пример для installer/detector.py:
  https://github.com/korbendallas000wt/LocalAILite/raw/refs/heads/main/installer/detector.py
Если 404 — проверь STRUCTURE.md, путь мог измениться.
Fallback: WORK/full_context.py (склейка всего кода).
Rate limit GitHub: 60 запросов/час без токена — читай выборочно.

## Когда пушить
- После каждого логически завершённого изменения
- ПЕРЕД переходом на другую тестовую машину
- В конце каждой сессии
- Перед экспериментальными правками (точка отката)

## Передача эстафеты
В конце каждой сессии обнови:
- WORK/WORKLOG.md — что сделано, баги, задачи
- WORK/HANDOFF.md — контекст для следующей модели
Эти файлы НЕ пушатся в GitHub (в .gitignore), но передаются между сессиями.

## Технические ограничения проекта
- numpy 2.x из pip НЕ работает на старом CPU (E5450) — нужен numpy<2 или системный из apt
- Для SDXL venv строго Python 3.12 (не 3.13, не 3.14)
- PyQt6 на старом CPU — только системный из пакетного менеджера
- torch CPU работает на E5450 без SSE4.2
- Гибридная схема Debian 13: системный 3.13 (UI) + портативный 3.12 (SDXL)
