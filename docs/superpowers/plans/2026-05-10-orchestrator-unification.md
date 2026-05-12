# Orchestrator Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the base `Orchestrator` class from `~/git/ariel/` into a canonical `lmf` Python package in `~/git/lmf/stack/`, have Ariel import from it, and delete the stale duplicate in `~/git/lmf-ollama-obsidian/`.

**Architecture:** The `lmf` package (at `~/git/lmf/stack/lmf/`) provides the generic HTTP orchestrator, backend abstraction, and prompt compiler. Ariel subclasses `Orchestrator` with its persona, guard, memory, and thinking layers. The two repos connect via `PYTHONPATH=/lmf_stack` set in Docker Compose; a volume mount exposes `~/git/lmf/stack` as `/lmf_stack` inside the Ariel container. Local dev uses `export PYTHONPATH=~/git/lmf/stack:$PYTHONPATH`.

**Tech Stack:** Python 3.11+, pyyaml, requests; existing pytest suite; Docker Compose volumes.

---

## File Map

### Created in `~/git/lmf/`
| File | Responsibility |
|---|---|
| `stack/lmf/__init__.py` | Package root |
| `stack/lmf/backends.py` | Backend abstraction (moved from `ariel/core/`) |
| `stack/lmf/build_prompt.py` | Prompt compiler (moved from `ariel/core/`) |
| `stack/lmf/orchestrator.py` | Base `Orchestrator` + `Handler` + `run_with()` (moved + generalized) |

### Modified in `~/git/ariel/`
| File | Change |
|---|---|
| `core/ariel/persona.py` | Update import: `from lmf.orchestrator import Orchestrator` |
| `core/orchestrator.py` | Gutted to Ariel-specific entry point only (imports from LMF) |
| `requirements.txt` | Note LMF dev dependency |
| `tests/conftest.py` | New: add `/lmf_stack` (or `~/git/lmf/stack`) to `sys.path` |
| `tests/test_vault_tools.py` | Update sys.path insert to use conftest |
| `tests/test_orchestrator_write_gate.py` | Same |

### Deleted in `~/git/lmf-ollama-obsidian/`
| File | Change |
|---|---|
| `core/ariel/` (entire dir) | Deleted — stale duplicate, not used by Docker |

### Modified in `~/git/docker-compose.yml`
| File | Change |
|---|---|
| `docker-compose.yml` | Add `lmf_stack` volume + `PYTHONPATH` env to `ariel` service |

---

## Task 1: Create branches

**Files:** No file changes — git operations only.

- [ ] **Step 1: Create branches in all three repos**

```bash
git -C ~/git/lmf checkout -b feat/canonical-orchestrator
git -C ~/git/ariel checkout -b feat/import-from-lmf
git -C ~/git/lmf-ollama-obsidian checkout -b feat/drop-ariel-duplicate
```

- [ ] **Step 2: Verify branches**

```bash
git -C ~/git/lmf branch --show-current
git -C ~/git/ariel branch --show-current
git -C ~/git/lmf-ollama-obsidian branch --show-current
```

Expected output: `feat/canonical-orchestrator`, `feat/import-from-lmf`, `feat/drop-ariel-duplicate`

---

## Task 2: Establish LMF package skeleton

**Files:**
- Create: `~/git/lmf/stack/lmf/__init__.py`

- [ ] **Step 1: Create the package directory and empty `__init__.py`**

```bash
mkdir -p ~/git/lmf/stack/lmf
touch ~/git/lmf/stack/lmf/__init__.py
```

- [ ] **Step 2: Verify import resolves**

```bash
PYTHONPATH=~/git/lmf/stack python3 -c "import lmf; print('lmf package OK')"
```

Expected: `lmf package OK`

- [ ] **Step 3: Commit to lmf repo**

```bash
git -C ~/git/lmf add stack/lmf/__init__.py
git -C ~/git/lmf commit -m "feat: add lmf package skeleton for canonical orchestrator"
```

---

## Task 3: Move backends.py to LMF

**Files:**
- Create: `~/git/lmf/stack/lmf/backends.py`

The file is moved verbatim — no LMF-specific changes needed.

- [ ] **Step 1: Write the failing import test**

```bash
cat > /tmp/test_backends_import.py << 'EOF'
import sys
sys.path.insert(0, str(__import__('pathlib').Path.home() / 'git/lmf/stack'))
from lmf.backends import build_backend, BackendError, RateLimitError, BackendResult
print("OK")
EOF
python3 /tmp/test_backends_import.py
```

