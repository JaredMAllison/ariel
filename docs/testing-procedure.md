# Testing Procedure — lmf-ollama-obsidian

Reference for manual and automated testing. Use this when you want to verify behaviour without a Claude session.

---

## Quick checks (no Ollama needed)

Run the full unit test suite against the worktree or main branch:

```bash
cd /home/jared/lmf-ollama-obsidian          # or .worktrees/write-tools-gate
pytest tests/ -v
```

**What this covers:**
- `test_kb_core_create_file.py` — `create_file()` in kb_core (no vault needed, uses tmp_path)
- `test_orchestrator_write_gate.py` — all gate logic, mocked Ollama (no Ollama needed)
- `test_config_loader.py` — config YAML loading
- `test_init.py` — bootstrap script
- `test_metrics.py` — scoring functions
- `test_seeder.py` — synthetic vault seeder

All tests run in ~0.3 seconds. No network, no Ollama, no vault required.

---

## Synthetic vault battery (Ollama required)

Runs the full prompt battery against a deterministic synthetic vault. Safe — writes go to a temp copy.

```bash
cd /home/jared/lmf-ollama-obsidian

# CPU on Gretchen (qwen2.5:1.5b or 3b)
python3 features/testing/harness.py --vault features/testing/synthetic/vault --model qwen2.5:1.5b

# GPU on Bazza
python3 features/testing/harness.py \
  --vault features/testing/synthetic/vault \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

**What this covers:** T001–T014 (tool exercise, grounding, hallucination, enforcement) + W001–W003 (write gate: confirm, create, reject).

Write exercises (W001–W003) verify actual disk state — the harness checks the file was written (or not written) after a yes/no response.

**Results land in:** `features/testing/results/synthetic/`

---

## Live vault battery (Ollama required, read-only safe)

Runs against your real Marlin vault. Always uses `--snapshot` to avoid mutating the live vault.

```bash
python3 features/testing/harness.py \
  --vault ~/Documents/Obsidian/Marlin \
  --snapshot \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

**Results land in:** `features/testing/results/operator/`

---

## Manual gate smoke test (Ollama required)

Manually verify the confirmation gate end-to-end using Python REPL:

```bash
cd /home/jared/lmf-ollama-obsidian
python3 -c "
import sys; sys.path.insert(0, 'core')
from orchestrator import Orchestrator, _init_config
_init_config()
orch = Orchestrator('$HOME/Documents/Obsidian/Marlin', test_mode=True)

# Turn 1: should show proposal
reply1 = orch.chat('Add this to my inbox: test entry')
print('--- Turn 1 ---')
print(reply1)
print()

# Turn 2: confirm
reply2 = orch.chat('yes')
print('--- Turn 2 ---')
print(reply2)
"
```

Expected Turn 1: `Ariel wants to append to \`Inbox.md\`... Confirm? (yes/no)`
Expected Turn 2: `Done.\n\n✓ Written to \`Inbox.md\`` (test_mode=True makes the summary visible)

---

## What to look for in test output

| Metric | Target | Meaning |
|---|---|---|
| `tool_accuracy` | ≥ 75% | Model calls the right tool for the job |
| `grounding_rate` | ≥ 80% | Answers reference actual vault content |
| `hallucination_rate` | 0% | Model admits uncertainty instead of fabricating |
| `tool_enforcement` | PASS | No blocked tools were called |
| `write_gate_rate` | 100% | Gate always fires before write |
| `write_confirm_rate` | 100% | Confirmed writes actually execute |
| `content_match_rate` | 100% | Written content matches proposal |

---

## Checking a specific write gate scenario manually

```python
orch.pending_write        # None if no gate pending
orch.verbose_writes       # True = see ✓ Written to after confirm
orch.allow_external_writes  # False = vault-relative paths only
orch.test_mode            # True = implies verbose
```

To force a gate state for testing:
```python
orch.pending_write = {
    "name": "append_to_file",
    "args": {"file_path": "Inbox.md", "content": "- manual test"},
    "proposal": "...",
}
reply = orch.chat("yes")
print(reply)
```
