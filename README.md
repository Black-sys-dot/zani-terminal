# ⚡ ZANI Terminal  
**Agentic CLI system with intelligent caching, memory compression, and project-aware reasoning**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Model](https://img.shields.io/badge/Gemini-API-purple)
![Interface](https://img.shields.io/badge/Interface-CLI-black)
![Architecture](https://img.shields.io/badge/Architecture-Agentic-orange)
![Status](https://img.shields.io/badge/Version-V1-green)

---

## 🚀 What is ZANI?

ZANI Terminal is a **project-aware AI CLI agent** that understands your entire codebase, remembers conversations, manages context automatically, and executes real file operations safely.

It is designed to behave like a persistent engineering partner inside your terminal.

Core idea:

- Scan project once  
- Cache intelligently  
- Track changes  
- Compress history  
- Execute tools safely  
- Keep token usage efficient  

This is not a chatbot wrapper.  
This is a **stateful agent runtime**.

---

## 🧠 Core Capabilities

### 🔹 Project Awareness
- Scans full workspace
- Builds structured project context
- Tracks file hashes and size changes
- Detects change magnitude

### 🔹 Explicit Cache System
- Creates persistent project cache
- Detects when cache becomes outdated
- Rebuild recommendation based on change %
- TTL based expiration
- User always confirms rebuild

### 🔹 Implicit Cache Optimization
- Stable token ordering
- Predictable context layout
- Designed for maximum cache reuse

### 🔹 Memory System
- Stores full conversation history
- Automatic compression when threshold reached
- Preserves architecture decisions and file updates
- Genesis snapshot of initial codebase

### 🔹 Tool Execution Engine
- Safe tool calling
- User confirmation required
- File writes tracked into memory
- Chat mode blocks tools
- Act mode allows tools

### 🔹 Terminal Visual System
- Rich UI panels
- Token usage receipts
- Context size reporting
- ANSI rendered character art

---

## 🧱 Architecture Overview

```
User Command
    ↓
CLI Parser
    ↓
Workspace Scan
    ↓
Cache Decision Engine
    ↓
Memory Compression (if needed)
    ↓
Session Builder
    ↓
Model Interaction
    ↓
Tool Execution (optional)
    ↓
State Persistence
```

---

## 📦 Project Structure

```
zani-terminal/
│
├── pyproject.toml
├── zani.py
├── .env.example
│
├── core/
│   ├── zani_brain.py
│   ├── cache_manager.py
│   ├── memory.py
│   ├── tools.py
│   ├── project_state.py
│   ├── registry_manager.py
│   ├── rebake_engine.py
│   ├── safety_layers.py
│   └── visuals.py
│
├── config/
│   └── settings.yaml
│
└── .zani/
    ├── history.json
    └── registry.json
```

---

## ⚙️ Requirements

- **Docker** (Engine running, your user allowed to run `docker`)
- Interactive terminal (`-it`; any modern terminal — no Kitty required)
- **OpenRouter** or **Google Gemini** API key
- Internet on first run (image build pulls base layers + Go module)

Everything else (`pylsp`, `mcp-language-server`, Python stack) ships **inside the image**.

---

## 📦 Install

1. Clone or copy this repository (keep the folder — the launcher builds from it).

2. Put the **`zani`** shell launcher on your PATH:

```bash
chmod +x /path/to/zani-terminal/zani
ln -sf /path/to/zani-terminal/zani ~/.local/bin/zani
```

3. From **any project directory**:

```bash
cd /path/to/your/project
zani tui
```

The **first** `zani tui` builds `zani-terminal:latest` automatically (several minutes). Later runs start immediately.

```bash
zani build   # force rebuild after you change Zani
zani help
```

The container mounts your **current directory** as `/workspace` and creates **`.zani.env`** there on first run if needed.

---

## 🔐 API Key Setup (GLOBAL MACHINE ENV)

ZANI reads the API key from your system environment.

### Windows

```
System Properties → Environment Variables → New
Name: GOOGLE_API_KEY
Value: your_key_here
```

Restart terminal after setting.

### Linux / macOS

Add this to your shell configuration (e.g., `~/.bashrc`, `~/.zshrc`, or `~/.profile`):

```bash
export GOOGLE_API_KEY="your_key_here"
```

And reload your shell:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

### `.env` File (Alternative Setup)

Keys are loaded inside the container from:

1. **`<zani-repo>/.env`** — optional machine-wide default (copy from `.env.example` next to the launcher).
2. **`<project>/.zani.env`** — per project (created empty on first `zani tui`; project values override the repo `.env`).

Never commit real `.env` or `.zani.env` files.

Inside `.env`:
```env
GOOGLE_API_KEY="your_key_here"
```

Why global?

- Works from any directory
- No need to reconfigure per project
- Enables universal CLI access

---

## 🧩 How ZANI Is Made Globally Accessible

Symlink the **Docker launcher** `zani` (repo root) into a directory on your `PATH`:

```bash
chmod +x /path/to/zani-terminal/zani
ln -sf /path/to/zani-terminal/zani ~/.local/bin/zani
```

Result:

```bash
zani tui
```

works from any directory on your machine.

This gives full freedom:

- any virtual environment
- any project location
- any install structure

---

## 🚀 First Time Setup

From your project directory, set `GOOGLE_API_KEY` or `OPENROUTER_KEY` (see API Key Setup), then:

```
zani tui
```

Use the full character harness:

```
zani tui --zani
```

---

## 💬 Commands

| Command | Description |
|---------|-------------|
| `zani tui` | Base terminal UI (MCP tools, chat/act modes inside the TUI) |
| `zani tui --zani` | Full Zani visual profile (portrait, backdrop, framed panels) |

---

## 🧠 Runtime Behavior

Inside the TUI, **chat** and **act** modes control tool access (`/mode chat|act` or Ctrl+T). Each prompt includes a runtime block so the model knows whether tools are allowed.

---

## 💾 Cache Lifecycle

1. Project scanned
2. Token size checked
3. If threshold exceeded → recommend explicit cache
4. File changes tracked continuously
5. Change magnitude calculated
6. Cache rebuild suggested when outdated
7. User confirms rebuild

---

## 🧾 Token Accounting

After each run ZANI prints:

- input tokens
- output tokens
- cached tokens
- hit / miss status
- project context size
- conversation history size

Full transparency.

---

## 🧠 Memory Compression Logic

When history exceeds threshold:

- preserve summaries
- preserve file modifications
- summarize older conversation
- keep recent interaction window

This prevents context explosion.

---

## ⚠️ Limitations & Usage Recommendations (v1)

### 📁 Static File Filtering
Zani currently skips machine and system files using **static exclusion rules only**.

This means:

- No intelligent filtering yet  
- No semantic detection of irrelevant files  
- No adaptive context pruning  
- No dynamic project chunking  

Zani simply ignores predefined paths and file patterns (for example `.zani`, virtual environments, etc.).

Future versions may introduce smarter filtering, but for now the system relies on **explicit static exclusions only**.

---

### 💰 Cost Awareness (Important)
Zani builds and processes **full project context** to operate effectively.  
Because of this, token usage depends heavily on project size.

**Strong recommendation:**

1. First test Zani on a **small project**
2. Observe token usage
3. Understand cache behavior
4. Learn how rebakes affect cost
5. Estimate realistic usage before scaling

This helps you avoid unexpected costs and understand how the system behaves.

---

### 🧪 Recommended Usage Scope (v1)
Zani is currently optimized for:

- Small projects  
- Experimental repositories  
- Learning workflows  
- Architecture exploration  
- Controlled environments  

---

### 🚫 Not Recommended Yet
For now, Zani is **not recommended for mid-size or large codebases**.

Reasons:

- Static filtering may include unnecessary files  
- Context size can grow very quickly  
- Cost estimation becomes harder  
- Cache rebuilds can become expensive  
- No advanced project chunking yet  

Large repositories will work technically, but **efficiency and cost control are not fully optimized in this version**.

---

### 👍 Best Practice
Start small → observe behavior → scale gradually.

---

### 🧯 Susy Behavior Recovery
If the system starts behaving inconsistently (cache instability, strange responses, etc.):

Restart the TUI from your project directory if session state looks wrong.

---

## 🎥 Demo Videos

### Polished Demo
Shows agent workflow and capabilities.

```
https://www.linkedin.com/posts/sarvam-tarapure-a34b8a353_buildinpublic-agenticai-python-ugcPost-7431737801387245568-V33T?utm_source=share&utm_medium=member_desktop&rcm=ACoAAFhGBUgBXX12LIUudR9lGheAXqDoZonblCA
```

### Raw Debug Session
Unedited engineering session while building and debugging ZANI.

```
https://drive.google.com/file/d/18o-wj8U9rcwwT60F5jvvScAg1ku9-MDE/view?usp=sharing
```

---

## ⚠️ Sus Behavior Recovery

If the TUI behaves unstable, quit and run `zani tui` again from a clean terminal in your project directory.

---

## 🧪 Development Philosophy

- deterministic context ordering
- token efficiency first
- user control over automation
- persistent agent memory
- explicit safety confirmation
- reproducible execution environment

---

## 🧩 Why This Project Exists

Most AI tools are stateless prompt responders.

ZANI is designed as:

- a persistent engineering entity
- aware of your full codebase
- able to modify files safely
- optimized for long running projects
- built for real development workflows

---

## 📜 License

Personal project.  
Use freely for learning and experimentation.

---

## 👤 Author

Built as an experimental agentic terminal system exploring:

- persistent context design
- explicit caching strategy
- memory compression
- project change detection
- tool mediated execution

---

## ⭐ If You Like This Project

Star the repo or fork it and build your own agent runtime.

```
The future of development is not prompting tools.
It is building systems that remember.
```
