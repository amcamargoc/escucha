#!/usr/bin/env python3
"""
Escucha CLI — Terminal Push-to-Talk client connecting to a WhisperFlow WebSocket server.
"""

import argparse
import asyncio
import json
import sys
import threading
import urllib.request
from typing import List, Optional

import websockets
from pynput import keyboard

from whisperflow import config as wf_config

from escucha import APP_NAME
from escucha.clipboard import paste_text_macos
from escucha.permissions import play_sound
from escucha.session import open_mic_stream

CLI_KEY_MAP = {
    "ctrl": (keyboard.Key.ctrl, keyboard.Key.ctrl_r),
    "right_shift": (keyboard.Key.shift_r,),
    "right_option": (keyboard.Key.alt_r,),
    "right_cmd": (keyboard.Key.cmd_r,),
    "f8": (keyboard.Key.f8,),
    "f9": (keyboard.Key.f9,),
    "f10": (keyboard.Key.f10,),
}


def check_server(http_url: str) -> dict:
    """Verify the WhisperFlow server is reachable at /ready."""
    with urllib.request.urlopen(f"{http_url}/ready", timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def run_ws_ptt_session(  # pylint: disable=too-many-statements
    ws_url: str,
    release_event: asyncio.Event,
    cancel_event: asyncio.Event,
    language: str,
    model: Optional[str],
) -> str:
    """Stream mic audio over WebSocket while held, then flush and return text."""
    loop = asyncio.get_running_loop()
    audio, stream = open_mic_stream()

    final_segments: List[str] = []
    last_partial: str = ""

    async def send_audio(ws):
        try:
            while not release_event.is_set() and not cancel_event.is_set():
                data = await loop.run_in_executor(
                    None,
                    lambda: stream.read(
                        wf_config.CHUNK_SIZE, exception_on_overflow=False
                    ),
                )
                await ws.send(data)
                await asyncio.sleep(0.001)
            if not cancel_event.is_set():
                await ws.send(json.dumps({"type": "stop"}))
            else:
                await ws.close()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    async def receive_transcripts(ws):
        nonlocal last_partial
        try:
            async for message in ws:
                if cancel_event.is_set():
                    break
                res = json.loads(message)
                if res.get("type") == "error":
                    continue
                text = res.get("data", {}).get("text", "").strip()
                if not text:
                    continue
                if res.get("is_partial", True):
                    last_partial = text
                    preview = f"{' '.join(final_segments)} {text}".strip()
                    sys.stdout.write(f"\r🎤 {preview[:80]:<80}")
                    sys.stdout.flush()
                else:
                    final_segments.append(text)
                    last_partial = ""
                    committed = " ".join(final_segments)
                    sys.stdout.write(f"\r⏳ {committed[:80]:<80}")
                    sys.stdout.flush()
        except websockets.ConnectionClosed:
            pass

    try:
        async with websockets.connect(ws_url) as ws:
            start_msg = {"type": "start", "language": language}
            if model:
                start_msg["model"] = model
            await ws.send(json.dumps(start_msg))
            await asyncio.gather(send_audio(ws), receive_transcripts(ws))
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    if cancel_event.is_set():
        return ""
    if not final_segments and last_partial:
        final_segments.append(last_partial)
    return " ".join(final_segments).strip()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Escucha CLI."""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} CLI — Push-to-Talk client for WhisperFlow"
    )
    parser.add_argument(
        "--host",
        default="localhost:8181",
        help="WhisperFlow host:port (default: localhost:8181)",
    )
    parser.add_argument(
        "--key",
        default="ctrl",
        choices=list(CLI_KEY_MAP.keys()),
        help="Push-to-Talk key (default: ctrl)",
    )
    parser.add_argument(
        "--lang", default="en", help="Whisper language code (default: en)"
    )
    parser.add_argument("--model", default=None, help="Optional model name from /ready")
    return parser.parse_args()


def main() -> None:  # pylint: disable=too-many-statements
    """Run the Escucha CLI Push-to-Talk client."""
    args = parse_args()
    http_url = f"http://{args.host}"
    ws_url = f"ws://{args.host}/ws"
    target_keys = CLI_KEY_MAP[args.key]

    try:
        ready_info = check_server(http_url)
        models_str = ", ".join(ready_info.get("models", []))
        print(
            f"✅ {APP_NAME} connected to WhisperFlow v{ready_info.get('version')} "
            f"at {http_url} (models: {models_str})"
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"❌ Could not reach WhisperFlow at {http_url}/ready: {exc}")
        sys.exit(1)

    print(f"🎙️  Hold [{args.key}] by itself to speak, release to paste.\n")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    state = {"recording": False, "release": None, "cancel": None}
    lock = threading.Lock()

    def start_recording():
        state["release"] = asyncio.Event()
        state["cancel"] = asyncio.Event()
        play_sound("Tink")
        sys.stdout.write(f"\r🔴 {'Listening...':<80}")
        sys.stdout.flush()

        async def _runner():
            try:
                transcript = await run_ws_ptt_session(
                    ws_url,
                    state["release"],
                    state["cancel"],
                    args.lang,
                    args.model,
                )
                if state["cancel"].is_set():
                    sys.stdout.write(f"\r⚪ {'(cancelled: shortcut pressed)':<80}\n")
                elif transcript:
                    play_sound("Pop")
                    sys.stdout.write(f"\r✅ {transcript:<80}\n")
                    paste_text_macos(transcript)
                else:
                    sys.stdout.write(f"\r⚪ {'(no speech detected)':<80}\n")
                sys.stdout.flush()
            finally:
                with lock:
                    state["recording"] = False

        asyncio.run_coroutine_threadsafe(_runner(), loop)

    def on_press(key):
        with lock:
            if key in target_keys and not state["recording"]:
                state["recording"] = True
                loop.call_soon_threadsafe(start_recording)
            elif key not in target_keys and state["recording"] and state["cancel"]:
                loop.call_soon_threadsafe(state["cancel"].set)

    def on_release(key):
        if key in target_keys and state["release"] is not None:
            loop.call_soon_threadsafe(state["release"].set)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print(f"\nStopping {APP_NAME}...")
    finally:
        listener.stop()
        loop.stop()


if __name__ == "__main__":
    main()
