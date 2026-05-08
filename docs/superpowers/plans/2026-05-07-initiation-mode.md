# Initiation Mode — Task Plan

**Date:** 2026-05-07
**Spec:** `docs/superpowers/specs/2026-05-07-initiation-mode-design.md`
**Worktree:** `.worktrees/initiation-mode` (branch: `feature/initiation-mode`)

---

## Tasks

### Task 1: Create `core/prompts/init.md` — Init Persona Template

**Files:** `core/prompts/init.md` (NEW)

Write the init persona template. Must include:
- Role definition (onboarding guide, not full assistant)
- Trust profile + onboarding mode section (from deploy.yaml or defaults)
- Question sets per profile (personal, professional, mixed)
- Behavioral rules: 1-3 sentence responses, one question at a time, follow subject changes
- Completion criteria + `[INIT_COMPLETE]` signal output format
- Handoff protocol instructions
- Resume-from-partial awareness
- Write gate: append_to_file to Inbox.md only

**Verification:** File exists, reads as valid Markdown, contains all required sections.

---

### Task 2: Modify `core/orchestrator.py` — Init Mode Core

**Files:** `core/orchestrator.py`

Add to the `Orchestrator` class and module level:

1. `_WRITE_TOOLS` and `_CONFIRMATION_YES` constants (needed for Covenant Term 6)
2. `is_confirmation()` helper function
3. `load_deploy_config(vault)` function
4. `_is_first_run(self, vault)` method
5. Init mode branch in `__init__()` — load init.md if first run, disable KB/tools
6. `_load_init_state()`, `_save_init_state()`, `_clear_init_state()` methods
7. `_extract_profile(reply)` — parse profile from `[INIT_COMPLETE]` response
8. `_build_foundation_md(profile)` — assemble LOCAL_MIND_FOUNDATION.md
9. `_complete_initiation()` — write files, seed vault, reload prompt, introduce Ariel
10. Init mode handling in `chat()` — detect `[INIT_COMPLETE]`, handoff on confirmation
11. Init mode write gate in `_dispatch_tool()` — only allow append_to_file to Inbox.md
12. `/reset` enhancement — clear init state in init mode
13. `init_state` and `init_handoff` fields on Orchestrator

**Verification:** `python3 -c "from core.orchestrator import Orchestrator; print('OK')"` succeeds from worktree root.

---

### Task 3: Extend Cockpit `deploy/windows/init.py`

**Files:** `~/git/cockpit/deploy/windows/init.py`

Add prompts for:
- Instance name (default: "LMF")
- Trust profile (personal/professional/mixed, default: "personal")
- Onboarding mode (guided/quick/skip, default: "guided")

Write `deploy.yaml` alongside `config.yaml` in the operator directory.

**Verification:** `python3 ~/git/cockpit/deploy/windows/init.py --help` (or dry-run) shows new prompts.

---

### Task 4: Verify and Review

- Run `python3 -c "from core.orchestrator import *"` from worktree root
- Run `python3 core/build_prompt.py` against a test vault path
- Run `python3 -c "from core.orchestrator import Orchestrator; o = Orchestrator('/tmp/test-vault')"` with and without LOCAL_MIND_FOUNDATION.md
- Verify `/reset` clears init state in init mode
- Verify write gate enforcement: only Inbox.md allowed in init mode
- Verify handoff flow: detection → confirmation → write → reload → introduce

---

## Task Plan

1. → Task 1 (init.md template)
2. → Task 2 (orchestrator changes)
3. → Task 3 (init.py deploy.yaml)
4. → Task 4 (review)
5. → PR
