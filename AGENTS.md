# AGENTS.md — Mandatory Architecture & Coding Rules for Escucha

All AI agents working in this workspace MUST follow these architectural boundaries and quality standards without exception.

## 1. Strict Two-Folder Root Architecture (`escucha/` vs `whisperflow-base/`)

The root of this repository contains **only two code directories**. Never create extra folders or loose scripts in the repository root:

```text
/
├── escucha/                 # 🎙️ LAYER 2: "Escucha" Dictation Application (Our Product)
│   ├── Escucha.app/         # 🍎 Native macOS Application Bundle
│   ├── escucha/             # 📦 Escucha Python package
│   │   ├── __init__.py      # Product metadata (APP_NAME = "Escucha", BUNDLE_ID = "com.escucha.app")
│   │   ├── config.py        # Hotkey presets, debounce/tail timing, model catalog, hallucination filters
│   │   ├── permissions.py   # macOS Input Monitoring, Accessibility checks & system audio cues
│   │   ├── clipboard.py     # Clipboard preservation & active-window Cmd+V injection
│   │   ├── session.py       # Push-to-Talk capture, live preview & model downloader
│   │   ├── menubar.py       # Native macOS Menu Bar UI (EscuchaMenuBarApp)
│   │   └── cli.py           # Terminal Push-to-Talk client (python -m escucha.cli)
│   ├── tests/               # 🧪 Escucha product unit & QA tests (test_escucha_qa.py)
│   ├── requirements.txt     # Escucha dependencies
│   └── run.sh               # Escucha runner (-start, -test, -cli)
│
└── whisperflow-base/        # 🔒 LAYER 1: Base Engine (Cloned Open-Source Upstream)
    ├── whisperflow/         # Core Whisper model pool, streaming & FastAPI server
    ├── tests/               # Upstream unit & benchmark tests
    ├── docs/                # Upstream documentation
    └── run.sh               # Upstream runner
```

### Mandatory Rules for AI Agents
1. **Never pollute `whisperflow-base/` with product/UI/OS-specific code**:
   - `whisperflow-base/` is the cloned open-source base repository. Do NOT put macOS hotkeys, clipboard pasting, Menu Bar UI, or **Escucha** product logic inside `whisperflow-base/`.
   - Modify `whisperflow-base/` ONLY when fixing or extending the core STT/WebSocket streaming engine itself.
2. **All product features belong inside `escucha/`**:
   - The product is named **Escucha** (`APP_NAME = "Escucha"` in `escucha/escucha/__init__.py`). Never use legacy names like "WhisperFlow Dictate".
   - Place all new product features in their dedicated submodule under `escucha/escucha/`:
     - **Shortcuts / Hotkeys / Timing / Settings**: `escucha/escucha/config.py`
     - **OS Permissions & Audio Cues**: `escucha/escucha/permissions.py`
     - **Text Injection & Clipboard**: `escucha/escucha/clipboard.py`
     - **Audio Recording, VAD, Model Management & PTT Pipeline**: `escucha/escucha/session.py`
     - **macOS Menu Bar UI**: `escucha/escucha/menubar.py`
     - **CLI / Terminal Dictation**: `escucha/escucha/cli.py`
   - Do **NOT** create loose files or extra folders in the repository root.
3. **All Escucha tests belong in `escucha/tests/`**:
   - Every change or new feature in `escucha/` must have corresponding unit/QA tests in `escucha/tests/`.

## 2. Testing & Quality Gates

Before finishing any code change, run `./escucha/run.sh -test`, which enforces:
1. `black` formatting across `escucha/escucha`, `escucha/tests`, `whisperflow-base/whisperflow`, and `whisperflow-base/tests`
2. `pylint --fail-under=9.9` across both layers
3. `pytest` across `escucha/tests` and `whisperflow-base/tests` (with ≥ 95% base engine coverage)
