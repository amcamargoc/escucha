# CLAUDE.md — AI Agent Architecture & Engineering Guide

Mandatory architectural and engineering rules for Claude Code and all AI coding assistants working in this repository.
See [README.md](README.md) for end-user usage and [AGENTS.md](AGENTS.md) for the strict layer rules.

---

## 1. Two-Folder Root Architecture

This repository strictly separates the cloned upstream engine (`whisperflow-base/`) from our product (`escucha/`):

- **`escucha/`** — The **Escucha** macOS voice dictation & Push-to-Talk product (`Escucha.app`, `escucha/escucha/` Python package, `escucha/tests/` QA test suite, `escucha/run.sh`).
- **`whisperflow-base/`** — The cloned open-source WhisperFlow base repository (`whisperflow-base/whisperflow/` core STT package, `whisperflow-base/tests/`, `whisperflow-base/docs/`).

**Never place loose scripts or extra folders at the repository root, and never put Escucha UI/hotkey/OS code inside `whisperflow-base/`.**

---

## 2. Commands

| Command | What it does |
|---------|--------------|
| `./escucha/run.sh -start` | Set up `.venv` & `base.en.pt` if missing, then launch **Escucha** (`🎙️`) in the macOS Menu Bar |
| `./escucha/run.sh -test` | Run `black`, `pylint --fail-under=9.9`, and `pytest` across **both** `escucha/` and `whisperflow-base/` |
| `./escucha/run.sh -cli` | Run the terminal Push-to-Talk client against a WhisperFlow WebSocket server |
| `./whisperflow-base/run.sh -run-server` | Start the base WhisperFlow FastAPI server on port 8181 |
| `./whisperflow-base/run.sh -test` | Run only the base engine's format, lint, and unit test suite |

---

## 3. Technical & Thread-Safety Conventions

- **Whisper Model Thread-Safety**: Never call a single Whisper model instance from two threads simultaneously (`kv-cache` hooks corrupt concurrent calls). Always use `ts.get_model()` (`ModelPool`) and `ts.transcribe_pcm_chunks_async()`.
- **macOS AppKit Thread-Safety (`escucha/escucha/menubar.py`)**: Never mutate `rumps.App.title` or `rumps.MenuItem` properties directly from background `asyncio` or `Quartz` threads. Always dispatch UI mutations onto the main Cocoa thread via `self._ui(...)` (`PyObjCTools.AppHelper.callAfter`).
- **Quartz CGEventTap Resilience**: Always handle `kCGEventTapDisabledByTimeout` and `kCGEventTapDisabledByUserInput` by re-enabling `self.event_tap`.
- **Quality Gate**: Always run `./escucha/run.sh -test` and verify it passes before finishing any task.
