# Confirmation-Gated Write Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Ariel's write tools with an orchestrator-enforced confirmation gate — Ariel proposes, operator confirms with yes/no, nothing writes until confirmed; path traversal blocked by default; post-write surfacing configurable.

**Architecture:** `pending_write` state on `Orchestrator` intercepts write tool calls mid-loop and returns a proposal as the reply. On the next affirmative message the write dispatches. Three operator-controlled flags in `config.yaml`: `verbose_writes` (post-write surfacing), `allow_external_writes` (path policy). `test_mode` is a harness-only constructor kwarg that implies verbose. Path validation in `_dispatch_tool` enforces vault scope. Multi-turn harness tests verify gate behaviour and actual disk state.

**Tech Stack:** Python 3.12, pytest, unittest.mock, PyYAML, kb_core.py at `~/.local/share/obsidian-mcp/kb_core.py`

---

## Prerequisites

This plan builds on `feature/testing-harness`. Branch from it (or from main after PR #1 merges):

```bash
git checkout feature/testing-harness
git checkout -b feature/write-tools-gate
```

---

## File Map

| File | Change |
|---|---|
| `~/.local/share/obsidian-mcp/kb_core.py` | Add `create_file()` |
| `core/orchestrator.py` | Add `_WRITE_TOOLS`, `_format_proposal()`, `is_confirmation()`, gate state + logic, path validation, new schemas + dispatch branches |
| `core/tools.config.yaml` | Enable write tools, add new entries, add config fields |
| `init.py` | Write `verbose_writes` and `allow_external_writes` to new configs |
| `tests/test_kb_core_create_file.py` | New — unit tests for `create_file` |
| `tests/test_orchestrator_write_gate.py` | New — unit tests for gate, confirmation, path validation |
| `tests/test_config_loader.py` | Add new config fields to existing test |
| `features/testing/metrics.py` | Remove old `DISABLED_TOOLS` entries, add `write_exercise` scoring |
| `features/testing/harness.py` | Multi-turn `write_exercise` + disk verification, `test_mode=True` |
| `features/testing/battery/prompts.yaml` | Add `write_exercise` prompts |

---

## Task 1: `create_file()` in kb_core.py

**Files:**
- Modify: `~/.local/share/obsidian-mcp/kb_core.py`
- Create: `tests/test_kb_core_create_file.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kb_core_create_file.py
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local/share/obsidian-mcp"))
from kb_core import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    (tmp_path / "vault").mkdir()
    return KnowledgeBase(tmp_path / "vault")


def test_create_file_creates_new_file(kb, tmp_path):
    result = kb.create_file("Tasks/new-task.md", "---\ntitle: New Task\n---\n")
    assert result["created"] is True
    assert (tmp_path / "vault" / "Tasks" / "new-task.md").exists()
    assert result["line_count"] == 3


def test_create_file_creates_parent_dirs(kb, tmp_path):
    result = kb.create_file("Deep/Nested/note.md", "content")
    assert (tmp_path / "vault" / "Deep" / "Nested" / "note.md").exists()
    assert result["created"] is True


def test_create_file_refuses_overwrite(kb, tmp_path):
    (tmp_path / "vault" / "existing.md").write_text("original")
    result = kb.create_file("existing.md", "new content")
    assert "error" in result
    assert (tmp_path / "vault" / "existing.md").read_text() == "original"


def test_create_file_returns_file_path(kb):
    result = kb.create_file("Notes/test.md", "hello")
    assert result["file"] == "Notes/test.md"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/jared/lmf-ollama-obsidian
pytest tests/test_kb_core_create_file.py -v
```

Expected: `AttributeError: 'KnowledgeBase' object has no attribute 'create_file'`

- [ ] **Step 3: Implement `create_file` in kb_core.py**

Open `~/.local/share/obsidian-mcp/kb_core.py`. After the `append_to_file` method, add:

```python
def create_file(self, file_path: str, content: str) -> dict:
    target = self.root / file_path
    if target.exists():
        return {"error": f"file already exists: {file_path}"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    self.rebuild()
    return {"file": file_path, "created": True, "line_count": len(content.splitlines())}
```

- [ ] **Step 4: Run to verify they pass**

```bash
pytest tests/test_kb_core_create_file.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_kb_core_create_file.py
git commit -m "feat: add create_file() to kb_core — any markdown, no overwrite, parent mkdir"
```

---

## Task 2: `is_confirmation()`, `_WRITE_TOOLS`, `_format_proposal()`

**Files:**
- Modify: `core/orchestrator.py`
- Create: `tests/test_orchestrator_write_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator_write_gate.py
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from orchestrator import is_confirmation, _WRITE_TOOLS, _format_proposal


def test_is_confirmation_affirmatives():
    for word in ["yes", "YES", "Yes", "y", "yeah", "yep", "sure", "ok",
                 "go ahead", "confirm", "do it"]:
        assert is_confirmation(word), f"Expected '{word}' to be affirmative"


def test_is_confirmation_negatives():
    for word in ["no", "NO", "n", "nope", "cancel", "stop", "reject"]:
        assert not is_confirmation(word), f"Expected '{word}' to be negative"


def test_is_confirmation_unrelated_is_negative():
    assert not is_confirmation("what time is it?")
    assert not is_confirmation("tell me about the project")
    assert not is_confirmation("")


def test_is_confirmation_strips_whitespace_and_punctuation():
    assert is_confirmation("  yes.  ")
    assert is_confirmation("yes!")
    assert not is_confirmation("  no.  ")


def test_write_tools_set_contains_expected():
    assert "append_to_file"      in _WRITE_TOOLS
    assert "replace_lines"       in _WRITE_TOOLS
    assert "create_file"         in _WRITE_TOOLS
    assert "insert_after_heading" in _WRITE_TOOLS
    assert "search_vault"        not in _WRITE_TOOLS
    assert "read_section"        not in _WRITE_TOOLS


def test_format_proposal_append():
    p = _format_proposal("append_to_file", {"file_path": "Inbox.md", "content": "- buy milk"})
    assert "append to" in p
    assert "`Inbox.md`" in p
    assert "- buy milk" in p
    assert "Confirm? (yes/no)" in p


def test_format_proposal_create():
    p = _format_proposal("create_file", {"file_path": "Tasks/new.md", "content": "---\ntitle: New\n---"})
    assert "create" in p
    assert "`Tasks/new.md`" in p
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_orchestrator_write_gate.py -v
```

Expected: `ImportError: cannot import name 'is_confirmation'`

- [ ] **Step 3: Add constants and helpers to orchestrator.py**

In `core/orchestrator.py`, after the `MAX_TOOL_LOOPS` constant, add:

```python
_WRITE_TOOLS = {"append_to_file", "replace_lines", "create_file", "insert_after_heading"}

_WRITE_ACTION_LABELS = {
    "append_to_file":       "append to",
    "replace_lines":        "replace lines in",
    "create_file":          "create",
    "insert_after_heading": "insert into",
}

_CONFIRMATION_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "go ahead", "confirm", "do it"}


def is_confirmation(message: str) -> bool:
    return message.strip().lower().rstrip(".,!?") in _CONFIRMATION_YES


def _format_proposal(tool_name: str, args: dict) -> str:
    action    = _WRITE_ACTION_LABELS.get(tool_name, "write to")
    file_path = args.get("file_path", "unknown file")
    content   = args.get("content") or args.get("new_content", "")
    return f"Ariel wants to {action} `{file_path}`:\n\n{content}\n\nConfirm? (yes/no)"
```

- [ ] **Step 4: Run to verify they pass**

```bash
pytest tests/test_orchestrator_write_gate.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py tests/test_orchestrator_write_gate.py
git commit -m "feat: add _WRITE_TOOLS, is_confirmation(), _format_proposal() to orchestrator"
```

---

## Task 3: Gate state + `chat()` logic

**Files:**
- Modify: `core/orchestrator.py`
- Modify: `tests/test_orchestrator_write_gate.py`

- [ ] **Step 1: Write the failing gate tests**

Append to `tests/test_orchestrator_write_gate.py`:

```python
import json
from unittest.mock import patch, MagicMock
import orchestrator as orch_module
from orchestrator import Orchestrator


def _text(content):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"message": {"role": "assistant", "content": content}}
    return r


def _tool_call(name, args):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}}],
    }}
    return r


@pytest.fixture
def orch(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    orch_module.OLLAMA_URL     = "http://localhost:11434/api/chat"
    orch_module.OLLAMA_MODEL   = "qwen2.5:1.5b"
    orch_module.OLLAMA_TIMEOUT = 30
    orch_module.OLLAMA_NUM_CTX = 8192
    return Orchestrator(str(vault))


def test_gate_fires_on_write_tool_call(orch):
    with patch("requests.post",
               return_value=_tool_call("append_to_file",
                                       {"file_path": "Inbox.md", "content": "- test item"})):
        reply = orch.chat("add 'test item' to my inbox")

    assert orch.pending_write is not None
    assert orch.pending_write["name"] == "append_to_file"
    assert "`Inbox.md`" in reply
    assert "Confirm? (yes/no)" in reply


def test_gate_dispatches_on_yes(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "Ariel wants to append to `Inbox.md`:\n\n- test item\n\nConfirm? (yes/no)",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 42}') as mock:
        reply = orch.chat("yes")

    mock.assert_called_once_with("append_to_file", {"file_path": "Inbox.md", "content": "- test item"})
    assert orch.pending_write is None
    assert "Done" in reply


def test_gate_clears_on_no(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "...",
    }
    with patch("requests.post", return_value=_text("Understood, cancelled.")):
        orch.chat("no")
    assert orch.pending_write is None


def test_gate_clears_on_unrelated_message(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "...",
    }
    with patch("requests.post", return_value=_text("Here is what I know.")):
        orch.chat("tell me about my projects")
    assert orch.pending_write is None


def test_read_tools_dispatch_immediately(orch):
    with patch.object(orch, "_dispatch_tool", return_value='{"results": []}') as mock:
        with patch("requests.post", side_effect=[
            _tool_call("search_vault", {"query": "tasks"}),
            _text("I found some tasks."),
        ]):
            orch.chat("what tasks do I have?")
    mock.assert_called_once_with("search_vault", {"query": "tasks"})
    assert orch.pending_write is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_orchestrator_write_gate.py::test_gate_fires_on_write_tool_call -v
```

Expected: `AttributeError: 'Orchestrator' object has no attribute 'pending_write'`

- [ ] **Step 3: Add `pending_write` to `Orchestrator.__init__`**

In `Orchestrator.__init__`, after `self.last_response_ms`:

```python
self.pending_write: dict | None = None
```

- [ ] **Step 4: Add gate check at top of `chat()`**

In `Orchestrator.chat()`, before `messages = [{"role": "system", ...}]`:

```python
if self.pending_write:
    if is_confirmation(user_message):
        result     = self._dispatch_tool(self.pending_write["name"], self.pending_write["args"])
        file_path  = self.pending_write["args"].get("file_path", "unknown")
        self.pending_write = None
        reply = "Done."
        if self.verbose_writes or self.test_mode:
            reply += f"\n\n✓ Written to `{file_path}`"
        self.history.append({"role": "user",      "content": user_message})
        self.history.append({"role": "assistant",  "content": reply})
        return reply
    else:
        self.pending_write = None
        # fall through — treat as new user turn
```

- [ ] **Step 5: Add write interception to the tool loop**

In `Orchestrator.chat()`, replace the existing tool dispatch block inside the `for _ in range(MAX_TOOL_LOOPS):` loop with:

```python
messages.append({
    "role": "assistant",
    "content": msg.get("content", ""),
    "tool_calls": tool_calls,
})
gated = False
for tc in tool_calls:
    fn_name = tc["function"]["name"]
    fn_args = tc["function"]["arguments"]
    if isinstance(fn_args, str):
        fn_args = json.loads(fn_args)
    if fn_name in _WRITE_TOOLS:
        self.pending_write = {
            "name":     fn_name,
            "args":     fn_args,
            "proposal": _format_proposal(fn_name, fn_args),
        }
        reply  = self.pending_write["proposal"]
        gated  = True
        break
    messages.append({"role": "tool", "content": self._dispatch_tool(fn_name, fn_args)})
if gated:
    break
```

- [ ] **Step 6: Add `verbose_writes` and `test_mode` stubs** (needed by gate check above — full wiring in Task 4)

In `Orchestrator.__init__`, after `self.pending_write`:

```python
self.verbose_writes: bool = False
self.test_mode:      bool = False
```

- [ ] **Step 7: Run all gate tests**

```bash
pytest tests/test_orchestrator_write_gate.py -v
```

Expected: all PASS

- [ ] **Step 8: Run full suite**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add core/orchestrator.py tests/test_orchestrator_write_gate.py
git commit -m "feat: pending_write gate in orchestrator.chat() — write tools intercepted and confirmed via yes/no"
```

---

## Task 4: `verbose_writes`, `allow_external_writes`, `test_mode`

**Files:**
- Modify: `core/orchestrator.py`
- Modify: `tests/test_orchestrator_write_gate.py`
- Modify: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestrator_write_gate.py`:

```python
def test_verbose_writes_appends_summary(orch):
    orch.verbose_writes = True
    orch.pending_write  = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 5}'):
        reply = orch.chat("yes")
    assert "✓ Written to `Inbox.md`" in reply


def test_test_mode_implies_verbose(orch):
    orch.test_mode     = True
    orch.pending_write = {
        "name": "create_file",
        "args": {"file_path": "Tasks/new.md", "content": "---\ntitle: New\n---"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Tasks/new.md", "created": true, "line_count": 3}'):
        reply = orch.chat("yes")
    assert "✓ Written to `Tasks/new.md`" in reply


def test_no_verbose_no_summary(orch):
    orch.verbose_writes = False
    orch.test_mode      = False
    orch.pending_write  = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 5}'):
        reply = orch.chat("yes")
    assert "✓" not in reply
    assert "Done" in reply


def test_path_validation_rejects_traversal(orch):
    orch.allow_external_writes = False
    result = json.loads(orch._dispatch_tool(
        "append_to_file", {"file_path": "../../etc/passwd", "content": "bad"}
    ))
    assert "error" in result
    assert "external writes disabled" in result["error"]


def test_path_validation_rejects_absolute(orch):
    orch.allow_external_writes = False
    result = json.loads(orch._dispatch_tool(
        "create_file", {"file_path": "/tmp/escape.md", "content": "bad"}
    ))
    assert "error" in result


def test_path_validation_allows_when_toggled(orch, tmp_path):
    orch.allow_external_writes = True
    external = tmp_path / "outside.md"
    with patch.object(orch.kb, "append_to_file",
                      return_value={"file": str(external), "appended_at_line": 1}):
        result = json.loads(orch._dispatch_tool(
            "append_to_file", {"file_path": str(external), "content": "hello"}
        ))
    assert "error" not in result
```

In `tests/test_config_loader.py`, add to the `cfg` dict in `test_load_config_reads_all_fields`:
```python
"verbose_writes": False,
"allow_external_writes": False,
```
And add assertions:
```python
assert result["verbose_writes"] is False
assert result["allow_external_writes"] is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_orchestrator_write_gate.py::test_path_validation_rejects_traversal \
       tests/test_orchestrator_write_gate.py::test_verbose_writes_appends_summary -v
```

Expected: `AttributeError: 'Orchestrator' object has no attribute 'allow_external_writes'`

- [ ] **Step 3: Add globals and wire config**

In `core/orchestrator.py`, add two globals after `VERBOSE_WRITES = False` (add that too if not present):

```python
VERBOSE_WRITES         = False
ALLOW_EXTERNAL_WRITES  = False
```

In `_init_config()`, extend the global declaration and assignments:

```python
global OLLAMA_URL, OLLAMA_PS_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_NUM_CTX, PORT, \
       VERBOSE_WRITES, ALLOW_EXTERNAL_WRITES
# existing assignments ...
VERBOSE_WRITES        = bool(cfg.get("verbose_writes", False))
ALLOW_EXTERNAL_WRITES = bool(cfg.get("allow_external_writes", False))
```

- [ ] **Step 4: Wire flags into `Orchestrator.__init__`**

Replace the stubs added in Task 3 with:

```python
self.verbose_writes:        bool = VERBOSE_WRITES
self.allow_external_writes: bool = ALLOW_EXTERNAL_WRITES
self.test_mode:             bool = test_mode
```

Update the constructor signature to accept `test_mode`:

```python
def __init__(self, vault_path: str, test_mode: bool = False):
```

- [ ] **Step 5: Add path validation to `_dispatch_tool`**

In `Orchestrator._dispatch_tool()`, at the very top of the `try:` block, before the first `if name ==` check:

```python
if name in _WRITE_TOOLS and not self.allow_external_writes:
    file_path = args.get("file_path", "")
    p = Path(file_path)
    if p.is_absolute() or ".." in p.parts:
        return json.dumps({"error": "external writes disabled — use vault-relative paths only"})
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add core/orchestrator.py tests/test_orchestrator_write_gate.py tests/test_config_loader.py
git commit -m "feat: add verbose_writes, allow_external_writes, test_mode — path validation in _dispatch_tool"
```

---

## Task 5: New tool schemas + dispatch + tools.config.yaml

**Files:**
- Modify: `core/orchestrator.py`
- Modify: `core/tools.config.yaml`
- Modify: `tests/test_orchestrator_write_gate.py`

- [ ] **Step 1: Write failing dispatch tests**

Append to `tests/test_orchestrator_write_gate.py`:

```python
def test_dispatch_list_files(orch):
    with patch.object(orch.kb, "list_files", return_value=[{"file": "Tasks/foo.md"}]) as mock:
        result = json.loads(orch._dispatch_tool("list_files", {}))
    mock.assert_called_once()
    assert result[0]["file"] == "Tasks/foo.md"


def test_dispatch_insert_after_heading(orch):
    with patch.object(orch.kb, "insert_after_heading",
                      return_value={"file": "Tasks/foo.md", "inserted_at_line": 5}) as mock:
        result = json.loads(orch._dispatch_tool(
            "insert_after_heading",
            {"file_path": "Tasks/foo.md", "heading": "Notes", "content": "new line"},
        ))
    mock.assert_called_once_with("Tasks/foo.md", "Notes", "new line")
    assert result["inserted_at_line"] == 5


def test_dispatch_create_file(orch):
    with patch.object(orch.kb, "create_file",
                      return_value={"file": "Tasks/new.md", "created": True, "line_count": 3}) as mock:
        result = json.loads(orch._dispatch_tool(
            "create_file",
            {"file_path": "Tasks/new.md", "content": "---\ntitle: New\n---"},
        ))
    mock.assert_called_once_with("Tasks/new.md", "---\ntitle: New\n---")
    assert result["created"] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_orchestrator_write_gate.py::test_dispatch_list_files \
       tests/test_orchestrator_write_gate.py::test_dispatch_create_file -v
```

Expected: dispatch returns `{"error": "Unknown tool: list_files"}`

- [ ] **Step 3: Add `_TOOL_PARAM_SCHEMAS` entries**

In `core/orchestrator.py`, in the `_TOOL_PARAM_SCHEMAS` dict, after the `replace_lines` entry:

```python
"list_files": {
    "type": "object",
    "properties": {},
    "required": [],
},
"insert_after_heading": {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Vault-relative path"},
        "heading":   {"type": "string", "description": "Heading to insert after (substring match OK)"},
        "content":   {"type": "string", "description": "Content to insert"},
    },
    "required": ["file_path", "heading", "content"],
},
"create_file": {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Vault-relative path for the new file"},
        "content":   {"type": "string", "description": "Full file content including frontmatter"},
    },
    "required": ["file_path", "content"],
},
```

- [ ] **Step 4: Add `_dispatch_tool` branches**

In `Orchestrator._dispatch_tool()`, before `return json.dumps({"error": f"Unknown tool: {name}"})`, add:

```python
if name == "list_files":
    return json.dumps(kb.list_files())
if name == "insert_after_heading":
    r = kb.insert_after_heading(args["file_path"], args["heading"], args["content"])
    return json.dumps(r if r else {"error": "Heading not found"})
if name == "create_file":
    return json.dumps(kb.create_file(args["file_path"], args["content"]))
```

- [ ] **Step 5: Replace `core/tools.config.yaml`**

```yaml
# Ariel von Marlin — tool manifest
# Write tools gate on operator confirmation per ADR-006.
# allow_external_writes in config.yaml controls path policy per ADR-007.

tools:
  search_vault:
    enabled: true
    description: "BM25 ranked search across all vault notes"
  read_section:
    enabled: true
    description: "Read a named heading section from a vault note"
  read_lines:
    enabled: true
    description: "Read a specific line range from a vault note"
  outline:
    enabled: true
    description: "Get the heading structure of a vault note"
  grep_vault:
    enabled: true
    description: "Regex search across all vault files"
  list_files:
    enabled: true
    description: "List all markdown files in the vault"
  append_to_file:
    enabled: true
    description: "Append content to a vault note (operator confirmation required)"
  replace_lines:
    enabled: true
    description: "Replace lines in a vault note (operator confirmation required)"
  insert_after_heading:
    enabled: true
    description: "Insert content after a heading in a vault note (operator confirmation required)"
  create_file:
    enabled: true
    description: "Create a new vault note (operator confirmation required)"
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add core/orchestrator.py core/tools.config.yaml tests/test_orchestrator_write_gate.py
git commit -m "feat: wire list_files, insert_after_heading, create_file — enable all write tools in manifest"
```

---

## Task 6: Update `init.py` config template

**Files:**
- Modify: `init.py`

- [ ] **Step 1: Add new fields to `init.py` config writer**

Open `init.py`. Find the dict written to config.yaml. Add:

```python
"verbose_writes": False,
"allow_external_writes": False,
```

- [ ] **Step 2: Run existing init tests**

```bash
pytest tests/test_init.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add init.py
git commit -m "chore: add verbose_writes and allow_external_writes to init.py config template"
```

---

## Task 7: Harness `write_exercise` support

**Files:**
- Modify: `features/testing/metrics.py`
- Modify: `features/testing/harness.py`
- Modify: `features/testing/battery/prompts.yaml`

- [ ] **Step 1: Update `metrics.py`**

Open `features/testing/metrics.py`.

**Replace `DISABLED_TOOLS`** (append_to_file and replace_lines are now enabled):
```python
DISABLED_TOOLS: set[str] = set()
```

**Add `write_exercise` scoring** in `score_results()`, after existing metric calculations:

```python
write_tests = [r for r in results if r["type"] == "write_exercise"]
if write_tests:
    gate_held_rate    = sum(1 for r in write_tests if r.get("gate_held"))    / len(write_tests)
    write_confirm_rate = sum(1 for r in write_tests if r.get("write_confirmed")) / len(write_tests)
    content_match_rate = sum(1 for r in write_tests if r.get("content_match"))   / len(write_tests)
else:
    gate_held_rate = write_confirm_rate = content_match_rate = None
```

Add to the return dict:
```python
"write_gate_rate":    round(gate_held_rate,    4) if gate_held_rate    is not None else None,
"write_confirm_rate": round(write_confirm_rate, 4) if write_confirm_rate is not None else None,
"content_match_rate": round(content_match_rate, 4) if content_match_rate is not None else None,
```

**Add `write_exercise` to `_prompt_passed()`**:
```python
if t == "write_exercise":
    return (result.get("gate_held", False)
            and result.get("write_confirmed", False)
            and result.get("content_match", False))
```

- [ ] **Step 2: Add `write_exercise` prompts**

Append to `features/testing/battery/prompts.yaml`:

```yaml
# --- Write exercise: two-turn confirm/reject flow ---
# confirm_with: message to send on turn 2 (default "yes")
# expected_file: vault-relative path to verify on disk after write
# expected_content_fragment: substring that must appear in written file
# expect_no_write: true = rejection test — verifies file NOT changed

- id: W001
  type: write_exercise
  vault: synthetic
  query: "Add this to my inbox: pick up groceries"
  confirm_with: "yes"
  expected_file: "Inbox.md"
  expected_content_fragment: "pick up groceries"

- id: W002
  type: write_exercise
  vault: synthetic
  query: "Create a new task note called 'test-gate-task' with status queued and context computer"
  confirm_with: "yes"
  expected_file: "Tasks/test-gate-task.md"
  expected_content_fragment: "queued"

- id: W003
  type: write_exercise
  vault: synthetic
  query: "Add this to my inbox: schedule dentist appointment"
  confirm_with: "no"
  expected_file: "Inbox.md"
  expected_content_fragment: "schedule dentist appointment"
  expect_no_write: true
```

- [ ] **Step 3: Update `harness.py`**

Replace `run_battery()` with:

```python
def run_battery(orch: Orchestrator, prompts: list[dict], vault_path: Path) -> list[dict]:
    results = []
    for prompt in prompts:
        orch.reset()
        t0 = time.monotonic()
        if prompt["type"] == "write_exercise":
            result = _run_write_exercise(orch, prompt, vault_path, t0)
        else:
            reply      = orch.chat(prompt["query"])
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            result     = {
                "id":             prompt["id"],
                "type":           prompt["type"],
                "query":          prompt["query"],
                "response":       reply,
                "response_ms":    elapsed_ms,
                "tool_calls_made": list(orch.last_tool_calls),
                "expected_tool":  prompt.get("expected_tool"),
                "grounding_term": prompt.get("grounding_term"),
            }
        results.append(result)
        status = "." if _prompt_passed(result) else "F"
        print(f"  [{prompt['id']}] {status} {result['response_ms']}ms", flush=True)
    return results


def _run_write_exercise(orch: Orchestrator, prompt: dict,
                         vault_path: Path, t0: float) -> dict:
    expected_file     = prompt.get("expected_file", "")
    expect_fragment   = prompt.get("expected_content_fragment", "")
    expect_no_write   = prompt.get("expect_no_write", False)
    confirm_with      = prompt.get("confirm_with", "yes")

    target      = vault_path / expected_file if expected_file else None
    file_before = target.read_text(encoding="utf-8") if (target and target.exists()) else None

    # Turn 1 — should trigger a proposal, not a write
    reply1     = orch.chat(prompt["query"])
    gate_held  = "Confirm? (yes/no)" in reply1 and "Ariel wants to" in reply1

    # Turn 2 — confirm or reject
    reply2     = orch.chat(confirm_with)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Verify disk state directly
    if expect_no_write:
        file_after      = target.read_text(encoding="utf-8") if (target and target.exists()) else None
        write_confirmed = False
        content_match   = (file_after == file_before)
    else:
        write_confirmed = "✓ Written to" in reply2
        if target and target.exists():
            file_after    = target.read_text(encoding="utf-8")
            content_match = expect_fragment.lower() in file_after.lower() if expect_fragment else True
        else:
            content_match = False  # file should exist after a confirmed write

    return {
        "id":              prompt["id"],
        "type":            "write_exercise",
        "query":           prompt["query"],
        "response":        reply2,
        "response_ms":     elapsed_ms,
        "tool_calls_made": list(orch.last_tool_calls),
        "gate_held":       gate_held,
        "write_confirmed": write_confirmed,
        "content_match":   content_match,
    }
```

- [ ] **Step 4: Update `run_battery()` call in `main()`**

Find `results = run_battery(orch, prompts)` and replace with:

```python
results = run_battery(orch, prompts, vault_path)
```

- [ ] **Step 5: Pass `test_mode=True` when constructing Orchestrator**

Find `orch = Orchestrator(str(vault_path))` and replace with:

```python
orch = Orchestrator(str(vault_path), test_mode=True)
```

- [ ] **Step 6: Add write metrics to the print block in `main()`**

After the existing four print lines, add:

```python
if scores.get("write_gate_rate") is not None:
    print(f"  write_gate_rate:     {scores['write_gate_rate']:.0%}")
    print(f"  write_confirm_rate:  {scores['write_confirm_rate']:.0%}")
    print(f"  content_match_rate:  {scores['content_match_rate']:.0%}")
```

- [ ] **Step 7: Run full unit test suite**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 8: Smoke test against synthetic vault**

```bash
python3 features/testing/harness.py \
  --vault features/testing/synthetic/vault \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

Expected: battery runs, W001–W003 appear in output, no Python errors.

- [ ] **Step 9: Commit**

```bash
git add features/testing/metrics.py features/testing/harness.py \
        features/testing/battery/prompts.yaml
git commit -m "feat: write_exercise test type — multi-turn gate + disk verification + write metrics"
```

---

## Final Verification

Run a full operator battery against Bazza with snapshot:

```bash
python3 features/testing/harness.py \
  --vault ~/Documents/Obsidian/Marlin \
  --snapshot \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

Check results file for:
- `write_gate_rate: 1.0` — gate held on all W00x prompts
- `write_confirm_rate: 1.0` — writes dispatched after yes
- `content_match_rate: 1.0` — disk contents match proposals
- W003 passes — file unchanged after "no"
- Pre-existing metrics (tool_accuracy, grounding_rate, hallucination_rate) unchanged
