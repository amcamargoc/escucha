"""
QA & Unit Test Suite for the Escucha Dictation Application (`escucha/`).
Tests edge cases: debounce, shortcut cancellation, silence/hallucination filtering,
clipboard preservation, CGEventTap timeout recovery, and race conditions.
"""

# pylint: disable=no-member

import asyncio
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import Quartz

import escucha.clipboard as esc_clip
import escucha.menubar as esc_mb
import escucha.session as esc_sess


def make_pcm_chunk(amplitude: int = 0) -> bytes:
    """Create a 1024-sample int16 PCM chunk with the given amplitude."""
    arr = np.full(1024, amplitude, dtype=np.int16)
    return arr.tobytes()


def test_hallucination_filter():
    """Verify silence and short-burst Whisper hallucinations are filtered out."""
    assert esc_sess.is_hallucination("", speech_chunk_count=10) is True
    assert esc_sess.is_hallucination("Hello world", speech_chunk_count=2) is True
    assert esc_sess.is_hallucination("Thank you.", speech_chunk_count=5) is True
    assert (
        esc_sess.is_hallucination("thanks for watching!", speech_chunk_count=8) is True
    )
    assert esc_sess.is_hallucination("you", speech_chunk_count=4) is True
    assert esc_sess.is_hallucination("[BLANK_AUDIO]", speech_chunk_count=10) is True
    assert esc_sess.is_hallucination("run tests", speech_chunk_count=6) is False
    assert esc_sess.is_hallucination("Thank you.", speech_chunk_count=20) is False


@patch("escucha.clipboard.subprocess.run")
@patch("escucha.clipboard.wait_for_modifiers_clear")
@patch("escucha.clipboard.time.sleep")
def test_clipboard_preservation(_mock_sleep, _mock_wait, mock_run):
    """Verify paste_text_macos saves and restores the user's previous clipboard."""
    calls = []

    def side_effect(cmd, **kwargs):
        calls.append((cmd, kwargs.get("input")))
        res = MagicMock()
        res.returncode = 0
        if cmd == ["pbpaste"]:
            res.stdout = b"https://secret-copied-url.example.com"
        return res

    mock_run.side_effect = side_effect
    ok = esc_clip.paste_text_macos(
        "  Hello   from   Escucha  ", preserve_clipboard=True
    )
    assert ok is True
    assert calls[0][0] == ["pbpaste"]
    assert calls[1] == (["pbcopy"], b"Hello from Escucha ")
    assert calls[2][0][0] == "osascript"
    assert calls[3] == (["pbcopy"], b"https://secret-copied-url.example.com")


@pytest.mark.asyncio
async def test_quick_tap_debounce_does_not_open_mic_or_beep():
    """Verify tapping Control for <180ms does not open PyAudio or play a sound."""
    app = esc_mb.EscuchaMenuBarApp(start_services=False)
    release_ev = asyncio.Event()
    cancel_ev = asyncio.Event()

    with patch("escucha.session.pyaudio.PyAudio") as mock_pyaudio, patch(
        "escucha.session.play_sound"
    ) as mock_sound:
        asyncio.get_running_loop().call_later(0.03, release_ev.set)
        result = await app.run_local_ptt_session(release_ev, cancel_ev)
        assert result == ""
        mock_pyaudio.assert_not_called()
        mock_sound.assert_not_called()


@pytest.mark.asyncio
async def test_shortcut_combo_cancels_recording():
    """Verify pressing another key (e.g. Ctrl+C) cancels recording without pasting."""
    app = esc_mb.EscuchaMenuBarApp(start_services=False)
    release_ev = asyncio.Event()
    cancel_ev = asyncio.Event()

    mock_stream = MagicMock()
    mock_stream.read.return_value = make_pcm_chunk(2000)
    mock_audio = MagicMock()
    mock_audio.open.return_value = mock_stream

    with patch("escucha.config.HOLD_DEBOUNCE_SECONDS", 0.01), patch(
        "escucha.session.pyaudio.PyAudio", return_value=mock_audio
    ), patch("escucha.session.play_sound"), patch(
        "escucha.session.ts.get_model"
    ), patch(
        "escucha.session.ts.transcribe_pcm_chunks_async"
    ) as mock_transcribe:
        asyncio.get_running_loop().call_later(0.05, cancel_ev.set)
        result = await app.run_local_ptt_session(release_ev, cancel_ev)
        assert result == ""
        mock_transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_full_utterance_transcribed_once_without_word_duplication():
    """Verify a hold with speech + pause + speech produces a single clean transcript."""
    app = esc_mb.EscuchaMenuBarApp(start_services=False)
    release_ev = asyncio.Event()
    cancel_ev = asyncio.Event()

    chunk_sequence = (
        [make_pcm_chunk(3000)] * 6
        + [make_pcm_chunk(0)] * 4
        + [make_pcm_chunk(3000)] * 6
    )
    idx = 0

    def read_chunk(*_args, **_kwargs):
        nonlocal idx
        if idx < len(chunk_sequence):
            chunk = chunk_sequence[idx]
            idx += 1
            if idx == len(chunk_sequence):
                release_ev.set()
            return chunk
        return make_pcm_chunk(0)

    mock_stream = MagicMock()
    mock_stream.read.side_effect = read_chunk
    mock_audio = MagicMock()
    mock_audio.open.return_value = mock_stream

    async def fake_transcribe(_model, _chunks, _lang):
        return {"text": " Try out edge cases and see how it behaves."}

    with patch("escucha.config.HOLD_DEBOUNCE_SECONDS", 0.01), patch(
        "escucha.session.pyaudio.PyAudio", return_value=mock_audio
    ), patch("escucha.session.play_sound"), patch(
        "escucha.session.ts.get_model"
    ), patch(
        "escucha.session.ts.transcribe_pcm_chunks_async", side_effect=fake_transcribe
    ):
        result = await app.run_local_ptt_session(release_ev, cancel_ev)
        assert result == "Try out edge cases and see how it behaves."


def test_cgeventtap_timeout_reenables_tap():
    """Verify macOS kCGEventTapDisabledByTimeout automatically re-enables the tap."""
    app = esc_mb.EscuchaMenuBarApp(start_services=False)
    app.event_tap = MagicMock()
    with patch("escucha.menubar.Quartz.CGEventTapEnable") as mock_enable:
        app.quartz_event_callback(
            None, Quartz.kCGEventTapDisabledByTimeout, MagicMock(), None
        )
        mock_enable.assert_called_once_with(app.event_tap, True)


def test_instant_press_release_race_never_locks_is_recording():
    """Verify pressing and immediately releasing the key in <5ms never leaves is_recording stuck."""
    app = esc_mb.EscuchaMenuBarApp(start_services=False)
    with patch("escucha.session.play_sound"):
        app.handle_key_press()
        app.handle_key_release()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and app.is_recording:
            time.sleep(0.02)
        assert app.is_recording is False
