#!/bin/bash
# install.sh — точка входа инсталлера LocalAILite
# Запуск: ./install.sh или bash install.sh
#
# Что делает:
# 1. Проверяет наличие Python 3
# 2. Запускает installer/cli.py с теми же аргументами
#
# Идемпотентен: можно запускать повторно — пропустит уже установленное.

set -e  # Выход при ошибке

# Определяем папку скрипта (чтобы работало из любой директории)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Проверяем Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден в системе."
    echo ""
    echo "Установите Python 3 через пакетный менеджер:"
    echo "  • Manjaro/Arch:    sudo pacman -S python"
    echo "  • Fedora:          sudo dnf install python3"
    echo "  • Debian/Ubuntu:   sudo apt install python3"
    echo "  • openSUSE:        sudo zypper install python3"
    exit 1
fi

# Проверяем минимальную версию Python (3.8+ для инсталлера)
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MINOR" -lt 8 ]]; then
    echo "⚠ Python $PYTHON_VERSION слишком старый (требуется 3.8+)."
    echo "  Это не критично для инсталлера, но приложение требует Python 3.10+."
    echo ""
fi

# Запускаем инсталлер, передаём все аргументы
echo "LocalAILite Installer"
echo "======================"
echo ""
exec python3 installer/cli.py "$@"
