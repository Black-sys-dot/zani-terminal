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

- Python 3.10+
- pip (or pipx) to install
- Google Gemini or OpenRouter API key
- Terminal with ANSI support
- Internet connection

Optional system tools (Zani degrades gracefully without them):

- `mcp-language-server` — LSP code intelligence
- `gopls` / `rust-analyzer` / `typescript-language-server` / `clangd` — for non-Python projects
- `mpv` / `ffplay` / `mpg123` — for voice replies

---

## 📦 Install

Recommended: install as a Python package, which puts a `zani` command on your PATH.

```bash
# from the repo root
pip install .

# or for an isolated global install
pipx install .
```

Confirm it works:

```bash
zani --help
```

For development, run it straight from the source tree instead:

```bash
python zani.py tui
```

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

Alternatively, you can create a `.env` file containing the key. ZANI will look for a `.env` file in:
1. The **installation directory** (next to the installed `zani` script) to apply it globally.
2. The **current working directory** (where you run the command) to apply it locally to a single project.

Copy `.env.example` to `.env` in either location and fill in the keys. Never commit a real `.env`.

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

`pip install .` (or `pipx install .`) already makes the `zani` command available
everywhere. The manual launchers below are only needed when running straight
from the source tree instead.

### Windows
We run ZANI through a batch launcher.

Example:

```
@echo off
"E:\agenting_gooner\.venv\Scripts\python.exe" "E:\zani-terminal\zani.py" %*
```

Saved as:

```
C:\ZaniBin\zani.bat
```

Then add that folder to system PATH.

### Linux / macOS
We run ZANI through the shell launcher script `zani` in the root of the repository.

1. Make the scripts executable:
   ```bash
   chmod +x zani zani.py
   ```

2. Symlink the launcher script into a directory in your `PATH` (e.g., `~/.local/bin/` or `/usr/local/bin/`):
   ```bash
   ln -s /path/to/zani-terminal/zani ~/.local/bin/zani
   ```

Result:

```bash
zani chat "hello"
```

works from any directory on your machine.

This gives full freedom:

- any virtual environment
- any project location
- any install structure

---

## 🚀 First Time Setup

Inside your project directory:

```
zani init
```

This will:

- scan workspace
- store genesis snapshot
- estimate project tokens
- optionally create explicit cache

---

## 💬 Commands

### Initialize workspace

```
zani init
```

### Chat with project awareness

```
zani chat "your question"
```

### Execute actions (tool enabled)

```
zani act "your instruction"
```

### Stop active explicit cache

```
zani stop
```

---

## 🧠 Runtime Behavior

Every request includes a runtime instruction block that defines:

- current mode
- tool permissions
- modification policy

This ensures deterministic behavior between chat and act modes.

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

```bash
zani init
```

Reinitializing the workspace usually restores stable operation.

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

If system behaves unstable:

```
zani init
```

Reinitialization rebuilds workspace state and restores stability.

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
