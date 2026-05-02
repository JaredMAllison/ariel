# lmf-ollama-obsidian

lmf-ollama-obsidian is the LLM orchestrator stack layer of the Local Mind Foundation architecture — clone this to deploy a local AI assistant against your own vault.

## Quick start

1. Install dependencies: `pip install requests pyyaml`
2. Run first-time setup: `python init.py`
3. Start the orchestrator: `python core/orchestrator.py`

## Structure

- `core/` — orchestrator, prompt builder, tool manifest
- `features/ui/` — browser chat interface
- `features/testing/` — test harness (see Plan 2)
- `operator/` — your deployment config (gitignored)

## Reference instance

The Marlin surfacing engine (marlin.py, webhook.py, tasks.py) lives in [JaredMAllison/marlin](https://github.com/JaredMAllison/marlin). lmf-ollama-obsidian is the LLM conversation layer only.

## LMF

Part of the [Local Mind Foundation](https://github.com/local-mind-foundation) architecture.
