# Spec: Ariel Write Battery — Full Integration Test Suite

**Date:** 2026-05-11
**Status:** ready for implementation
**OpenCode plan:** `plans/2026-05-11-ariel-write-battery.md`

---

## Problem

Write tools (`append_to_file`, `replace_lines`, `create_file`, `insert_after_heading`) are enabled=false in production. Before enabling them, a full test suite must verify:

1. All four tools work end-to-end through `ArielOrchestrator` (not just the base `Orchestrator`)
2. The write gate fires correctly in the Ariel persona's Think→Read→Respond flow
3. File I/O lands correctly on a realistic vault snapshot — not an empty tmp_path

The existing `test_orchestrator_write_gate.py` tests the gate against the base `Orchestrator` with `requests.post` mocked. ArielOrchestrator overrides `chat()` entirely and uses `_call_backend`/`_call_backend_with_history` via the LMF backend abstraction — those mocks don't reach it.

---

## Scope

### New file: `tests/tools.config.test.yaml`

Copy of `core/tools.config.yaml` with all four write tools set `enabled: true`. Used only in test fixtures — never deployed.

### New file: `tests/fixtures/snapshot_vault.py`

A `snapshot_vault` pytest fixture that builds a realistic vault in `tmp_path`:

```
vault/
├── Inbox.md               — has frontmatter + two existing items
├── Tasks/
│   ├── check-lola-oil.md  — status: active, priority: 2
│   └── reschedule-dentist.md — status: active, priority: 1
├── Projects/
│   └── lmf.md             — status: active, brief: "Local Mind Framework"
└── LOCAL_MIND_FOUNDATION.md
```

Frontmatter on task files must be valid (same schema as production vault) so `create_file` tests can verify the schema of the written output.

### New file: `tests/test_ariel_write_battery.py`

Full battery test suite. All tests use:
- `snapshot_vault` fixture (realistic vault content)
- `ArielOrchestrator` initialized with `tools_config_path=tests/tools.config.test.yaml` and `test_mode=True`
- Backends mocked via `unittest.mock.patch.object(orch, "_call_backend")` and `patch.object(orch, "_call_backend_with_history")`

---

## Test Cases

### Fixture

```python
@pytest.fixture
def ariel(snapshot_vault):
    test_config = Path(__file__).parent / "tools.config.test.yaml"
    orch = ArielOrchestrator(str(snapshot_vault), test_mode=True, tools_config_path=str(test_config))
    return orch
```

### Gate fires on write tool call from Think step

The Think step (`_call_backend`) returns a Think block containing a `Tool: create_file(...)` call. Verify that after `orch.chat("create a task to check on Jaina")`, `orch.pending_write` is set and the reply contains "Confirm?".

```
Think mock output:
  "I should create a task note for checking on Jaina.
   Tool: create_file("Tasks/check-on-jaina.md", "---\ntitle: Check on Jaina\nstatus: active\n---\n")"

Assert: orch.pending_write["name"] == "create_file"
Assert: "Confirm?" in reply
```

### create_file — confirm → file written

Continue from above. Send `orch.chat("yes")`. Verify:
- `(snapshot_vault / "Tasks/check-on-jaina.md").exists()` is True
- File contains valid frontmatter (`title:` present)
- `orch.pending_write is None`

### append_to_file — inbox append

```
Think mock: Tool: append_to_file("Inbox.md", "- check on Jaina")
Assert: gate fires
Confirm "yes"
Assert: Inbox.md content ends with "- check on Jaina"
Assert: original Inbox.md items still present (non-destructive)
```

### replace_lines — status update

```
Think mock: Tool: replace_lines("Tasks/check-lola-oil.md", 4, 4, "status: done")
Assert: gate fires
Confirm "yes"
Assert: check-lola-oil.md line 4 is now "status: done"
Assert: rest of file unchanged
```

### insert_after_heading

```
Think mock: Tool: insert_after_heading("Tasks/reschedule-dentist.md", "Notes", "Call back Dr. Kim")
Assert: gate fires
Confirm "yes"
Assert: "Call back Dr. Kim" appears after ## Notes heading
```

### Path traversal blocked even with writes enabled

```
orch._dispatch_tool("append_to_file", {"file_path": "../../etc/passwd", "content": "x"})
Assert: result contains "error"
Assert: no file written outside vault
```

### Gate clears on "no"

```
Think mock → gate fires → send "no"
Assert: pending_write is None
Assert: no file written
```

### All four tools registered in _WRITE_TOOLS

Verify the constant includes all four: `create_file`, `append_to_file`, `replace_lines`, `insert_after_heading`. (Regression guard — if a tool is renamed, this catches it.)

---

## What NOT in scope

- Live backend calls (no Groq or Ollama in CI)
- Testing Think quality (prompt engineering, not structural correctness)
- Testing the retrieval loop (Item 3) — separate concern
- Performance testing

---

## How to enable writes in production

After this battery passes:

1. In `core/tools.config.yaml`: set `enabled: true` on all four write tools
2. Restart the orchestrator container
3. Ariel will propose writes and wait for confirmation — no silent writes

The write gate is already production-ready (tested in `test_orchestrator_write_gate.py`). This battery is the final gate before enabling.
