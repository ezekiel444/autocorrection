# Local Auto-Correction Tool

create your own api keys from here:
 https://aistudio.google.com/api-keys
 https://console.groq.com/keys

A privacy-first, editor-agnostic text correction system that runs entirely on your machine using a local LLM. Select text in any application, hit a hotkey, and get corrections no data ever leaves your computer.

## Features

- **Works with any editor** — Word, OpenOffice, PowerPoint, VS Code, browser, anything with a clipboard
- **System-wide hotkeys** — Ctrl+Shift+C to analyze, Ctrl+Shift+A to auto-apply corrections
- **Local LLM** — Powered by Ollama, all processing stays on your machine
- **Docker Compose** — Single command to deploy the entire stack
- **Multi-language** — Auto-detects English, French, Spanish, German, Portuguese
- **Custom dictionaries** — Add domain-specific terms (medical, legal, technical)
- **Style guide enforcement** — Configurable rules for tone, sentence length, passive voice
- **Confidence scoring** — See how sure the model is about each suggestion
- **REST API** — Integrate with scripts and other tools
- **Plugin system** — Extend with custom correction rules
- **Clipboard monitoring** — Optional auto-analysis on every copy
- **Export reports** — JSON, HTML, PDF formats
- **Correction history** — Track and undo past corrections

## Prerequisites

- **Podman** and **podman-compose** (or `podman compose` via podman 4.7+)
- **Python 3.11+** (for the system tray app)
- **Linux/WSL** with X11 or Wayland display server
- **xclip** or **xsel** (for clipboard access)
- **libnotify** / `notify-send` (for desktop notifications)
- **NVIDIA GPU** (optional, for faster LLM inference)

### Install system dependencies (Ubuntu/Debian)

```bash
sudo apt install xclip libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1 podman podman-compose
```

## Quick Start

### 1. Clone and configure

```bash
cd ~/teamwork_projects/autocorrection-tw
cp .env.example .env
```

Edit `.env` to set your API key and preferences:

```env
API_PORT=8080
API_KEY=your-secret-key
MODEL_NAME=llama3.2:3b
MODEL_CONTEXT_WINDOW=4096
```

### 2. Start the services

```bash
podman-compose up -d
```

This starts three containers:
- **autocorrect-llm** — Ollama LLM service (network-isolated, no internet access)
- **autocorrect-engine** — Correction Engine (text analysis pipeline)
- **autocorrect-api** — API Gateway (REST API on port 8080)

### 3. First start (model auto-downloads)

The first `podman-compose up -d` automatically pulls the configured model (~2GB). This takes a few minutes. Check progress:

```bash
podman logs -f autocorrect-llm
```

You'll see "Model llama3.2:3b pulled successfully." when done. Subsequent starts are instant since the model persists in the volume.

To switch models, change `MODEL_NAME` in `.env` and restart:
- `llama3.2:1b` — Faster, less accurate
- `llama3.1:8b` — More accurate, needs more RAM/VRAM
- `mistral:7b` — Good alternative
- `gemma2:2b` — Lightweight option
- `llama3.1:8b` — More accurate, needs more RAM/VRAM
- `mistral:7b` — Good alternative
- `gemma2:2b` — Lightweight option

Wait for the health check to pass:

```bash
podman-compose ps   # All services should show "healthy"
```

### 4. Install the desktop app

```bash
## linux
python -m venv .venv
source .venv/bin/activate
pip install -e ".[app]"


## for windows
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[app]"
python -m app.main


```

### 5. Run the system tray app

```bash
python -m app.main
```

You'll see a green circle icon in your system tray. The tool is ready.

## Usage

The tool runs as a system tray application on your desktop. It communicates with the containerized correction engine via the REST API. You interact with it through hotkeys, the tray menu, or directly via the API.

### How It Works

