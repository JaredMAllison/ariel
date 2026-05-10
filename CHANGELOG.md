# Changelog

## 2026-05-01 — Testing harness (features/testing/)

- `features/testing/synthetic/seeder.py` — deterministic vault seeder from YAML spec
- `features/testing/synthetic/seed_spec.yaml` — committed test data (2 projects, 4 tasks, 2 insights, 2 daily notes)
- `features/testing/battery/prompts.yaml` — 14-prompt battery across 4 test types (tool_exercise, grounding, hallucination_boundary, tool_enforcement)
- `features/testing/metrics.py` — scoring module; `score_results()`, `write_results()`, `_prompt_passed()`
- `features/testing/harness.py` — runs battery against Orchestrator directly; `--vault`, `--model`, `--models`, `--gpu`, `--host` flags
- `core/orchestrator.py` — added `last_tool_calls: list[str]` tracking (reset per `chat()`, appended in `_dispatch_tool()`)
- Result files: `{date}-{model}-{vault_type}-r{N}.yaml` with run counter, `inference_host`, `gpu_accelerated`
- First baseline run: `features/testing/results/synthetic/2026-05-01-qwen2.5-1.5b-synthetic-r1.yaml` (CPU, Gretchen)
- ADR: `ariel-von-marlin-adr-005-testing-harness.md`

## 2026-05-01 — Initial release

- Repo structure: core/, features/, operator/ (gitignored)
- Orchestrator + build_prompt + tools config moved from marlin-ariel-orchestrator
- Hardcoded constants replaced by operator/config.yaml
- init.py bootstrap script
