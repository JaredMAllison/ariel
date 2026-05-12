# Plan: Ariel Write Battery — Full Integration Test Suite

**Spec:** `specs/2026-05-11-ariel-write-battery.md`
**Branch:** `feature/ariel-write-battery`
**Prereqs:** Items 0–6 merged (done). Write tools disabled in production (correct — gate must pass first).

---

## Task 1 — Write-enabled test config

**File:** `tests/tools.config.test.yaml`

Copy `core/tools.config.yaml`. Set `enabled: true` on:
- `append_to_file`
- `replace_lines`
- `create_file`
- `insert_after_heading`

Leave all read tools unchanged.

**Done when:** File exists and is valid YAML.

---

## Task 2 — Snapshot vault fixture

**File:** `tests/fixtures/__init__.py` (empty) + `tests/fixtures/snapshot_vault.py`

Create a `snapshot_vault` pytest fixture that builds this structure in `tmp_path`:

```
vault/
├── LOCAL_MIND_FOUNDATION.md  — "---\ntitle: test\n---"
├── Inbox.md                  — frontmatter + two items
├── Tasks/
│   ├── check-lola-oil.md     — valid task frontmatter, status: active, priority: 2
│   └── reschedule-dentist.md — valid task frontmatter + "## Notes" heading section
└── Projects/
    └── lmf.md                — valid project frontmatter
```

Frontmatter schema (from production vault):
```yaml
---
title: <string>
type: task
status: active
priority: <int>
created: 2026-05-11
context: [any-time]
tags: [task, active]
---
```

**Done when:** Fixture importable and `snapshot_vault` yields a Path with all files present.

---

## Task 3 — ArielOrchestrator test fixture

**File:** `tests/test_ariel_write_battery.py` (top section — imports + fixtures only)

```python
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from ariel.persona import ArielOrchestrator
from tests.fixtures.snapshot_vault import snapshot_vault  # noqa

TEST_CONFIG = Path(__file__).parent / "tools.config.test.yaml"

def _think(content: str):
    """Mock _call_backend return — Think step output."""
    return content

def _respond(content: str):
    """Mock _call_backend_with_history return — Respond step output."""
    return content

@pytest.fixture
def ariel(snapshot_vault):
    orch = ArielOrchestrator(
        str(snapshot_vault),
        test_mode=True,
        tools_config_path=str(TEST_CONFIG),
    )
    return orch
```

**Done when:** `ariel` fixture initializes without errors and `orch.vault` points to snapshot.

---

## Task 4 — Write all battery tests

**File:** `tests/test_ariel_write_battery.py` (body — all test functions)

Implement all 8 test cases from the spec:

1. `test_gate_fires_on_create_file` — Think returns create_file tool call → gate fires → pending_write set → "Confirm?" in reply
2. `test_create_file_confirm_writes_file` — continue above → "yes" → Tasks/check-on-jaina.md exists with title frontmatter
3. `test_append_to_inbox` — Think returns append_to_file → gate → confirm → Inbox.md updated, original content preserved
4. `test_replace_lines` — Think returns replace_lines → gate → confirm → line changed, rest unchanged
5. `test_insert_after_heading` — Think returns insert_after_heading → gate → confirm → content appears after heading
6. `test_path_traversal_blocked` — direct _dispatch_tool call with ../../etc/passwd → error, no file outside vault
7. `test_gate_clears_on_no` — gate fires → "no" → pending_write None → no file written
8. `test_write_tools_registered` — assert all four in `_WRITE_TOOLS` constant

For mocking, use:
```python
with patch.object(orch, "_call_backend", return_value=_think("... Tool: create_file(...)")):
    with patch.object(orch, "_call_backend_with_history", return_value=_respond("Task noted.")):
        reply = orch.chat("create a task to check on Jaina")
```

**Done when:** All 8 tests pass with `pytest tests/test_ariel_write_battery.py -v`.

---

## Task 5 — Run full test suite, verify no regressions

```bash
cd ~/git/ariel && pytest tests/ -v
```

All existing tests must still pass. The new battery adds 8 tests on top.

**Done when:** Full suite green. Report any failures with output.

---

## Definition of Done

- [ ] Task 1: `tests/tools.config.test.yaml` exists, writes enabled
- [ ] Task 2: `tests/fixtures/snapshot_vault.py` fixture works
- [ ] Task 3: `ariel` fixture initializes cleanly
- [ ] Task 4: All 8 battery tests implemented and passing
- [ ] Task 5: Full test suite green, no regressions
- [ ] PR created and ready for review
