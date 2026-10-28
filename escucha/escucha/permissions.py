"""
macOS system permissions (Input Monitoring, Accessibility) and audio feedback for Escucha.
"""

# pylint: disable=no-member

import subprocess
import Quartz


def check_macos_permissions(prompt: bool = False) -> dict:
    """Check (and optionally request) macOS Input Monitoring and Accessibility permissions."""
    listen_ok = bool(Quartz.CGPreflightListenEventAccess())
    post_ok = bool(Quartz.CGPreflightPostEventAccess())
    if prompt:
        if not listen_ok:
            Quartz.CGRequestListenEventAccess()
        if not post_ok:
            Quartz.CGRequestPostEventAccess()
    return {"input_monitoring": listen_ok, "accessibility": post_ok}


def open_macos_privacy_settings(_sender=None) -> None:
    """Open macOS System Settings -> Privacy & Security -> Accessibility."""
    subprocess.run(
        [
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ],
        check=False,
    )


def play_sound(name: str, enabled: bool = True) -> None:
    """Play a subtle macOS system sound ('Tink' on start, 'Pop' on finish)."""
    if not enabled:
        return
    try:
        # pylint: disable=consider-using-with
        subprocess.Popen(
            ["afplay", "-v", "0.4", f"/System/Library/Sounds/{name}.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
