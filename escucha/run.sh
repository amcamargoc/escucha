#!/bin/bash
# Escucha Product Runner (Menu Bar App, Tests, and CLI)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
MODELS_DIR="$REPO_ROOT/whisperflow-base/whisperflow/models"
export PYTHONPATH="$REPO_ROOT/whisperflow-base:$SCRIPT_DIR:${PYTHONPATH:-}"

cd "$SCRIPT_DIR"

ensure_venv() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        echo "First-time setup for Escucha: checking PortAudio and creating Python environment..."
        if command -v brew >/dev/null 2>&1 && ! brew list portaudio >/dev/null 2>&1; then
            brew install portaudio
        fi
        PYTHON_CMD="python3"
        if command -v python3.12 >/dev/null 2>&1; then
            PYTHON_CMD="python3.12"
        fi
        $PYTHON_CMD -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip wheel "setuptools<70"
        pip install -r "$REPO_ROOT/whisperflow-base/requirements-dev.txt"
        pip install -r "$SCRIPT_DIR/requirements.txt"
    else
        source "$VENV_DIR/bin/activate"
    fi
}

if [ "${1:-}" = "-start" ] || [ "$#" -eq 0 ]; then
    ensure_venv
    if [ ! -f "$MODELS_DIR/base.en.pt" ]; then
        echo "Downloading recommended Whisper model for Escucha (base.en.pt, 139 MB)..."
        python -c "import whisper; whisper._download(whisper._MODELS['base.en'], '$MODELS_DIR', False)"
    fi
    echo "Launching Escucha in your macOS Menu Bar (🎙️)..."
    pkill -f "escucha.menubar" 2>/dev/null || true
    nohup "$VENV_DIR/bin/python" -m escucha.menubar >/dev/null 2>&1 &
    echo "✅ Escucha is running! Look for 🎙️ in the top-right macOS Menu Bar."
elif [ "$1" = "-test" ]; then
    ensure_venv
    echo "Running format, linter, and QA tests for Escucha..."
    black "$SCRIPT_DIR/escucha" "$SCRIPT_DIR/tests"
    pylint --fail-under=9.9 "$SCRIPT_DIR/escucha" "$SCRIPT_DIR/tests"
    pytest -v "$SCRIPT_DIR/tests"
    echo "Running format, linter, and unit tests for WhisperFlow Base..."
    (cd "$REPO_ROOT/whisperflow-base" && ./run.sh -test)
elif [ "$1" = "-cli" ]; then
    ensure_venv
    shift
    exec "$VENV_DIR/bin/python" -m escucha.cli "$@"
else
    echo "Usage: ./run.sh [-start | -test | -cli]"
    exit 1
fi
