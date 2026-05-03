# Testing Procedure

## 1. Unit tests (no Ollama, no vault, ~0.3s)

Covers all gate logic, config loading, metrics scoring, kb_core, and seeder.

```bash
cd /home/jared/lmf-ollama-obsidian
pytest tests/ -v
```

Expected: 52 passed, 0 failed.


## 2. Synthetic battery — CPU (Gretchen)

Runs the full 17-prompt battery against the synthetic vault. Generates the vault on first run.

```bash
cd /home/jared/lmf-ollama-obsidian
python3 features/testing/harness.py --model qwen2.5:1.5b
```

For 3b:
```bash
python3 features/testing/harness.py --model qwen2.5:3b
```

Results land in `features/testing/results/synthetic/`.


## 3. Synthetic battery — GPU (Bazza)

```bash
cd /home/jared/lmf-ollama-obsidian
python3 features/testing/harness.py \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

Results land in `features/testing/results/synthetic/`.


## 4. Live vault battery (read-only, snapshot mode)

Runs against your real Marlin vault. `--snapshot` copies it to a temp dir first — the live vault is never touched.

```bash
cd /home/jared/lmf-ollama-obsidian
python3 features/testing/harness.py \
  --vault ~/Documents/Obsidian/Marlin \
  --snapshot \
  --model qwen2.5:7b \
  --gpu \
  --host bazza \
  --ollama-url http://10.0.0.78:11434
```

Results land in `features/testing/results/operator/`.


## 5. Manual gate smoke test (REPL)

Verify the confirmation gate end-to-end. No battery needed.

```bash
cd /home/jared/lmf-ollama-obsidian
python3 - <<'EOF'
import sys
sys.path.insert(0, 'core')
from orchestrator import Orchestrator, _init_config
_init_config()
orch = Orchestrator('/home/jared/Documents/Obsidian/Marlin', test_mode=True)

reply1 = orch.chat("Add this to my inbox: test entry")
print("=== Turn 1 (should show proposal) ===")
print(reply1)

reply2 = orch.chat("yes")
print("=== Turn 2 (should confirm write) ===")
print(reply2)
EOF
```

Expected Turn 1: `Ariel wants to append to \`Inbox.md\`... Confirm? (yes/no)`
Expected Turn 2: `Done.\n\n✓ Written to \`Inbox.md\``

To test rejection, replace `orch.chat("yes")` with `orch.chat("no")` — Turn 2 should return a cancellation message and the file should be unchanged.


## 6. Checking results

Result files are YAML. Key fields:

```
tool_accuracy        — model calls the right tool (target: ≥75%)
grounding_rate       — answers reference real vault content (target: ≥80%)
hallucination_rate   — model fabricates instead of admitting uncertainty (target: 0%)
tool_enforcement     — PASS/FAIL (target: PASS)
write_gate_rate      — gate fired before every write (target: 100%)
write_confirm_rate   — confirmed writes actually executed (target: 100%)
content_match_rate   — written content matches proposal (target: 100%)
avg_response_ms      — average turn latency
```

Read a result file:
```bash
cat features/testing/results/synthetic/<filename>.yaml
```

List all runs:
```bash
ls -lt features/testing/results/synthetic/
```


## 7. Operator config

The harness needs `operator/config.yaml`. If it doesn't exist:

```bash
cd /home/jared/lmf-ollama-obsidian
python3 init.py
```

Or write it manually:
```yaml
vault_path: /home/jared/Documents/Obsidian/Marlin
model: qwen2.5:7b
port: 8742
num_ctx: 8192
ollama_url: http://10.0.0.78:11434/api/chat
timeout_s: 300
verbose_writes: false
allow_external_writes: false
```
