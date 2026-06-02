# Local Auto-Correction Tool

An editor-agnostic text correction system. Select text in any application, press a hotkey, and get corrections on your clipboard ready to paste back.

Supports two backends:
- **Groq** (recommended) — Fast cloud LLM, 3-5 second responses
- **Ollama** (local) — Private, all data stays on your machine, but slow on CPU (~2min)

## Features

- **Works with any editor** — Word, PowerPoint, Notepad, VS Code, browser, anything
- **System-wide hotkeys** — Ctrl+Alt+C to correct, auto-copies your selection
- **Cross-platform** — Windows and Linux
- **Multi-language** — English, French, Spanish, German, Portuguese
- **Fast** — 3-5 seconds with Groq backend
- **REST API** — Integrate with scripts and other tools
- **Custom dictionaries** — Add domain-specific terms
- **Plugin system** — Extend with custom correction rules

## Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Podman** (or Docker) with compose support
- API key from [Groq](https://console.groq.com/keys) (recommended) or [Google AI Studio](https://aistudio.google.com/api-keys)

### 2. Clone and configure

```bash
git clone git@github.com:ezekiel444/autocorrection.git
cd autocorrection
```

Create your `.env` file:

```env
API_PORT=8080
API_KEY=your-internal-api-key
MODEL_NAME=llama3.2:3b
MODEL_CONTEXT_WINDOW=4096

# LLM Backend: "openai" (Groq, fast) or "ollama" (local, private)
LLM_BACKEND=openai
OPENAI_API_KEY=your-groq-api-key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

### 3. Start the services

```bash
podman compose up -d
```

Wait for all services to be healthy:
```bash
podman compose ps
```

### 4. Install the desktop app

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[app]"
```

**Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[app]"
sudo apt install xclip libnotify-bin  # clipboard + notifications
```

### 5. Run

```bash
python -m app.main
```

You'll see a tray icon and a "Ready" notification. The tool is active.

## Usage

### Workflow (one shortcut does everything)

1. **Select text** in any application (Word, Notepad, PowerPoint, browser)
2. Press **Ctrl+Alt+C**
3. Wait 3-5 seconds (you'll see a "Processing..." notification)
4. See "Corrections Applied" notification
5. Press **Ctrl+V** to paste the corrected text back

That's it. The tool auto-copies your selection, sends it for correction, and puts the result on your clipboard.

### Hotkeys

| Shortcut | Action |
|----------|--------|
| **Ctrl+Alt+C** | Auto-correct selected text — result goes to clipboard, just paste back |
| **Ctrl+Alt+V** | Correct with review — shows a popup to accept/reject individual corrections |

### System Tray Menu

Right-click the tray icon:
- **Run Correction** — Correct whatever is on the clipboard
- **Open History** — View past corrections
- **Settings** — Opens settings GUI (backend, API keys, hotkeys)
- **Quit** — Exit the application

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BACKEND` | `openai` | `openai` (Groq/cloud) or `ollama` (local) |
| `OPENAI_API_KEY` | — | Your Groq API key |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | API endpoint |
| `OPENAI_MODEL` | `llama-3.3-70b-versatile` | Model to use |
| `API_PORT` | `8080` | Internal API port |
| `API_KEY` | `changeme` | Internal API authentication |
| `MODEL_NAME` | `llama3.2:3b` | Ollama model (when using local backend) |

### Switching backends

**Fast (cloud, Groq):**
```env
LLM_BACKEND=openai
OPENAI_API_KEY=gsk_your_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

**Private (local, slow without GPU):**
```env
LLM_BACKEND=ollama
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Host Machine                                     │
│                                                   │
│  ┌──────────────┐     ┌─────────────────────┐    │
│  │ System Tray  │────▶│  Groq API (cloud)   │    │
│  │ App (pystray)│     └─────────────────────┘    │
│  └──────┬───────┘                                 │
│         │ (fallback)                              │
│         ▼                                         │
│  ┌─────────────┐    ┌─────────────┐              │
│  │ API Gateway │───▶│ Correction  │              │
│  │  :8080      │    │   Engine    │              │
│  └─────────────┘    └──────┬──────┘              │
│                            │                      │
│                     ┌──────▼──────┐               │
│                     │   Ollama    │               │
│                     │  (local LLM)│               │
│                     └─────────────┘               │
│  ─── Podman Containers ───────────                │
└──────────────────────────────────────────────────┘
```

When `LLM_BACKEND=openai`, the tray app calls Groq directly (bypasses containers for speed). When `LLM_BACKEND=ollama`, it routes through the containerized pipeline.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format .
```

## Building the Desktop App (.exe)

Build a standalone Windows executable — no Python installation needed to run it:

```bash
# Install PyInstaller (one-time)
pip install pyinstaller

# Build the .exe
python build_exe.py
```

The output is `dist/AutoCorrect.exe` (~24 MB). To use it:

1. Copy `dist/AutoCorrect.exe` to any folder (e.g., your Desktop)
2. Copy your `.env` file to the same folder
3. Double-click `AutoCorrect.exe` — it runs silently with a tray icon

No terminal window, no Python needed. Share the `.exe` + `.env` with anyone.

To rebuild after code changes:
```bash
python build_exe.py
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "API request timed out" | Switch to Groq backend (`LLM_BACKEND=openai`) |
| "Failed to analyze text" | Check containers: `podman compose ps` |
| Hotkeys not working | Make sure app is running (`python -m app.main`) |
| No notification on Windows | Install plyer: `pip install plyer` |
| Clipboard error on Linux | Install xclip: `sudo apt install xclip` |
| Garbled output | Already fixed — uses find-and-replace instead of offsets |

## Stopping

```bash
# Stop containers
podman compose down

# Stop tray app
# Right-click tray icon → Quit
```

## Security

- `.env` and `secrets.env` are in `.gitignore` — never committed
- When using Groq, your text is sent to Groq's servers for processing
- When using Ollama, all processing is local — nothing leaves your machine
- The Ollama container has no internet access (isolated network)

## License

Private project.
