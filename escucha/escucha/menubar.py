#!/usr/bin/env python3
"""
Escucha — Native macOS Menu Bar Dictation Application.

Runs the Escucha Push-to-Talk experience inside a macOS Menu Bar icon (🎙️)
powered by the base `whisperflow` transcription engine.
"""

# pylint: disable=no-member,too-many-instance-attributes

import asyncio
import logging
import threading
from functools import partial
from typing import Callable, Dict, Optional

import AppKit
import Quartz
import rumps
from PyObjCTools import AppHelper

import whisperflow.transcriber as ts

from escucha import APP_NAME
from escucha.clipboard import paste_text_macos, set_clipboard_macos
from escucha.config import DOWNLOADABLE_MODELS, HOTKEY_PRESETS
from escucha.permissions import (
    check_macos_permissions,
    open_macos_privacy_settings,
    play_sound,
)
from escucha.session import (
    download_whisper_model,
    run_ptt_session,
    select_default_model,
)

LOG = logging.getLogger(__name__)


class EscuchaMenuBarApp(rumps.App):
    """Native macOS Menu Bar app for Escucha Push-to-Talk dictation."""

    def __init__(self, start_services: bool = True) -> None:
        super().__init__("🎙️", quit_button=None)

        self.current_model_name = select_default_model()
        self.current_hotkey_id = "ctrl"
        self.sound_enabled = True
        self.last_transcript = ""

        # Synchronization & state machine
        self.lock = threading.Lock()
        self.key_is_down = False
        self.is_recording = False
        self.is_loading_model = False
        self.release_event: Optional[asyncio.Event] = None
        self.cancel_event: Optional[asyncio.Event] = None
        self.event_tap = None

        # Dedicated asyncio loop in a background thread
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.loop_thread.start()

        # Build Menu UI
        self.status_item = rumps.MenuItem(f"⏳ {APP_NAME}: Loading Whisper model...")
        self.permissions_item = rumps.MenuItem(
            "⚙️ macOS Privacy & Accessibility Settings...",
            callback=open_macos_privacy_settings,
        )
        self.last_text_item = rumps.MenuItem(
            "Last: (none yet)", callback=self.copy_last_transcript
        )

        # Hotkey submenu
        self.hotkey_menu = rumps.MenuItem("Push-to-Talk Key")
        self.hotkey_items: Dict[str, rumps.MenuItem] = {}
        for key_id, info in HOTKEY_PRESETS.items():
            item = rumps.MenuItem(
                info["label"], callback=partial(self.select_hotkey, key_id)
            )
            item.state = int(key_id == self.current_hotkey_id)
            self.hotkey_items[key_id] = item
            self.hotkey_menu.add(item)

        # Model submenu
        self.model_menu = rumps.MenuItem("Whisper Model")
        self.model_items: Dict[str, rumps.MenuItem] = {}
        self._rebuild_model_menu()

        # Sound toggle
        self.sound_item = rumps.MenuItem("Sound Effects", callback=self.toggle_sound)
        self.sound_item.state = int(self.sound_enabled)

        self.menu = [
            self.status_item,
            self.last_text_item,
            None,
            self.hotkey_menu,
            self.model_menu,
            self.sound_item,
            self.permissions_item,
            None,
            rumps.MenuItem(f"Quit {APP_NAME}", callback=self.quit_app),
        ]

        if start_services:
            check_macos_permissions(prompt=True)
            asyncio.run_coroutine_threadsafe(
                self._load_model_async(self.current_model_name), self.loop
            )
            self.tap_thread = threading.Thread(
                target=self._run_quartz_key_tap, daemon=True
            )
            self.tap_thread.start()

    def _ui(self, fn: Callable[[], None]) -> None:
        """Execute UI updates safely on the main Cocoa thread."""
        if threading.current_thread() is threading.main_thread():
            fn()
        else:
            try:
                AppHelper.callAfter(fn)
            except Exception:  # pylint: disable=broad-exception-caught
                fn()

    def _run_async_loop(self) -> None:
        """Run the background asyncio event loop."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _rebuild_model_menu(self) -> None:
        """Populate the Whisper Model submenu with installed and downloadable models."""
        if getattr(self.model_menu, "_menu", None) is not None:
            self.model_menu.clear()
        self.model_items.clear()

        for model_name in ts.list_models():
            item = rumps.MenuItem(
                model_name, callback=partial(self.select_model, model_name)
            )
            item.state = int(model_name == self.current_model_name)
            self.model_items[model_name] = item
            self.model_menu.add(item)

        missing_downloads = [
            (key, filename, label)
            for key, filename, label in DOWNLOADABLE_MODELS
            if filename not in self.model_items
        ]
        if missing_downloads:
            self.model_menu.add(None)
            for key, filename, label in missing_downloads:
                self.model_menu.add(
                    rumps.MenuItem(
                        label,
                        callback=partial(self.download_model, key, filename),
                    )
                )

    def _update_idle_status(self) -> None:
        """Restore the Menu Bar icon and status text to the ready state."""
        label = HOTKEY_PRESETS[self.current_hotkey_id]["label"]
        perms = check_macos_permissions(prompt=False)

        def _apply():
            if not perms["input_monitoring"]:
                self.title = "⚠️"
                self.status_item.title = (
                    "⚠️ Enable Input Monitoring in Privacy Settings"
                )
            else:
                self.title = "🎙️"
                self.status_item.title = f"{APP_NAME} Ready — Hold {label} to speak"

        self._ui(_apply)

    async def _load_model_async(self, model_name: str) -> None:
        """Load a Whisper model checkpoint in the background executor."""
        with self.lock:
            if self.is_loading_model:
                return
            self.is_loading_model = True

        self._ui(
            lambda: (
                setattr(self, "title", "⏳"),
                setattr(self.status_item, "title", f"Loading {model_name}..."),
            )
        )
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, ts.get_model, model_name
            )
            self.current_model_name = model_name

            def _update_checks():
                for name, item in self.model_items.items():
                    item.state = int(name == model_name)

            self._ui(_update_checks)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOG.exception("Failed to load model %s: %s", model_name, exc)
        finally:
            with self.lock:
                self.is_loading_model = False
            self._update_idle_status()

    def select_hotkey(self, key_id: str, _sender) -> None:
        """Switch the active Push-to-Talk key preset."""
        if key_id not in HOTKEY_PRESETS:
            return
        self.current_hotkey_id = key_id
        for k, item in self.hotkey_items.items():
            item.state = int(k == key_id)
        self._update_idle_status()

    def select_model(self, model_name: str, _sender) -> None:
        """Switch the active Whisper model."""
        with self.lock:
            if self.is_loading_model or self.is_recording:
                return
        asyncio.run_coroutine_threadsafe(self._load_model_async(model_name), self.loop)

    def download_model(self, model_key: str, filename: str, _sender) -> None:
        """Download a Whisper model checkpoint and activate it."""
        with self.lock:
            if self.is_loading_model or self.is_recording:
                return
            self.is_loading_model = True

        async def _dl():
            self._ui(
                lambda: (
                    setattr(self, "title", "⬇️"),
                    setattr(self.status_item, "title", f"Downloading {filename}..."),
                )
            )
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, download_whisper_model, model_key
                )
                self._ui(self._rebuild_model_menu)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOG.exception("Model download failed: %s", exc)
                with self.lock:
                    self.is_loading_model = False
                self._update_idle_status()
                return

            with self.lock:
                self.is_loading_model = False
            await self._load_model_async(filename)

        asyncio.run_coroutine_threadsafe(_dl(), self.loop)

    def toggle_sound(self, sender) -> None:
        """Toggle start/stop audio cues on or off."""
        self.sound_enabled = not self.sound_enabled
        sender.state = int(self.sound_enabled)

    def copy_last_transcript(self, _sender) -> None:
        """Copy the most recent dictated phrase back to the macOS clipboard."""
        if self.last_transcript:
            set_clipboard_macos(self.last_transcript.encode("utf-8"))
            rumps.notification(
                APP_NAME,
                "Copied to Clipboard",
                self.last_transcript,
            )

    def quit_app(self, _sender) -> None:
        """Quit the Escucha Menu Bar application."""
        rumps.quit_application()

    async def run_local_ptt_session(
        self, release_event: asyncio.Event, cancel_event: asyncio.Event
    ) -> str:
        """Run a Push-to-Talk session and update the Menu Bar UI states."""
        return await run_ptt_session(
            model_name=self.current_model_name,
            release_event=release_event,
            cancel_event=cancel_event,
            sound_enabled=self.sound_enabled,
            on_listening=lambda: self._ui(
                lambda: (
                    setattr(self, "title", "🔴"),
                    setattr(
                        self.status_item,
                        "title",
                        "🔴 Listening... (Release key to paste)",
                    ),
                )
            ),
            on_partial=lambda text: self._ui(
                partial(setattr, self.status_item, "title", f"🎤 {text[:55]}")
            ),
            on_finalizing=lambda: self._ui(
                lambda: (
                    setattr(self, "title", "⏳"),
                    setattr(self.status_item, "title", "⏳ Finalizing speech..."),
                )
            ),
        )

    def handle_key_press(self) -> None:
        """Thread-safe handler when the Push-to-Talk key is pressed."""
        with self.lock:
            self.key_is_down = True
            if self.is_recording or self.is_loading_model:
                return
            self.is_recording = True
            release_ev = asyncio.Event()
            cancel_ev = asyncio.Event()
            self.release_event = release_ev
            self.cancel_event = cancel_ev

        async def _session_runner():
            try:
                with self.lock:
                    if not self.key_is_down:
                        release_ev.set()

                transcript = await self.run_local_ptt_session(release_ev, cancel_ev)
                if transcript and not cancel_ev.is_set():
                    self.last_transcript = transcript
                    short = (
                        transcript[:42] + "..." if len(transcript) > 42 else transcript
                    )
                    self._ui(
                        partial(setattr, self.last_text_item, "title", f"Last: {short}")
                    )
                    play_sound("Pop", self.sound_enabled)
                    paste_text_macos(transcript)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOG.exception("Error in PTT session: %s", exc)
            finally:
                self._update_idle_status()
                with self.lock:
                    self.is_recording = False

        asyncio.run_coroutine_threadsafe(_session_runner(), self.loop)

    def handle_key_release(self) -> None:
        """Thread-safe handler when the Push-to-Talk key is released."""
        with self.lock:
            self.key_is_down = False
            release_ev = self.release_event
        if release_ev is not None:
            self.loop.call_soon_threadsafe(release_ev.set)

    def handle_other_key_down(self) -> None:
        """Cancel active recording when another key is pressed (e.g., Ctrl+C)."""
        with self.lock:
            cancel_ev = self.cancel_event if self.is_recording else None
        if cancel_ev is not None:
            self.loop.call_soon_threadsafe(cancel_ev.set)

    def quartz_event_callback(self, _proxy, event_type, event, _refcon):
        """Process raw Quartz CGEventTap events including timeout recovery."""
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self.event_tap is not None:
                Quartz.CGEventTapEnable(self.event_tap, True)
            return event

        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )
        preset = HOTKEY_PRESETS[self.current_hotkey_id]
        target_codes = preset["keycodes"]
        flag_mask = preset["flag_mask"]

        if flag_mask is not None:
            if event_type == Quartz.kCGEventFlagsChanged and keycode in target_codes:
                flags = Quartz.CGEventGetFlags(event)
                if bool(flags & flag_mask):
                    self.handle_key_press()
                else:
                    self.handle_key_release()
            elif event_type == Quartz.kCGEventKeyDown and keycode not in target_codes:
                self.handle_other_key_down()
        elif keycode in target_codes:
            if event_type == Quartz.kCGEventKeyDown:
                self.handle_key_press()
            elif event_type == Quartz.kCGEventKeyUp:
                self.handle_key_release()

        return event

    def _run_quartz_key_tap(self) -> None:
        """Listen for global key press/release via macOS Quartz CGEventTap."""
        mask = (
            (1 << Quartz.kCGEventFlagsChanged)
            | (1 << Quartz.kCGEventKeyDown)
            | (1 << Quartz.kCGEventKeyUp)
        )
        self.event_tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self.quartz_event_callback,
            None,
        )
        if self.event_tap is None:
            LOG.error(
                "Failed to create Quartz CGEventTap (check Input Monitoring permission)"
            )
            self._update_idle_status()
            return
        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self.event_tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(),
            run_loop_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(self.event_tap, True)
        Quartz.CFRunLoopRun()


def main() -> None:
    """Launch the Escucha macOS Menu Bar app without a Dock icon."""
    AppKit.NSApplication.sharedApplication().setActivationPolicy_(
        AppKit.NSApplicationActivationPolicyAccessory
    )
    EscuchaMenuBarApp().run()


if __name__ == "__main__":
    main()