1. You select text in any application (Word, browser, terminal, anything)
2. You trigger analysis via hotkey or tray menu
3. The tool copies your selected text from the clipboard
4. It sends the text to the local LLM for analysis (spelling, grammar, punctuation, style, clarity)
5. You get a desktop notification with the results
6. The corrected text is placed on your clipboard — just paste it back

All processing happens locally. No text ever leaves your machine.

### Hotkey Mode (recommended)

| Shortcut | Action |
|----------|--------|
| **Ctrl+Alt+C** | Analyze selected text — shows a notification with correction count. You review before applying. |
| **Ctrl+Alt+A** | Analyze and auto-apply — high-confidence corrections (≥80%) are applied automatically, corrected text goes to clipboard. |

**Workflow:**

1. Select text in any application (highlight it)
2. Press **Ctrl+Alt+C** to analyze
3. A desktop notification appears: "Found 5 correction(s). 3 high-confidence."
4. If you want to auto-apply the confident ones, press **Ctrl+Alt+A** instead
5. Paste (Ctrl+V) the corrected text back into your document

The tool works with any application that supports copy/paste — Word, LibreOffice, Google Docs in a browser, PowerPoint, email clients, code editors, etc.

### Clipboard Monitoring (optional)

Enable in `config/settings.yaml` or via the Settings panel:

```yaml
general:
  clipboard_monitoring: true
```

When enabled, the tool automatically analyzes any text you copy (Ctrl+C) and shows a notification if corrections are found. Text shorter than 10 characters or longer than 5000 characters is ignored. The tool won't re-analyze its own clipboard writes (no feedback loops).

### System Tray Menu

Right-click the tray icon:
- **Run Correction** — Analyze whatever is currently on the clipboard
- **Open History** — View past corrections with undo capability
- **Settings** — Configure language, style rules, hotkeys, dictionaries
- **Quit** — Exit the application

The tray icon color indicates status:
- 🟢 Green — Idle, ready
- 🟡 Amber — Processing text
- 🔴 Red — Error (check logs)

### REST API

For scripting, automation, or integration with other tools:

```bash
# Health check
curl http://localhost:8080/api/v1/health

# Analyze text
curl -X POST http://localhost:8080/api/v1/correct \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"text": "This sentense has a speling eror."}'
```

The response includes each correction with type, confidence score, reason, and suggested fix.

API docs (Swagger UI) available at: http://localhost:8080/api/v1/docs

### Batch Processing

Process entire files without selecting text piece by piece:

```bash
curl -X POST http://localhost:8080/api/v1/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"file_path": "/path/to/document.txt"}'
```

The corrected file is saved alongside the original with a `-corrected` suffix (e.g., `report.txt` → `report-corrected.txt`). The original is never modified.

Supported formats: `.txt`, `.md`, `.rtf` (up to 10MB)

## Configuration

All settings are in `config/settings.yaml`:

```yaml
general:
  default_language: "en"
  auto_apply_high_confidence: false
  clipboard_monitoring: false
  history_retention_days: 30

model:
  name: "llama3.2:3b"
  context_window: 4096
  temperature: 0.3

hotkeys:
  analyze: "ctrl+alt+c"
  analyze_and_apply: "ctrl+alt+a"

style_guide:
  enabled: true
  max_sentence_length: 30
  detect_passive_voice: true
  tone: "neutral"
```

## Custom Dictionaries

Add domain-specific terms so they won't be flagged as errors:

```bash
# Create a dictionary file
echo -e "Kubernetes\nDocker\nFastAPI\nmicroservice" > config/dictionaries/tech-terms.txt
```

Place `.txt` or `.csv` files in the dictionaries volume. They're loaded automatically.

## Plugins

Create custom correction rules in the `plugins/` directory:

