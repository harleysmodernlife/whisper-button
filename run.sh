#!/bin/bash
# Whisper Button Launcher — auto-creates a venv on first run
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "First run: setting up Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Installing dependencies (this may take a few minutes)..."
    "$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    echo "Setup complete."
fi

exec "$VENV_DIR/bin/python3" "$APP_DIR/app.py" "$@"
