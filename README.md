# Escucha 🎙️

**Escucha** is a native macOS Push-to-Talk voice dictation application built on top of the open-source [WhisperFlow](whisperflow-base/README.md) real-time speech-to-text engine.

Hold a single key anywhere on macOS (Browser, Terminal, Slack, Notes, IDE) to speak, and release to automatically paste clean, accurate text at your cursor while preserving your clipboard.

---

## Repository Structure

This repository is organized into **two strictly separated top-level directories**:

```text
.
├── escucha/                 # 🎙️ PRODUCT LAYER: Escucha macOS Dictation App
│   ├── Escucha.app/         # 🍎 Double-clickable macOS Application Bundle
│   ├── escucha/             # 📦 Escucha Python package (menubar, session, clipboard, permissions, cli, config)
│   ├── tests/               # 🧪 Escucha QA & unit test suite
│   ├── requirements.txt     # Escucha dependencies
│   └── run.sh               # Escucha launcher & test runner
│
├── whisperflow-base/        # 🔒 BASE ENGINE LAYER: Cloned open-source WhisperFlow engine
│   ├── whisperflow/         # Core STT engine (transcriber, streaming, fast_server, models/)
│   ├── tests/               # Base engine unit & benchmark tests
│   ├── docs/                # Upstream engine documentation & protocol spec
│   └── run.sh               # Upstream engine runner
│
├── AGENTS.md                # 🤖 AI Agent architectural rules & boundaries
├── CLAUDE.md                # 🤖 Claude Code & AI assistant reference
└── README.md                # 📖 Project overview & quick start
```

---

## Quick Start (macOS)

### Option 1: Double-Click `Escucha.app` (Recommended)
1. Open the [`escucha/`](escucha/) folder in Finder.
2. Double-click **`Escucha.app`**.
   - On first launch, if `.venv` or `base.en.pt` isn't installed yet, **Escucha** automatically sets up the environment and downloads the `base.en.pt` model (139 MB).
3. Look for the **`🎙️`** icon in the top-right macOS Menu Bar.

### Option 2: Launch from Terminal
```bash
./escucha/run.sh -start
```

---

## How to Use Escucha

1. **First-Time macOS Permissions**:
   - Allow **Microphone**, **Input Monitoring** (to detect the Push-to-Talk key globally), and **Accessibility** (to paste text automatically into your active window).
   - You can open macOS Privacy Settings anytime directly from the **`🎙️`** Menu Bar dropdown.
2. **Hold `Control (^)`** (by itself) and speak — the Menu Bar icon turns **`🔴`** and previews your words live.
3. **Release `Control (^)`** — **Escucha** finalizes your speech, pastes it into the focused window, and restores your previous clipboard.
4. **Customize from the `🎙️` Menu Bar Icon**:
   - **Push-to-Talk Key**: Switch between `Control (^)`, `Right Option (⌥)`, `Right Shift (⇧)`, `Right Command (⌘)`, `F8`, or `F9`.
   - **Whisper Model**: Switch between `base.en.pt` and `tiny.en.pt`, or download `small.en.pt` (461 MB) with one click.
   - **Sound Effects**: Toggle the start/stop audio cues on or off.

---

## Running Tests & Quality Checks

Run the full formatter (`black`), linter (`pylint >= 9.9`), and test suite (`pytest`) across both **Escucha** and **WhisperFlow Base**:

```bash
./escucha/run.sh -test
```
