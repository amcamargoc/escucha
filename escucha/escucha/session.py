"""
Push-to-Talk audio capture, live preview, hallucination filtering, and model management
built on top of the base `whisperflow` engine.
"""

import asyncio
import time
from typing import Callable, List, Optional

import pyaudio
import whisper

import whisperflow.streaming as st
import whisperflow.transcriber as ts
from whisperflow import config as wf_config

from escucha import config as esc_config
from escucha.permissions import play_sound


def select_default_model() -> str:
    """Return the best installed Whisper model based on PREFERRED_MODELS order."""
    available = ts.list_models()
    for preferred in esc_config.PREFERRED_MODELS:
        if preferred in available:
            return preferred
    return available[0] if available else "tiny.en.pt"


def download_whisper_model(model_key: str) -> None:
    """Download a Whisper model checkpoint into whisperflow/models/."""
    url = whisper._MODELS[model_key]  # pylint: disable=protected-access
    whisper._download(url, ts.MODELS_DIR, False)  # pylint: disable=protected-access


def open_mic_stream() -> tuple:
    """Open and return a (PyAudio, Stream) pair configured for 16 kHz mono int16 PCM."""
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=wf_config.SAMPLE_RATE,
        input=True,
        frames_per_buffer=wf_config.CHUNK_SIZE,
    )
    return audio, stream


def is_hallucination(text: str, speech_chunk_count: int) -> bool:
    """Filter out known Whisper silence/noise hallucinations on short bursts."""
    normalized = " ".join(text.strip().lower().split())
    if not normalized or speech_chunk_count < esc_config.MIN_SPEECH_CHUNKS:
        return True
    if speech_chunk_count < 12 and normalized in esc_config.HALLUCINATION_PHRASES:
        return True
    return False


async def capture_and_preview(
    stream,
    model_pool,
    release_event: asyncio.Event,
    cancel_event: asyncio.Event,
    on_partial: Optional[Callable[[str], None]] = None,
) -> tuple:
    """Capture mic chunks with tail padding while emitting live preview text."""
    loop = asyncio.get_running_loop()
    chunks: List[bytes] = []
    speech_chunk_count = 0
    capture_done = asyncio.Event()
    started_at = time.monotonic()

    async def _capture_loop():
        nonlocal speech_chunk_count
        try:
            while not cancel_event.is_set():
                if time.monotonic() - started_at > esc_config.MAX_HOLD_SECONDS:
                    release_event.set()
                pcm = await loop.run_in_executor(
                    None,
                    lambda: stream.read(
                        wf_config.CHUNK_SIZE, exception_on_overflow=False
                    ),
                )
                chunks.append(pcm)
                if not st.is_silent(pcm):
                    speech_chunk_count += 1

                if release_event.is_set():
                    tail_count = max(
                        1,
                        int(
                            esc_config.TAIL_PADDING_SECONDS
                            * wf_config.SAMPLE_RATE
                            / wf_config.CHUNK_SIZE
                        ),
                    )
                    for _ in range(tail_count):
                        if cancel_event.is_set():
                            break
                        tail_pcm = await loop.run_in_executor(
                            None,
                            lambda: stream.read(
                                wf_config.CHUNK_SIZE, exception_on_overflow=False
                            ),
                        )
                        chunks.append(tail_pcm)
                        if not st.is_silent(tail_pcm):
                            speech_chunk_count += 1
                    break
                await asyncio.sleep(0.001)
        finally:
            capture_done.set()

    async def _preview_loop():
        last_len = 0
        while (
            not capture_done.is_set()
            and not release_event.is_set()
            and not cancel_event.is_set()
        ):
            await asyncio.sleep(esc_config.PREVIEW_INTERVAL_SECONDS)
            if release_event.is_set() or cancel_event.is_set():
                break
            if (
                speech_chunk_count >= esc_config.MIN_SPEECH_CHUNKS
                and len(chunks) - last_len >= 4
            ):
                snapshot = list(chunks[-400:])
                last_len = len(chunks)
                res = await ts.transcribe_pcm_chunks_async(model_pool, snapshot, "en")
                partial_text = (res or {}).get("text", "").strip()
                if partial_text and on_partial and not release_event.is_set():
                    on_partial(partial_text)

    await asyncio.gather(_capture_loop(), _preview_loop())
    return chunks, speech_chunk_count


async def run_ptt_session(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    model_name: str,
    release_event: asyncio.Event,
    cancel_event: asyncio.Event,
    sound_enabled: bool = True,
    on_listening: Optional[Callable[[], None]] = None,
    on_partial: Optional[Callable[[str], None]] = None,
    on_finalizing: Optional[Callable[[], None]] = None,
) -> str:
    """
    Execute a complete Push-to-Talk session:
    1. Hold debounce (180ms) to ignore accidental modifier taps / Ctrl+C shortcuts.
    2. Live partial preview updates without mid-sentence window resets.
    3. Tail padding (80ms) after release so trailing consonants aren't clipped.
    4. Single whole-utterance final transcription to prevent duplicate words.
    """
    wait_tasks = [
        asyncio.create_task(release_event.wait()),
        asyncio.create_task(cancel_event.wait()),
    ]
    try:
        await asyncio.wait(
            wait_tasks,
            timeout=esc_config.HOLD_DEBOUNCE_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in wait_tasks:
            task.cancel()

    if release_event.is_set() or cancel_event.is_set():
        return ""

    if on_listening:
        on_listening()
    play_sound("Tink", sound_enabled)

    model_pool = ts.get_model(model_name)
    audio, stream = open_mic_stream()

    try:
        chunks, speech_chunk_count = await capture_and_preview(
            stream, model_pool, release_event, cancel_event, on_partial
        )
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    if cancel_event.is_set() or speech_chunk_count < esc_config.MIN_SPEECH_CHUNKS:
        return ""

    if on_finalizing:
        on_finalizing()

    final_res = await ts.transcribe_pcm_chunks_async(model_pool, chunks, "en")
    transcript = (final_res or {}).get("text", "").strip()

    if is_hallucination(transcript, speech_chunk_count):
        return ""
    return transcript
