#!/bin/bash
# get_context.sh — точечная выгрузка файлов для LLM
# Использование:
#   ./get_context.sh core/diffusers_worker.py ui/tabs/diffusers_tab.py
#   ./get_context.sh --list          # список всех .py файлов
#   ./get_context.sh --grep "def stop"  # найти функцию во всех файлах

PROJECT="/home/lin/Scripts/LocalAILite"
OUTPUT="$PROJECT/context_selection.py"

if [ "$1" == "--list" ]; then
    echo "=== Файлы проекта ==="
    find "$PROJECT" -name "*.py" \
        -not -path "*/__pycache__/*" \
        -not -path "*/Repo/*" \
        -not -path "*/bin/*" \
        -not -path "*/venv/*" \
        -not -path "*/Backup/*" \
        -not -path "*/data/*" \
        -not -name "full_context.py" \
        -not -name "full_docs.py" \
        -not -name "context_selection.py" \
        -not -name "merge_docs.py" \
        -type f | sort | while read f; do
        rel="${f#$PROJECT/}"
        lines=$(wc -l < "$f")
        echo "  $rel  ($lines строк)"
    done
    exit 0
fi

if [ "$1" == "--grep" ]; then
    shift
    echo "=== Поиск: $* ==="
    grep -rn "$*" "$PROJECT" --include="*.py" \
        --exclude-dir=__pycache__ --exclude-dir=Repo \
        --exclude-dir=bin --exclude-dir=venv \
        --exclude-dir=Backup --exclude-dir=data \
        --exclude=full_context.py --exclude=full_docs.py \
        --exclude=context_selection.py
    exit 0
fi

if [ $# -eq 0 ]; then
    echo "Использование:"
    echo "  $0 файл1.py файл2.py ...   — склейка выбранных файлов"
    echo "  $0 --list                   — список всех файлов"
    echo "  $0 --grep 'текст'           — поиск по коду"
    exit 1
fi

echo "# === LOCAL AI LITE - CONTEXT SELECTION ===" > "$OUTPUT"
echo "# Generated: $(date)" >> "$OUTPUT"
echo "# Files: $*" >> "$OUTPUT"
echo "" >> "$OUTPUT"

for rel in "$@"; do
    full="$PROJECT/$rel"
    if [ ! -f "$full" ]; then
        echo "⚠ Файл не найден: $rel" >&2
        continue
    fi
    echo "" >> "$OUTPUT"
    echo "# ════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "# FILE: $rel" >> "$OUTPUT"
    echo "# ════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    cat "$full" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
done

lines=$(wc -l < "$OUTPUT")
echo "✅ Сохранено $lines строк в $OUTPUT"