Expected: `ModuleNotFoundError` (file doesn't exist yet)

- [ ] **Step 2: Copy backends.py to LMF**

```bash
cp ~/git/ariel/core/backends.py ~/git/lmf/stack/lmf/backends.py
```

- [ ] **Step 3: Verify the import test passes**

```bash
python3 /tmp/test_backends_import.py
```

Expected: `OK`

- [ ] **Step 4: Commit to lmf repo**

```bash
git -C ~/git/lmf add stack/lmf/backends.py
git -C ~/git/lmf commit -m "feat: add canonical backends abstraction to lmf package"
```

---

## Task 4: Move build_prompt.py to LMF

**Files:**
- Create: `~/git/lmf/stack/lmf/build_prompt.py`

- [ ] **Step 1: Write the failing import test**

```bash
python3 -c "
import sys
sys.path.insert(0, str(__import__('pathlib').Path.home() / 'git/lmf/stack'))
from lmf.build_prompt import build_prompt
print('OK')
"
```

Expected: `ModuleNotFoundError`

- [ ] **Step 2: Copy build_prompt.py to LMF**

```bash
cp ~/git/ariel/core/build_prompt.py ~/git/lmf/stack/lmf/build_prompt.py
```

- [ ] **Step 3: Verify the import test passes**

```bash
python3 -c "
import sys
sys.path.insert(0, str(__import__('pathlib').Path.home() / 'git/lmf/stack'))
from lmf.build_prompt import build_prompt
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git -C ~/git/lmf add stack/lmf/build_prompt.py
git -C ~/git/lmf commit -m "feat: add canonical build_prompt to lmf package"
```

---

## Task 5: Move base Orchestrator to LMF

This is the core of the unification. We extract `Orchestrator`, `Handler`, and supporting functions from `ariel/core/orchestrator.py` into `lmf/stack/lmf/orchestrator.py`, with two changes:

1. **Imports** updated from bare-module style (`from backends import ...`) to package style (`from lmf.backends import ...`).
2. **`run()`** replaced by **`run_with(orchestrator_class, vault_path, *, config_path=None, tools_config_path=None)`** — takes the orchestrator class as a parameter so any LMF instance can supply its own subclass.
3. **`Orchestrator.__init__`** gains `tools_config_path: Path | None = None` parameter; falls back to same-directory `tools.config.yaml` if not supplied.

**Files:**
- Create: `~/git/lmf/stack/lmf/orchestrator.py`

- [ ] **Step 1: Write the failing import test**

```bash
python3 -c "
import sys
sys.path.insert(0, str(__import__('pathlib').Path.home() / 'git/lmf/stack'))
from lmf.orchestrator import Orchestrator, Handler, run_with
print('OK')
"
```

Expected: `ModuleNotFoundError`

- [ ] **Step 2: Create `lmf/orchestrator.py`**

Copy the content below verbatim to `~/git/lmf/stack/lmf/orchestrator.py`.

The key differences from `ariel/core/orchestrator.py`:
- Import lines changed: `from backends import ...` → `from lmf.backends import ...`; same for `build_prompt`
- `Orchestrator.__init__` signature: add `tools_config_path: Path | None = None`
- In `__init__`, replace `tools_config = Path(__file__).parent / "tools.config.yaml"` with `tools_config = tools_config_path or Path(__file__).parent / "tools.config.yaml"`
- `run()` is deleted; `run_with()` is added in its place

```python
"""
orchestrator.py — LMF base orchestrator.

HTTP server that sits between the user and Ollama.
Each turn: parses skill triggers, assembles context, calls the backend, returns response.

This is the canonical LMF implementation — instance-agnostic.
Subclass `Orchestrator` and pass your subclass to `run_with()` to create an instance.

Usage:
  from lmf.orchestrator import Orchestrator, run_with
"""

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
import yaml

from lmf.build_prompt import build_prompt
from lmf.backends import build_backend, BackendError, RateLimitError, BackendResult

_WRITE_TOOLS = {"append_to_file", "replace_lines", "create_file", "insert_after_heading"}
_CONFIRMATION_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "go ahead", "confirm", "do it"}

INIT_STATE_PATH = "operator/.init_state.json"
DEPLOY_CONFIG_PATH = "operator/deploy.yaml"


def is_confirmation(message: str) -> bool:
    return message.strip().lower().rstrip(".,!?") in _CONFIRMATION_YES


def load_deploy_config(vault: Path) -> dict:
    default = {"instance_name": "LMF", "trust_profile": "personal", "onboarding_mode": "guided"}
    path = vault / DEPLOY_CONFIG_PATH
    if path.exists():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {**default, **cfg}
    return default


def _resolve_env(value):
    if isinstance(value, str):
        def _replace(m):
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                print(f"[orchestrator] WARNING: env var ${var} not set — keeping literal '{m.group(0)}'", file=sys.stderr)
                return m.group(0)
            return val
        return re.sub(r'\$\{(\w+)\}', _replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(config_path: Path | None = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "operator" / "config.yaml"
    if not config_path.exists():
        sys.exit("[orchestrator] No operator config found — run python3 init.py to set up.")
    return _resolve_env(yaml.safe_load(config_path.read_text(encoding="utf-8")))


OLLAMA_URL        = ""
OLLAMA_PS_URL     = ""
OLLAMA_MODEL      = ""
OLLAMA_TIMEOUT    = 300
OLLAMA_NUM_CTX    = 8192
MAX_HISTORY_TURNS = 10
MAX_TOOL_LOOPS    = 5
HOST              = "0.0.0.0"
PORT              = 8742
SKILLS_DIR        = "System/Skills"
UI_FILE           = Path(__file__).parent.parent / "features" / "ui" / "ariel.html"

BACKENDS          : list[tuple[int, object]] = []
ACTIVE_BACKEND    : str | None = None
TURBO_MODE        = False
PACING_INTERVAL   = 8
LAST_REQUEST_TIME = 0.0


def _init_config(config_path: Path | None = None) -> None:
    global OLLAMA_URL, OLLAMA_PS_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_NUM_CTX, PORT
    global BACKENDS, ACTIVE_BACKEND, TURBO_MODE, PACING_INTERVAL, LAST_REQUEST_TIME
    cfg = load_config(config_path)

    OLLAMA_URL     = cfg.get("ollama_url", "http://localhost:11434/api/chat")
    OLLAMA_PS_URL  = OLLAMA_URL.replace("/api/chat", "/api/ps")
    OLLAMA_MODEL   = cfg.get("model", "qwen2.5:3b")
    OLLAMA_TIMEOUT = int(cfg.get("timeout_s", 300))
    OLLAMA_NUM_CTX = int(cfg.get("num_ctx", 8192))
    PORT           = int(cfg.get("port", 8742))

    pacing = cfg.get("pacing", {})
    TURBO_MODE      = pacing.get("mode", "slow") == "turbo"
    PACING_INTERVAL = int(pacing.get("interval_s", 8))
    LAST_REQUEST_TIME = 0.0

    BACKENDS = []
    for entry in cfg.get("backends", []):
        name = entry["name"]
        if entry.get("type") == "openai":
            key = entry.get("api_key", "")
            if not key or key.startswith("${"):
                print(f"[orchestrator] WARNING: backend '{name}' has no API key — skipping", file=sys.stderr)
                continue
        backend = build_backend(name, entry)
        priority = int(entry.get("priority", 99))
        BACKENDS.append((priority, backend))
    BACKENDS.sort(key=lambda x: x[0])

    if not BACKENDS:
        fallback_cfg = {
            "type": "ollama",
            "base_url": OLLAMA_URL.rstrip("/api/chat"),
            "model": OLLAMA_MODEL,
            "num_ctx": OLLAMA_NUM_CTX,
        }
        BACKENDS.append((0, build_backend("legacy-ollama", fallback_cfg)))

    ACTIVE_BACKEND = None


def load_skill(vault: Path, name: str) -> str | None:
    candidates = [
        vault / SKILLS_DIR / f"{name}.md",
        vault / SKILLS_DIR / name / f"{name}.md",
        vault / SKILLS_DIR / name / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None


def parse_skill_trigger(message: str) -> str | None:
    match = re.match(r"^/([a-z0-9_-]+)", message.strip())
    return match.group(1) if match else None


class Orchestrator:
    def __init__(self, vault_path: str, test_mode: bool = False, tools_config_path: Path | None = None):
        self.vault = Path(vault_path)
        self.is_init_mode = self._is_first_run()
        self.history: list[dict] = []
        self.inference_in_progress: bool = False
        self.last_response_ms: int | None = None
        self.last_tool_calls: list[str] = []
        self.init_handoff = None
        self.test_mode = test_mode

        self.loom_url = os.environ.get("LOOM_URL", "http://knowledge-loom:8888")

        if self.is_init_mode:
            self._enter_init_mode()
        else:
            self.system_prompt, self.prompt_stats = build_prompt(vault_path)
            tools_config = tools_config_path or Path(__file__).parent / "tools.config.yaml"
            self.tools = self._build_tools(tools_config)

        print(f"[orchestrator] Vault: {self.vault}")
        print(f"[orchestrator] System prompt: {len(self.system_prompt)} chars")
        if self.is_init_mode:
            print(f"[orchestrator] Mode: init (first run)")
        elif self.tools:
            print(f"[orchestrator] Tools: {[t['function']['name'] for t in self.tools]}")
        else:
            print("[orchestrator] Tools: none (Phase 1 mode)")
        print(f"[orchestrator] Listening on {HOST}:{PORT}")

    def _is_first_run(self) -> bool:
        return not (self.vault / "LOCAL_MIND_FOUNDATION.md").exists()

    def _enter_init_mode(self):
        deploy_cfg = load_deploy_config(self.vault)
        init_prompt_path = Path(__file__).parent.parent / "prompts" / "init.md"
        template = init_prompt_path.read_text(encoding="utf-8")

        init_state = self._load_init_state()
        if init_state.get("phase") != "interview":
            resume_context = (
                "The operator partially completed setup. "
                "Do not repeat questions already answered. "
                "Resume from where they left off."
            )
        else:
            resume_context = ""

        self.system_prompt = template.format(
            instance_name=deploy_cfg["instance_name"],
            trust_profile=deploy_cfg["trust_profile"],
            onboarding_mode=deploy_cfg["onboarding_mode"],
            resume_context=resume_context,
        )
        self.prompt_stats = {"memory_files_loaded": 0, "skills_in_index": 0}
        self.tools = []
        self.init_state = init_state
        self.init_handoff = None

    def reset(self):
        self.history = []
        if self.is_init_mode:
            self._clear_init_state()

    def _load_init_state(self) -> dict:
        path = self.vault / INIT_STATE_PATH
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"phase": "interview", "answered_questions": [], "profile_draft": {}}

    def _save_init_state(self):
        path = self.vault / INIT_STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        def _convert(o):
            if hasattr(o, "isoformat"):
                return o.isoformat()
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
        path.write_text(json.dumps(self.init_state, indent=2, default=_convert), encoding="utf-8")

    def _clear_init_state(self):
        path = self.vault / INIT_STATE_PATH
        if path.exists():
            path.unlink()

    def _extract_profile(self, reply: str) -> dict:
        after_signal = reply.split("[INIT_COMPLETE]", 1)[-1]
        match = re.search(r'^---\s*\n(.*?)\n---', after_signal, re.DOTALL | re.MULTILINE)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _build_foundation_md(self, profile: dict) -> str:
        fields = {
            "title": "LOCAL_MIND_FOUNDATION",
            "type": "profile",
            "instance_name": profile.get("instance_name", "LMF"),
            "trust_profile": profile.get("trust_profile", "personal"),
            "init_date": datetime.now().strftime("%Y-%m-%d"),
        }
        for key in ("operator_name", "primary_need", "attention_profile", "work_separate", "household_size"):
            if key in profile and profile[key]:
                fields[key] = profile[key]
        lines = ["---"]
        for k, v in fields.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _seed_vault_directories(self):
        for d in ["Tasks", "Projects", "Daily"]:
            (self.vault / d).mkdir(parents=True, exist_ok=True)
        inbox = self.vault / "Inbox.md"
        if not inbox.exists():
            inbox.write_text("", encoding="utf-8")

    def _complete_initiation(self) -> str:
        proposed_path = self.vault / ".proposed" / "LOCAL_MIND_FOUNDATION.md"
        if proposed_path.exists():
            foundation = proposed_path.read_text(encoding="utf-8")
        else:
            foundation = self._build_foundation_md(self.init_handoff["profile_draft"])

        (self.vault / "LOCAL_MIND_FOUNDATION.md").write_text(foundation, encoding="utf-8")
        shutil.rmtree(self.vault / ".proposed", ignore_errors=True)

        self._seed_vault_directories()

        self.system_prompt, self.prompt_stats = build_prompt(str(self.vault))
        self.is_init_mode = False
        self.init_handoff = None
        tools_config = Path(__file__).parent / "tools.config.yaml"
        self.tools = self._build_tools(tools_config)
        self._clear_init_state()

        cfg = load_config()
        ai_name = cfg.get("ai_name", "your assistant")
        print(f"[orchestrator] Initiation complete — handed off to {ai_name}")
        return f"Setup complete. Let me introduce you to {ai_name}."

    _TOOL_PARAM_SCHEMAS: dict = {
        "search_vault": {
            "type": "object",
            "properties": {
                "query":  {"type": "string",  "description": "Search query"},
                "top_k":  {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
        "read_section": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Vault-relative path"},
                "heading":   {"type": "string", "description": "Section heading — substring match OK"},
            },
            "required": ["file_path", "heading"],
        },
        "read_lines": {
            "type": "object",
            "properties": {
                "file_path":  {"type": "string",  "description": "Vault-relative path"},
                "start_line": {"type": "integer", "description": "Start line (1-indexed)"},
                "end_line":   {"type": "integer", "description": "End line (inclusive)"},
            },
            "required": ["file_path", "start_line", "end_line"],
        },
        "outline": {
            "type": "object",
            "properties": {"file_path": {"type": "string", "description": "Vault-relative path"}},
            "required": ["file_path"],
        },
        "grep_vault": {
            "type": "object",
            "properties": {
                "pattern":     {"type": "string", "description": "Regex pattern"},
                "file_filter": {"type": "string", "description": "Optional path substring"},
            },
            "required": ["pattern"],
        },
        "append_to_file": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Vault-relative path"},
                "content":   {"type": "string", "description": "Content to append"},
            },
            "required": ["file_path", "content"],
        },
        "replace_lines": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string",  "description": "Vault-relative path"},
                "start_line":  {"type": "integer", "description": "Start line (1-indexed)"},
                "end_line":    {"type": "integer", "description": "End line (inclusive)"},
                "new_content": {"type": "string",  "description": "Replacement content"},
            },
            "required": ["file_path", "start_line", "end_line", "new_content"],
        },
        "list_files": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }

    def _build_tools(self, config_path: Path) -> list[dict]:
        if not config_path.exists():
            return []
        conf = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        result = []
        for name, tool_conf in conf.get("tools", {}).items():
            if not tool_conf.get("enabled", False):
                continue
            schema = self._TOOL_PARAM_SCHEMAS.get(name)
            if schema is None:
                continue
            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_conf.get("description", ""),
                    "parameters": schema,
                },
            })
        return result

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r'\b[a-z0-9]+\b', text.lower())

    def _tool_search(self, query: str, top_k: int = 5) -> list[dict]:
        try:
            resp = requests.post(
                f"{self.loom_url}/api/search",
                json={"query": query, "limit": top_k},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Vault search unavailable — is knowledge-loom running?")

    def _tool_outline(self, file_path: str) -> list[dict] | dict:
        target = self.vault / file_path
        if not target.exists():
            return {"error": f"File not found: {file_path}"}
        result = []
        for i, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                result.append({"level": len(m.group(1)), "heading": m.group(2).strip(), "line_number": i})
        return result

    def _tool_read_section(self, file_path: str, heading: str) -> dict | None:
        target = self.vault / file_path
        if not target.exists():
            return {"error": f"File not found: {file_path}"}
        lines = target.read_text(encoding="utf-8").splitlines()
        heading_lower = heading.lower()
        heading_stack = []
        for i, line in enumerate(lines, 1):
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                level = len(m.group(1))
                heading_text = m.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text, i))
                breadcrumb = " > ".join(h[1] for h in heading_stack)
                if heading_lower in breadcrumb.lower():
                    content_start = i + 1
                    j = content_start - 1
                    while j < len(lines) and not re.match(r'^#{1,6}\s+', lines[j]):
                        j += 1
                    content = "\n".join(lines[content_start - 1:j]).strip()
                    return {
                        "file": file_path,
                        "heading": breadcrumb,
                        "heading_line": i,
                        "content_start": content_start,
                        "content_end": j,
                        "content": content,
                    }
        return None

    def _tool_read_lines(self, file_path: str, start_line: int, end_line: int) -> dict | None:
        target = self.vault / file_path
        if not target.exists():
            return None
        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(1, start_line)
        end = min(len(lines), end_line)
        return {
            "file": file_path,
            "start_line": start,
            "end_line": end,
            "content": "\n".join(lines[start - 1:end]),
        }

    def _tool_grep(self, pattern: str, file_filter: str | None = None, limit: int = 50) -> list[dict]:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return [{"error": f"Invalid regex: {e}"}]
        results = []
        for fp in sorted(self.vault.rglob("*.md")):
            rel = fp.relative_to(self.vault).as_posix()
            if file_filter and file_filter not in rel:
                continue
            for i, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
                if regex.search(line):
                    results.append({"file": rel, "line_number": i, "line_text": line[:500]})
                    if len(results) >= limit:
                        return results
        return results

    def _tool_append_to_file(self, file_path: str, content: str) -> dict:
        target = self.vault / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        current = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        new_lines = current + ["", content]
        target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return {"file": file_path, "appended_at_line": len(new_lines)}

    def _tool_replace_lines(self, file_path: str, start_line: int, end_line: int, new_content: str) -> dict:
        target = self.vault / file_path
        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(1, start_line)
        end = min(len(lines), end_line)
        new_lines = lines[:start - 1] + new_content.splitlines() + lines[end:]
        target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return {"file": file_path, "replaced_lines": end - start + 1, "new_line_count": len(new_lines)}

    def _tool_list_files(self) -> list[dict]:
        files = []
        for fp in sorted(self.vault.rglob("*.md")):
            rel = fp.relative_to(self.vault).as_posix()
            lines = fp.read_text(encoding="utf-8").splitlines()
            size_kb = round(fp.stat().st_size / 1024, 1)
            files.append({"file": rel, "line_count": len(lines), "size_kb": size_kb})
        return files

    def _dispatch_tool(self, name: str, args: dict) -> str:
        try:
            if self.is_init_mode:
                if name == "append_to_file" and args.get("file_path") == "Inbox.md":
                    inbox = self.vault / "Inbox.md"
                    inbox.parent.mkdir(parents=True, exist_ok=True)
                    with open(inbox, "a", encoding="utf-8") as f:
                        f.write(args["content"].strip() + "\n")
                    return json.dumps({"status": "appended to Inbox.md"})
                if name in _WRITE_TOOLS:
                    return json.dumps({"error": "In init mode, write tools are limited to Inbox.md"})
                return json.dumps({"error": "Vault tools are unavailable during init mode"})

            self.last_tool_calls.append(name)

            if name == "search_vault":
                return json.dumps(self._tool_search(args["query"], top_k=args.get("top_k", 5)))
            if name == "read_section":
                r = self._tool_read_section(args["file_path"], args["heading"])
                return json.dumps(r if r else {"error": "Section not found"})
            if name == "read_lines":
                r = self._tool_read_lines(args["file_path"], args["start_line"], args["end_line"])
                return json.dumps(r if r else {"error": "File not found"})
            if name == "outline":
                return json.dumps(self._tool_outline(args["file_path"]))
            if name == "grep_vault":
                return json.dumps(self._tool_grep(args["pattern"], file_filter=args.get("file_filter")))
            if name == "append_to_file":
                return json.dumps(self._tool_append_to_file(args["file_path"], args["content"]))
            if name == "replace_lines":
                return json.dumps(self._tool_replace_lines(
                    args["file_path"], args["start_line"], args["end_line"], args["new_content"]
                ))
            if name == "list_files":
                return json.dumps(self._tool_list_files())
            return json.dumps({"error": f"Unknown tool: {name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def chat(self, user_message: str, timeout: int = OLLAMA_TIMEOUT) -> str:
        global TURBO_MODE, PACING_INTERVAL, LAST_REQUEST_TIME
        self.last_tool_calls = []
        if self.is_init_mode and self.init_handoff:
            if is_confirmation(user_message):
                return self._complete_initiation()
            else:
                shutil.rmtree(self.vault / ".proposed", ignore_errors=True)
                self.init_handoff = None

        if user_message.strip().lower() in ("/marlin-turbo", "/turbo"):
            TURBO_MODE = not TURBO_MODE
            state = "Turbo ON — pacing disabled" if TURBO_MODE else "Slow mode ON — pacing active"
            return state

        messages = [{"role": "system", "content": self.system_prompt}]

        skill_name = parse_skill_trigger(user_message)
        if skill_name:
            skill_content = load_skill(self.vault, skill_name)
            if skill_content:
                messages.append({
                    "role": "user",
                    "content": f"[Skill loaded: /{skill_name}]\n\n{skill_content}"
                })
                messages.append({
                    "role": "assistant",
                    "content": f"Skill /{skill_name} loaded. Following its instructions now."
                })

        messages += self.history
        messages.append({"role": "user", "content": user_message})

        self.inference_in_progress = True
        t0 = time.monotonic()
        reply = ""
        try:
            if not TURBO_MODE and LAST_REQUEST_TIME > 0:
                elapsed = time.monotonic() - LAST_REQUEST_TIME
                if elapsed < PACING_INTERVAL:
                    time.sleep(PACING_INTERVAL - elapsed)
            LAST_REQUEST_TIME = time.monotonic()

            for _ in range(MAX_TOOL_LOOPS):
                result = None
                last_error = None
                for priority, backend in BACKENDS:
                    if not backend.is_available:
                        continue
                    try:
                        result = backend.chat(messages, tools=self.tools, timeout=timeout)
                        global ACTIVE_BACKEND
                        ACTIVE_BACKEND = backend.name
                        last_error = None
                        break
                    except RateLimitError:
                        last_error = f"{backend.name} rate limited"
                        continue
                    except BackendError as e:
                        last_error = str(e)
                        continue

                if result is None:
                    reply = f"[All backends exhausted: {last_error}]"
                    break

                tool_calls = result.tool_calls
                if not tool_calls:
                    reply = result.content
                    if reply and re.match(r'^\s*\{\s*"name"\s*:\s*"', reply.strip()):
                        messages.append({"role": "assistant", "content": reply})
                        messages.append({
                            "role": "user",
                            "content": "The tool call above has been handled. Now summarize what you found in natural language.",
                        })
                        continue
                    break

                messages.append({
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    if isinstance(fn_args, str):
                        fn_args = json.loads(fn_args)
                    messages.append({"role": "tool", "content": self._dispatch_tool(fn_name, fn_args)})
            else:
                reply = "[Tool loop limit reached — please rephrase your request.]"
        finally:
            self.inference_in_progress = False
            self.last_response_ms = int((time.monotonic() - t0) * 1000)

        if self.is_init_mode and "[INIT_COMPLETE]" in reply:
            profile = self._extract_profile(reply)
            proposed_dir = self.vault / ".proposed"
            proposed_dir.mkdir(parents=True, exist_ok=True)
            proposed_path = proposed_dir / "LOCAL_MIND_FOUNDATION.md"
            proposed_path.write_text(self._build_foundation_md(profile), encoding="utf-8")
            self.init_handoff = {
                "reply": reply,
                "profile_draft": profile,
                "proposal_file": ".proposed/LOCAL_MIND_FOUNDATION.md",
            }
            self.init_state["phase"] = "handoff"
            self.init_state["profile_draft"] = profile
            self._save_init_state()

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})

        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

        return reply


class Handler(BaseHTTPRequestHandler):
    orchestrator: Orchestrator = None

    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def _serve_ui(self):
        if not UI_FILE.exists():
            self._respond(404, {"error": "ui/ariel.html not found"})
            return
        content = UI_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/ui"):
            self._serve_ui()
        elif self.path == "/health":
            self._respond(200, {"status": "ok"})
        elif self.path == "/status":
            self._handle_status()
        else:
            self._respond(404, {"error": "not found"})

    def _handle_status(self):
        orch = self.orchestrator
        ollama_ok = False
        model_loaded = False
        model_name = OLLAMA_MODEL
        try:
            ps = requests.get(OLLAMA_PS_URL, timeout=3)
            ps.raise_for_status()
            ollama_ok = True
            models = ps.json().get("models", [])
            for m in models:
                if m.get("name", "").startswith(OLLAMA_MODEL.split(":")[0]):
                    model_loaded = True
                    model_name = m.get("name", OLLAMA_MODEL)
                    break
        except Exception:
            pass

        prompt_chars = len(orch.system_prompt)
        history_turns = len(orch.history) // 2
        self._respond(200, {
            "orchestrator": "ok",
            "ollama": "ok" if ollama_ok else "unreachable",
            "model": model_name,
            "model_loaded": model_loaded,
            "num_ctx": OLLAMA_NUM_CTX,
            "system_prompt_chars": prompt_chars,
            "system_prompt_tokens_est": prompt_chars // 4,
            "init_mode": orch.is_init_mode,
            "memory_files_loaded": orch.prompt_stats["memory_files_loaded"],
            "skills_in_index": orch.prompt_stats["skills_in_index"],
            "history_turns": history_turns,
            "inference_in_progress": orch.inference_in_progress,
            "last_response_ms": orch.last_response_ms,
            "turbo_mode": TURBO_MODE,
            "pacing_interval_s": PACING_INTERVAL,
            "active_backend": ACTIVE_BACKEND,
            "backends": [{"name": b.name, "available": b.is_available, "last_error": b.last_error}
                         for _, b in BACKENDS],
        })

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/chat":
            message = body.get("message", "").strip()
            if not message:
                self._respond(400, {"error": "message required"})
                return
            timeout = int(body.get("timeout_s", OLLAMA_TIMEOUT))
            try:
                reply = self.orchestrator.chat(message, timeout=timeout)
                resp = {"response": reply}
                if self.orchestrator.init_handoff:
                    pf = self.orchestrator.init_handoff.get("proposal_file")
                    if pf:
                        proposed_path = self.orchestrator.vault / pf
                        if proposed_path.exists():
                            resp["proposal"] = {
                                "path": pf,
                                "content": proposed_path.read_text(encoding="utf-8"),
                            }
                self._respond(200, resp)
            except requests.exceptions.Timeout:
                self._respond(504, {"error": f"model did not respond within {timeout}s"})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == "/turbo":
            global TURBO_MODE
            TURBO_MODE = not TURBO_MODE
            self._respond(200, {"turbo": TURBO_MODE, "pacing": "disabled" if TURBO_MODE else f"every {PACING_INTERVAL}s"})

        elif self.path == "/reset":
            self.orchestrator.reset()
            resp_body = {"status": "conversation reset"}
            if self.orchestrator.is_init_mode:
                resp_body["init_mode"] = True
                resp_body["message"] = "Init state cleared. You can start over."
            self._respond(200, resp_body)

        else:
            self._respond(404, {"error": "not found"})


def run_with(orchestrator_class, vault_path: str, *, config_path: Path | None = None, tools_config_path: Path | None = None):
    """Start the HTTP server using the given orchestrator subclass.

    Args:
        orchestrator_class: A subclass of Orchestrator to instantiate.
        vault_path: Absolute path to the LMF vault.
        config_path: Path to operator/config.yaml (defaults to vault/../operator/config.yaml).
        tools_config_path: Path to tools.config.yaml (defaults to lmf package dir).
    """
    _init_config(config_path)
    orch = orchestrator_class(vault_path, tools_config_path=tools_config_path)
    Handler.orchestrator = orch
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[orchestrator] Stopped.")
```

- [ ] **Step 3: Verify the import test passes**

```bash
python3 -c "
import sys
sys.path.insert(0, str(__import__('pathlib').Path.home() / 'git/lmf/stack'))
from lmf.orchestrator import Orchestrator, Handler, run_with
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git -C ~/git/lmf add stack/lmf/orchestrator.py
git -C ~/git/lmf commit -m "feat: add canonical base Orchestrator + run_with() to lmf package"
```

---

## Task 6: Add conftest.py to Ariel tests

All Ariel tests need `~/git/lmf/stack` on `sys.path`. A `conftest.py` sets this once rather than repeating in each test file.

**Files:**
- Create: `~/git/ariel/tests/conftest.py`

- [ ] **Step 1: Create conftest.py**

```python
# tests/conftest.py
import os
import sys
from pathlib import Path

# Resolve LMF stack from env or assume sibling directory layout
lmf_stack = os.environ.get("LMF_STACK_PATH", str(Path(__file__).parent.parent.parent / "lmf" / "stack"))
sys.path.insert(0, lmf_stack)
```

- [ ] **Step 2: Verify pytest picks it up**

```bash
cd ~/git/ariel && python3 -c "
import sys
sys.path.insert(0, 'tests')
import conftest
from lmf.orchestrator import Orchestrator
print('conftest path wiring OK')
"
```

Expected: `conftest path wiring OK`

- [ ] **Step 3: Commit**

```bash
git -C ~/git/ariel add tests/conftest.py
git -C ~/git/ariel commit -m "test: add conftest.py to wire LMF stack onto sys.path"
```

---

## Task 7: Rewrite ariel/core/orchestrator.py as thin entry point

After the base `Orchestrator` is in LMF, `ariel/core/orchestrator.py` becomes a thin shim: it imports from `lmf` and provides the Ariel-specific `run()` entry point.

**Files:**
- Modify: `~/git/ariel/core/orchestrator.py`

- [ ] **Step 1: Run the existing test baseline first**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -m pytest tests/test_vault_tools.py tests/test_init_mode.py -v 2>&1 | tail -20
```

Record which tests pass. This is the baseline to protect.

- [ ] **Step 2: Replace `ariel/core/orchestrator.py`**

```python
"""
orchestrator.py — Ariel entry point.

Imports the canonical base from the lmf package and wires ArielOrchestrator
as the concrete implementation.

Start the server:
  python3 core/orchestrator.py [vault_path]
"""
import sys
from pathlib import Path

from lmf.orchestrator import (  # noqa: F401  (re-exported for test compat)
    Orchestrator,
    Handler,
    run_with,
    is_confirmation,
    _WRITE_TOOLS,
    load_config,
    _init_config,
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    OLLAMA_NUM_CTX,
)

_ARIEL_TOOLS_CONFIG = Path(__file__).parent / "tools.config.yaml"


def run(vault_path: str):
    from ariel.persona import ArielOrchestrator
    run_with(ArielOrchestrator, vault_path, tools_config_path=_ARIEL_TOOLS_CONFIG)


if __name__ == "__main__":
    cfg = load_config()
    vault = sys.argv[1] if len(sys.argv) > 1 else cfg.get("vault_path", str(Path.home() / "Documents" / "vault"))
    run(vault)
```

- [ ] **Step 3: Re-run baseline tests — they must all still pass**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -m pytest tests/test_vault_tools.py tests/test_init_mode.py -v 2>&1 | tail -20
```

Expected: same results as Step 1 (no regressions).

- [ ] **Step 4: Commit**

```bash
git -C ~/git/ariel add core/orchestrator.py
git -C ~/git/ariel commit -m "refactor: gut orchestrator.py to Ariel entry point — base now lives in lmf"
```

---

## Task 8: Update persona.py import in Ariel

**Files:**
- Modify: `~/git/ariel/core/ariel/persona.py` line 8

- [ ] **Step 1: Write failing import test**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -c "
import sys, os
sys.path.insert(0, os.environ['LMF_STACK_PATH'])
sys.path.insert(0, 'core')
from ariel.persona import ArielOrchestrator
print('ArielOrchestrator import OK')
" 2>&1
```

This should currently work (imports from local `orchestrator.py`). We're about to change the import source to `lmf`.

- [ ] **Step 2: Update the import in persona.py**

Change line 8 of `~/git/ariel/core/ariel/persona.py` from:
```python
from ..orchestrator import Orchestrator
```
to:
```python
from lmf.orchestrator import Orchestrator
```

- [ ] **Step 3: Verify import still works**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -c "
import sys, os
sys.path.insert(0, os.environ['LMF_STACK_PATH'])
sys.path.insert(0, 'core')
from ariel.persona import ArielOrchestrator
print('ArielOrchestrator import OK')
"
```

Expected: `ArielOrchestrator import OK`

- [ ] **Step 4: Run full test suite**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -m pytest tests/ -v 2>&1 | tail -30
```

Compare pass/fail counts with the Task 7 Step 1 baseline. No new failures allowed.

- [ ] **Step 5: Commit**

```bash
git -C ~/git/ariel add core/ariel/persona.py
git -C ~/git/ariel commit -m "refactor: import Orchestrator from lmf package instead of local copy"
```

---

## Task 9: Update Docker Compose

Wire in the LMF stack volume so the Ariel container can import from it.

**Files:**
- Modify: `~/git/docker-compose.yml` — `ariel` service section

- [ ] **Step 1: Add LMF volume and PYTHONPATH to the ariel service**

In the `ariel` service block, add to `volumes`:
```yaml
      - /home/jared/git/lmf/stack:/lmf_stack:ro
```

And add to `environment`:
```yaml
      - PYTHONPATH=/lmf_stack
```

The resulting `ariel` service diff looks like:
```yaml
    environment:
      - OLLAMA_API_URL=http://ollama:11434
      - PYTHONUNBUFFERED=1
      - GROQ_API_KEY=${GROQ_API_KEY}
      - OPENROUTER_KEY=${OPENROUTER_KEY}
      - PYTHONPATH=/lmf_stack          # ← add this
    volumes:
      - /home/jared/git/ariel:/app:ro
      - /home/jared/Documents/Obsidian/Marlin:/vault
      - /home/jared/git/lmf/stack:/lmf_stack:ro   # ← add this
```

- [ ] **Step 2: Verify docker-compose config parses**

```bash
docker compose -f ~/git/docker-compose.yml config --quiet && echo "config OK"
```

Expected: `config OK` (no parse errors)

- [ ] **Step 3: Commit**

```bash
git -C ~/git add docker-compose.yml
git -C ~/git commit -m "feat: mount lmf/stack in ariel container and set PYTHONPATH"
```

---

## Task 10: Delete the duplicate from lmf-ollama-obsidian

**Files:**
- Delete: `~/git/lmf-ollama-obsidian/core/ariel/` (entire directory)

- [ ] **Step 1: Confirm the directory is genuinely a stale copy**

```bash
diff -rq ~/git/ariel/core/ariel/ ~/git/lmf-ollama-obsidian/core/ariel/ 2>&1
```

Expected: one diff (the syntax error in persona.py). Confirm no other useful content.

- [ ] **Step 2: Delete the duplicate**

```bash
rm -rf ~/git/lmf-ollama-obsidian/core/ariel/
```

- [ ] **Step 3: Verify the directory is gone**

```bash
ls ~/git/lmf-ollama-obsidian/core/
```

Expected: `ariel` is no longer listed.

- [ ] **Step 4: Commit**

```bash
git -C ~/git/lmf-ollama-obsidian add -A core/
git -C ~/git/lmf-ollama-obsidian commit -m "chore: remove stale ariel/ subpackage copy — canonical source is ariel repo"
```

---

## Task 11: Remove now-redundant files from ariel/core/

The original `backends.py` and `build_prompt.py` in `ariel/core/` are now canonical in LMF. Remove the copies from Ariel and confirm no test imports them directly.

**Files:**
- Delete: `~/git/ariel/core/backends.py`
- Delete: `~/git/ariel/core/build_prompt.py`

- [ ] **Step 1: Confirm no test directly imports these**

```bash
grep -r "from backends\|import backends\|from build_prompt\|import build_prompt" ~/git/ariel/tests/
```

Expected: no output. If any test imports them directly, update it to `from lmf.backends import ...` first.

- [ ] **Step 2: Confirm the orchestrator entry point doesn't import them directly**

```bash
grep "from backends\|from build_prompt" ~/git/ariel/core/orchestrator.py
```

Expected: no output (the new entry point only imports from `lmf`).

- [ ] **Step 3: Delete the files**

```bash
rm ~/git/ariel/core/backends.py ~/git/ariel/core/build_prompt.py
```

- [ ] **Step 4: Run full test suite to confirm nothing broke**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: same pass/fail counts as Task 8 Step 4.

- [ ] **Step 5: Commit**

```bash
git -C ~/git/ariel add -A core/backends.py core/build_prompt.py
git -C ~/git/ariel commit -m "chore: remove backends.py and build_prompt.py — now canonical in lmf package"
```

---

## Task 12: Final verification and PR prep

- [ ] **Step 1: Full integration smoke test (local, no Docker)**

```bash
cd ~/git/ariel && LMF_STACK_PATH=~/git/lmf/stack python3 -m pytest tests/ -v 2>&1
```

All tests that passed before the refactor must still pass.

- [ ] **Step 2: Verify LMF package imports cleanly from scratch**

```bash
python3 -c "
import sys
sys.path.insert(0, '$HOME/git/lmf/stack')
from lmf.orchestrator import Orchestrator, run_with
from lmf.backends import build_backend
from lmf.build_prompt import build_prompt
print('All LMF imports OK')
"
```

Expected: `All LMF imports OK`

- [ ] **Step 3: Verify Ariel entry point imports cleanly**

```bash
LMF_STACK_PATH=~/git/lmf/stack python3 -c "
import sys, os
sys.path.insert(0, os.environ['LMF_STACK_PATH'])
sys.path.insert(0, '$HOME/git/ariel/core')
from ariel.persona import ArielOrchestrator
print(ArielOrchestrator.__bases__)
"
```

Expected: `(<class 'lmf.orchestrator.Orchestrator'>,)`  ← confirms inheritance chain is correct.

- [ ] **Step 4: Summarize repo state and create PRs**

Check what's on each branch and open PRs:

```bash
git -C ~/git/lmf log feat/canonical-orchestrator --oneline
git -C ~/git/ariel log feat/import-from-lmf --oneline
git -C ~/git/lmf-ollama-obsidian log feat/drop-ariel-duplicate --oneline
```

---

## Self-Review

**Spec coverage:**
- [x] Base `Orchestrator` + `Handler` + `run_with()` extracted to LMF (Tasks 2–5)
- [x] `backends.py` and `build_prompt.py` moved to LMF (Tasks 3–4, 11)
- [x] Ariel imports from LMF via `PYTHONPATH` (Tasks 6–8)
- [x] Import mechanism wired in Docker Compose (Task 9)
- [x] Stale duplicate in `lmf-ollama-obsidian` deleted (Task 10)
- [x] Redundant files removed from `ariel/core/` (Task 11)
- [x] Test baseline maintained throughout (Tasks 7, 8, 11, 12)

**Placeholder scan:** None found — all steps contain exact commands or full code.

**Type/name consistency:** `run_with()` defined in Task 5, called in Task 7 entry point. `tools_config_path` param threaded consistently through `Orchestrator.__init__` and `run_with()`. `ArielOrchestrator` call to `super().__init__()` must pass `tools_config_path=_ARIEL_TOOLS_CONFIG` — this is done in Task 7 Step 2 via `run_with(..., tools_config_path=_ARIEL_TOOLS_CONFIG)`.

> **Note:** `ArielOrchestrator.__init__` currently calls `super().__init__(vault_path, test_mode)` without `tools_config_path`. When `run_with()` passes `tools_config_path` to the constructor, it will flow correctly because `run_with()` calls `orchestrator_class(vault_path, tools_config_path=tools_config_path)`. The `ArielOrchestrator.__init__` will need to accept and forward it: add `tools_config_path: Path | None = None` to its signature and pass `tools_config_path=tools_config_path` in `super().__init__(...)`. **This is an additional edit in Task 8 Step 2** — update `persona.py` signature at the same time as the import.
