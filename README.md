# LMF — Local Mind Foundation

A locally-sovereign AI assistant orchestrator for personal knowledge vaults. Designed for neurodivergent users who need cognitive prosthetics — not productivity tools.

LMF runs entirely on your hardware. No cloud dependency. No data leaves your machine. The assistant reads your vault, surfaces relevant context, and helps you think — on your terms.

---

## Why This Exists

Most AI tools are built for neurotypical workflows and require trusting a vendor with your data. LMF takes a different position:

- **Local only** — everything runs on your machine via Ollama. No data sent to a third party.
- **Vault-native** — reads your Obsidian/Markdown vault directly. No import step, no sync layer.
- **Conversational onboarding** — the assistant learns about you through conversation, not forms.
- **Operator-controlled** — writes require explicit confirmation. The AI cannot modify your vault without approval.

Built for people who need the system to find them, not the other way around.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    LMF Orchestrator                  │
│  core/orchestrator.py — prompt builder, tool dispatch │
│  core/backends.py — multi-model inference (Ollama)    │
│  core/build_prompt.py — vault-aware system prompt     │
│  core/tools.config.yaml — tool definitions             │
├─────────────────────────────────────────────────────┤
│                    Features                           │
│  features/ui/ — browser chat interface                │
│  features/testing/ — test harness + analysis          │
├─────────────────────────────────────────────────────┤
│                    Deployment                         │
│  init.py — first-time setup wizard                    │
│  tools/provision-usb.py — portable USB deployment     │
│  operator/ — your local config (gitignored)           │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install requests pyyaml
python init.py              # first-time setup
python core/orchestrator.py # start the assistant
```

## Key Features

- **Multi-backend inference** — Ollama, any OpenAI-compatible API. Hot-swappable at runtime.
- **Vault-aware prompting** — reads your actual vault content (tasks, projects, memory files) into system context.
- **Confirmation-gated writes** — `append_to_file` and `replace_lines` require operator approval before executing.
- **PII-safe testing harness** — synthetic vault seeder prevents real data exposure during test runs.
- **Portable deployment** — USB-friendly bootstrap scripts for air-gapped or offline use.
- **Test battery** — 14 prompts across 4 test types: tool exercise, grounding, hallucination boundary, tool enforcement.

## Test Results (qwen2.5:3b, CPU)

| Metric | Score |
|--------|-------|
| Tool Accuracy | 78% |
| Grounding Rate | 50% |
| Hallucination Rate | 50% |
| Tool Enforcement | PASS |

## Reference Instance

The reference deployment is [Marlin](https://github.com/JaredMAllison/marlin) — a production task surfacing engine that surfaces one task at a time via phone notification. LMF is the LLM conversation layer used by Marlin and other instances in the LMF architecture.

## Related Repos

- [cockpit](https://github.com/JaredMAllison/cockpit) — unified HUD for the LMF stack
- [marlin](https://github.com/JaredMAllison/marlin) — task surfacing engine
- [the-time-factory](https://github.com/JaredMAllison/the-time-factory) — ADHD-friendly visual calendar
- [prosper0](https://github.com/JaredMAllison/prosper0) — work-specific exobrain instance

---

*Part of the Local Mind Foundation architecture. Local-first, ND-designed, operator-sovereign.*
