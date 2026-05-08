# Initiation Mode — Design Spec

**Date:** 2026-05-07
**Status:** draft
**ADR:** lmf-adr-016-initiation-mode

---

## Overview

The orchestrator gains an **initiation mode** — a detectable first-run state that replaces the full Ariel assistant persona with a lightweight onboarding guide. The operator's first conversation with the system is profiling and setup, not form-filling. At the profiling threshold, the init persona writes `LOCAL_MIND_FOUNDATION.md`, seeds the vault, and hands off to Ariel.

---

## Architecture

```
Orchestrator.__init__()
  → _is_first_run()? Yes
      → Load core/prompts/init.md as system prompt
      → KB/tools disabled (no vault to read)
      → Track init_state for resume
  → _is_first_run()? No
      → Normal flow: build_prompt(), KB tools, etc.

chat()
  → In init mode? Check if response contains [INIT_COMPLETE]
      → Yes: Store profile, wait for operator confirmation
          → Confirmed: Write LOCAL_MIND_FOUNDATION.md, seed vault, reload prompt, introduce Ariel
          → Declined: Clear proposal, continue conversation
      → No: Normal chat with init persona

/reset
  → In init mode? Clear .init_state.json, reset conversation
  → Normal mode? Clear history as before
```

---

## Section 1 — First-Run Detection

### `_is_first_run()`

```python
def _is_first_run(self, vault: Path) -> bool:
    return not (vault / "LOCAL_MIND_FOUNDATION.md").exists()
```

Called once in `__init__()`. The sentinel file is `LOCAL_MIND_FOUNDATION.md` at the vault root. If absent, the instance has never been initialized.

### Init mode branch in `__init__()`

```python
self.is_init_mode = self._is_first_run(self.vault)
if self.is_init_mode:
    init_prompt_path = Path(__file__).parent / "prompts" / "init.md"
    self.system_prompt = init_prompt_path.read_text(encoding="utf-8")
    self.kb = None
    self.tools = []
    self.init_state = self._load_init_state()
    self.init_handoff = None  # pending completion proposal
    print("[orchestrator] Init mode — first run detected")
else:
    self.system_prompt, self.prompt_stats = build_prompt(vault_path)
    self.kb = KnowledgeBase(self.vault) if KB_AVAILABLE else None
    tools_config = Path(__file__).parent / "tools.config.yaml"
    self.tools = self._build_tools(tools_config) if self.kb else []
```

---

## Section 2 — Init Persona (`core/prompts/init.md`)

A standalone Markdown template file with these sections:

1. **Role** — lightweight onboarding guide, not full assistant
2. **Trust profile** — from deploy.yaml or defaults (personal/professional/mixed)
3. **Onboarding mode** — guided/quick/skip
4. **Behavioral rules** — 1-3 sentence responses, one question at a time, follow subject changes
5. **Question sets per profile** (per ADR-008):
   - **personal**: How should I refer to you? What brings you here today? How structured do you like things?
   - **professional**: What's your role? What kind of work do you need support with? Do you separate work from personal?
   - **mixed**: Combination of above
6. **Completion criteria** — populate LOCAL_MIND_FOUNDATION.md frontmatter:
   - `operator_name`, `primary_need`, `attention_profile`, `work_separate`, `household_size`
7. **Completion signal** — When confident, output `[INIT_COMPLETE]` on its own line, then present a natural-language summary, then ask for confirmation
8. **Handoff protocol** — On confirmation, the summary + profile is passed; on decline, continue
9. **Resume support** — If the operator partially completed setup, do not repeat answered questions
10. **Write gate** — May use append_to_file to Inbox.md only, for capturing thoughts during initiation
11. **Deploy config** — reads from operator/deploy.yaml if available, uses defaults otherwise

---

## Section 3 — Orchestrator Init Mode (`core/orchestrator.py`)

### Init state management

```python
INIT_STATE_PATH = "operator/.init_state.json"

def _load_init_state(self) -> dict:
    path = self.vault / INIT_STATE_PATH
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"phase": "interview", "answered_questions": [], "profile_draft": {}}

def _save_init_state(self):
    path = self.vault / INIT_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(self.init_state, indent=2), encoding="utf-8")

def _clear_init_state(self):
    path = self.vault / INIT_STATE_PATH
    if path.exists():
        path.unlink()
```

### Chat in init mode

The `chat()` method gains an init-mode branch. After getting the model response:

```python
if self.is_init_mode:
    if "[INIT_COMPLETE]" in reply:
        # Extract profile from response (after [INIT_COMPLETE])
        self.init_handoff = {"reply": reply, "profile_draft": self._extract_profile(reply)}
        return reply  # Contains summary + confirmation question
    
    if self.init_handoff and is_confirmation(user_message):
        return self._complete_initiation()
```

### Handoff flow

