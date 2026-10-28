"""
macOS clipboard preservation and active-window text injection for Escucha.
"""

# pylint: disable=no-member

import logging
import subprocess
import time
from typing import Optional

import Quartz
import rumps

from escucha import APP_NAME

LOG = logging.getLogger(__name__)


def get_clipboard_macos() -> Optional[bytes]:
    """Read current plain-text clipboard contents so we can restore it after pasting."""
    try:
        res = subprocess.run(["pbpaste"], capture_output=True, timeout=1.0, check=False)
        if res.returncode == 0:
            return res.stdout
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


def set_clipboard_macos(data: bytes) -> None:
    """Write raw bytes to the macOS clipboard."""
    subprocess.run(["pbcopy"], input=data, timeout=1.0, check=True)


def wait_for_modifiers_clear(timeout: float = 0.25) -> None:
    """Wait briefly until PTT modifier keys are released so Cmd+V doesn't become Ctrl+Cmd+V."""
    deadline = time.monotonic() + timeout
    mask = (
        Quartz.kCGEventFlagMaskControl
        | Quartz.kCGEventFlagMaskAlternate
        | Quartz.kCGEventFlagMaskShift
    )
    while time.monotonic() < deadline:
        flags = Quartz.CGEventSourceFlagsState(
            Quartz.kCGEventSourceStateCombinedSessionState
        )
        if not flags & mask:
            break
        time.sleep(0.015)


def paste_text_macos(text: str, preserve_clipboard: bool = True) -> bool:
    """
    Paste text into the active macOS window via Cmd+V while preserving
    the user's previous clipboard contents. If Accessibility is not enabled,
    leaves the text on the clipboard and notifies the user.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return False
    payload = (cleaned + " ").encode("utf-8")

    previous_clipboard = get_clipboard_macos() if preserve_clipboard else None
    try:
        wait_for_modifiers_clear()
        set_clipboard_macos(payload)
        time.sleep(0.03)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            timeout=2.0,
            check=True,
        )
        if previous_clipboard is not None:
            time.sleep(0.18)
            set_clipboard_macos(previous_clipboard)
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOG.warning("Failed to auto-paste text (left on clipboard): %s", exc)
        try:
            rumps.notification(
                APP_NAME,
                "Copied to Clipboard (Press ⌘V)",
                "Enable Accessibility in System Settings for automatic pasting.",
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False
