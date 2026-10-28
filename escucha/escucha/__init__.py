"""
Escucha — Voice Dictation & Push-to-Talk Application built on WhisperFlow.
"""

import sys
from pathlib import Path

# Ensure the sibling `whisperflow-base` directory is importable regardless of working directory
_BASE_ENGINE_DIR = Path(__file__).resolve().parents[2] / "whisperflow-base"
if _BASE_ENGINE_DIR.is_dir() and str(_BASE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_ENGINE_DIR))

APP_NAME = "Escucha"
BUNDLE_ID = "com.escucha.app"
__version__ = "1.0.0"