```python
# plugins/no-todo/main.py
name = "no-todo"
version = "1.0.0"

def analyze(text, language):
    """Find TODO comments in text."""
    issues = []
    import re
    for match in re.finditer(r'\bTODO\b', text):
        issues.append({
            "message": "TODO found - consider resolving",
            "start_offset": match.start(),
            "end_offset": match.end(),
            "original_text": match.group(),
            "severity": "suggestion",
        })
    return issues

def suggest(text, issue):
    return None  # No auto-fix for TODOs
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Host Machine                                        │
│  ┌──────────────┐                                   │
│  │ System Tray  │──── HTTP ────┐                    │
│  │ App (pystray)│              │                    │
│  └──────────────┘              ▼                    │
│                         ┌─────────────┐             │
│  Docker Compose         │ API Gateway │ :8080       │
│  ┌──────────────────────┤  (FastAPI)  ├──────┐      │
│  │                      └──────┬──────┘      │      │
│  │                             │             │      │
│  │  app_net                    ▼             │      │
│  │                      ┌─────────────┐      │      │
│  │                      │ Correction  │      │      │
│  │                      │   Engine    │ :8081│      │
│  │                      └──────┬──────┘      │      │
│  │                             │             │      │
│  │  internal_net (isolated)    ▼             │      │
│  │                      ┌─────────────┐      │      │
│  │                      │   Ollama    │      │      │
│  │                      │  LLM (no    │      │      │
│  │                      │  internet)  │      │      │
│  │                      └─────────────┘      │      │
│  └───────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────┘
```

**Privacy guarantee**: The LLM container runs on an internal Podman network with `internal: true` — it physically cannot reach the internet.

## Stopping

```bash
# Stop services (data persists in volumes)
podman-compose down

# Stop and remove all data
podman-compose down -v
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=services --cov=app

# Lint
ruff check .
ruff format .
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot connect to API Gateway" | Run `podman-compose ps` — ensure all services are healthy |
| "Clipboard access failed" | Install `xclip`: `sudo apt install xclip` |
| "notify-send not found" | Install: `sudo apt install libnotify-bin` |
| LLM slow / timing out | Use a smaller model: `ollama pull llama3.2:1b` |
| GPU not detected | Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) and configure CDI for Podman |
| Port 8080 in use | Change `API_PORT` in `.env` |
| Hotkeys not working | Ensure X11 display is accessible; try running with `DISPLAY=:0` |
| TLS certificate error during model pull | See "Corporate Proxy / Custom CA" section below |

### Corporate Proxy / Custom CA Certificates

If you're behind a corporate proxy (Cato Networks, Zscaler, Netskope, etc.) that intercepts TLS, you'll see errors like:

```
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

The fix is to copy your system's CA bundle into the project's `certs/` folder:

```bash
cp /etc/ssl/certs/ca-certificates.crt ./certs/ca-certificates.crt
```

This bundle should already include your proxy's certificate if it was installed on the host. The compose file mounts `./certs/ca-certificates.crt` into the LLM container automatically.

If your proxy cert isn't in the system bundle yet, append it first:

```bash
sudo cat /path/to/your-proxy.pem >> /etc/ssl/certs/ca-certificates.crt
sudo update-ca-certificates
cp /etc/ssl/certs/ca-certificates.crt ./certs/ca-certificates.crt
```

Then restart:

```bash
podman-compose down && podman-compose up -d
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8080` | Port for the API Gateway |
| `API_KEY` | `changeme` | API authentication key |
| `MODEL_NAME` | `llama3.2:3b` | Ollama model to use |
| `MODEL_CONTEXT_WINDOW` | `4096` | LLM context window size |
| `HOTKEY_ANALYZE` | `ctrl+alt+c` | Hotkey for text analysis |
| `HOTKEY_APPLY` | `ctrl+alt+a` | Hotkey for auto-apply |
| `CLIPBOARD_MONITORING` | `false` | Enable clipboard auto-monitoring |
| `API_URL` | `http://localhost:8080` | API Gateway URL (for tray app) |
| `CUSTOM_CA_CERT` | `/etc/ssl/certs/ca-certificates.crt` | Host CA bundle path (for corporate proxies) |

## License

Private project.
