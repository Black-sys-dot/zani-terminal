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
├── zani.py
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
- Google Gemini API key
- Terminal with ANSI support
- Internet connection

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

Why global?

- Works from any directory
- No need to reconfigure per project
- Enables universal CLI access

---

## 🧩 How ZANI Is Made Globally Accessible

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

Result:

```
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

## 🎥 Demo Videos

### Polished Demo
Shows agent workflow and capabilities.

```
[Add your LinkedIn / X video link here]
```

### Raw Debug Session
Unedited engineering session while building and debugging ZANI.

```
[Add raw debug video link here]
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
