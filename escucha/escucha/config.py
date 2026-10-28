"""
Configuration, hotkey presets, timing constants, and hallucination filters for Escucha.
"""

# pylint: disable=no-member

from typing import Dict
import Quartz

# Recording & Push-to-Talk timing parameters
HOLD_DEBOUNCE_SECONDS = (
    0.18  # Wait 180ms before activating mic/beep (avoids Ctrl+C beeps)
)
TAIL_PADDING_SECONDS = (
    0.08  # Keep recording 80ms after key-up so final consonant isn't clipped
)
MIN_SPEECH_CHUNKS = 3  # Minimum non-silent chunks (~190ms) required to transcribe
MAX_HOLD_SECONDS = 60.0  # Safety cap if OS drops a key-up event (e.g., screen lock)
PREVIEW_INTERVAL_SECONDS = 0.45

# Default Whisper model preference order for Escucha
PREFERRED_MODELS = ("base.en.pt", "small.en.pt", "tiny.en.pt")

# Downloadable model catalog shown in the Escucha Menu Bar
DOWNLOADABLE_MODELS = (
    ("base.en", "base.en.pt", "⬇️ Download base.en.pt (139 MB - Recommended)"),
    ("small.en", "small.en.pt", "⬇️ Download small.en.pt (461 MB - High Accuracy)"),
)

# Common Whisper hallucinations on near-silent / short audio bursts
HALLUCINATION_PHRASES = {
    "you",
    "you.",
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching.",
    "thanks for watching!",
    "bye",
    "bye.",
    "subtitles by the amara.org community",
    "[blank_audio]",
    ".",
    "...",
}

# Push-to-Talk key presets for macOS Quartz CGEventTap
HOTKEY_PRESETS: Dict[str, dict] = {
    "ctrl": {
        "label": "Control (^)",
        "keycodes": {59, 62},
        "flag_mask": Quartz.kCGEventFlagMaskControl,
    },
    "right_option": {
        "label": "Right Option (⌥)",
        "keycodes": {61},
        "flag_mask": Quartz.kCGEventFlagMaskAlternate,
    },
    "right_shift": {
        "label": "Right Shift (⇧)",
        "keycodes": {60},
        "flag_mask": Quartz.kCGEventFlagMaskShift,
    },
    "right_cmd": {
        "label": "Right Command (⌘)",
        "keycodes": {54},
        "flag_mask": Quartz.kCGEventFlagMaskCommand,
    },
    "f8": {
        "label": "F8 Key",
        "keycodes": {100},
        "flag_mask": None,
    },
    "f9": {
        "label": "F9 Key",
        "keycodes": {101},
        "flag_mask": None,
    },
}
