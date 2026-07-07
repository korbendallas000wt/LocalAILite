#!/bin/bash
# save_context.sh
OUTPUT="/home/lin/Scripts/LocalAILite/full_context.py"

echo "# === LOCAL AI LITE - FULL CONTEXT ===" > "$OUTPUT"
echo "# Generated: $(date)" >> "$OUTPUT"
echo "# Usage: grep 'def method_name' full_context.py" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Исключаем временные файлы, кэш, бэкапы
find /home/lin/Scripts/LocalAILite \
    -name "*.py" \
    -not -path "*/__pycache__/*" \
    -not -path "*/_Repo/*" \
    -not -path "*/bin/*" \
    -not -path "*/venv/*" \
    -not -path "*/Backup/*" \
    -not -path "*/data/*" \
    -not -name "full_context.py" \
    -type f | sort | while read file; do

    rel_path="${file#/home/lin/Scripts/LocalAILite/}"
    echo "" >> "$OUTPUT"
    echo "# ════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "# FILE: $rel_path" >> "$OUTPUT"
    echo "# ════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    cat "$file" >> "$OUTPUT"
done

lines=$(wc -l < "$OUTPUT")
echo "✅ Сохранено $lines строк в $OUTPUT"