```python
def _complete_initiation(self) -> str:
    profile = self.init_handoff["profile_draft"]
    
    # 1. Write LOCAL_MIND_FOUNDATION.md
    foundation = self._build_foundation_md(profile)
    (self.vault / "LOCAL_MIND_FOUNDATION.md").write_text(foundation, encoding="utf-8")
    
    # 2. Seed vault directories if missing
    for d in ["Tasks", "Projects", "Daily"]:
        (self.vault / d).mkdir(parents=True, exist_ok=True)
    inbox = self.vault / "Inbox.md"
    if not inbox.exists():
        inbox.write_text("", encoding="utf-8")
    
    # 3. Reload system prompt with Ariel identity
    self.system_prompt, self.prompt_stats = build_prompt(str(self.vault))
    
    # 4. Switch out of init mode
    self.is_init_mode = False
    self.init_handoff = None
    self.kb = KnowledgeBase(self.vault) if KB_AVAILABLE else None
    tools_config = Path(__file__).parent / "tools.config.yaml"
    self.tools = self._build_tools(tools_config) if self.kb else []
    self._clear_init_state()
    
    # 5. Introduce Ariel
    return "Setup complete. Let me introduce you to your assistant: Ariel."
```

---

## Section 4 — Confirmation Gate (Covenant Term 6)

Three structural safeguards in init mode:

### 4.1 Unconditioned write access

The init persona has access to `append_to_file` to `Inbox.md` only. This is enforced in `_dispatch_tool()`:

```python
if self.is_init_mode:
    if name == "append_to_file" and args.get("file_path") == "Inbox.md":
        # Allow — write to inbox
        pass
    elif name in _WRITE_TOOLS:
        return "[In init mode, write tools are limited to Inbox.md]"
```

Note: `_WRITE_TOOLS` and `_CONFIRMATION_YES` constants from `feat/pdf-knowledge-base` are needed. Since initiation mode builds on main (which lacks these), we add minimal versions:

```python
_WRITE_TOOLS = {"append_to_file", "replace_lines", "create_file", "insert_after_heading"}
_CONFIRMATION_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "go ahead", "confirm", "do it"}
```

### 4.2 Explicit confirmation before persistence

The handoff does not proceed until the operator confirms. A `"no"` or anything other than _CONFIRMATION_YES returns to conversation.

### 4.3 Init is a mode, not a lock

The `/reset` endpoint:
- In init mode: `_clear_init_state()` + `reset()` (clear history)
- The init prompt knows about .init_state.json and will resume on restart

---

## Section 5 — `deploy.yaml` (Layer 1 Config)

New file at `operator/deploy.yaml`:

```yaml
instance_name: "my-instance"
trust_profile: "mixed"
onboarding_mode: "guided"
```

Created by:
1. `~/git/cockpit/deploy/windows/init.py` now prompts for these three fields
2. The orchestrator reads `operator/deploy.yaml` on init, with all-defaults fallback

Reading logic:

```python
def load_deploy_config(vault: Path) -> dict:
    path = vault / "operator" / "deploy.yaml"
    default = {"instance_name": "LMF", "trust_profile": "personal", "onboarding_mode": "guided"}
    if path.exists():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {**default, **cfg}
    return default
```

---

## Section 6 — Resume from Partial

`operator/.init_state.json` tracks progress:

```json
{"phase": "interview", "answered_questions": [], "profile_draft": {}}
```

Fields:
- `phase`: `"interview"` (before completion) or `"handoff"` (summary presented, awaiting confirmation)
- `answered_questions`: list of question IDs or topics already covered
- `profile_draft`: partially populated profile fields, updated after each significant exchange

The init prompt reads this state and adjusts its behavior: "The operator partially completed setup. Do not repeat questions already answered. Resume from where they left off."

**Phase 1 scope:** Track at conversation level only (no persistent structured answer log beyond the draft). If interrupted mid-init, the model re-reads `profile_draft` and `answered_questions` from state and resumes.

---

## Section 7 — Files Changed

| File | Change |
|------|--------|
| `core/prompts/init.md` | **NEW** — init persona template |
| `core/orchestrator.py` | Add `_is_first_run()`, init mode branch, `_complete_initiation()`, init state management, deploy.yaml reading, Covenant Term 6 safeguards |
| `operator/.init_state.json` | **NEW** — resume state (created at runtime, not committed to repo) |
| `operator/deploy.yaml` | **NEW** — deploy config (created by init.py) |
| `~/git/cockpit/deploy/windows/init.py` | Extend with instance_name, trust_profile, onboarding_mode prompts |

---

## Open Questions

1. **Resume-from-partial**: deploy to Phase 1 or defer to Phase 2? (handoff doc defers recommendation — first run unlikely to be interrupted)
2. **.init_state.json location**: inside the vault (operator/) or outside (e.g. ~/.local/share/lmf-init/)? Inside vault means it's portable with the vault; outside means it survives vault deletion.
