#!/usr/bin/env python3
"""lmf-ollama-obsidian testing harness — runs prompt battery against Orchestrator directly."""

import sys
import time
import shutil
import tempfile
import yaml
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "core"))
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator, load_config, _init_config
import orchestrator as orch_module
from metrics import score_results, write_results, _prompt_passed


def load_prompts(path: Path, vault_type: str) -> list[dict]:
    all_prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [p for p in all_prompts if p.get("vault", "any") in ("any", vault_type)]


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
                "id":              prompt["id"],
                "type":            prompt["type"],
                "query":           prompt["query"],
                "response":        reply,
                "response_ms":     elapsed_ms,
                "tool_calls_made": list(orch.last_tool_calls),
                "expected_tool":   prompt.get("expected_tool"),
                "grounding_term":  prompt.get("grounding_term"),
            }
        results.append(result)
        status = "." if _prompt_passed(result) else "F"
        print(f"  [{prompt['id']}] {status} {result['response_ms']}ms", flush=True)
    return results


def _run_write_exercise(orch: Orchestrator, prompt: dict,
                         vault_path: Path, t0: float) -> dict:
    expected_file   = prompt.get("expected_file", "")
    expect_fragment = prompt.get("expected_content_fragment", "")
    expect_no_write = prompt.get("expect_no_write", False)
    confirm_with    = prompt.get("confirm_with", "yes")

    target      = vault_path / expected_file if expected_file else None
    file_before = target.read_text(encoding="utf-8") if (target and target.exists()) else None

    # Turn 1 — should trigger proposal, not write
    reply1    = orch.chat(prompt["query"])
    gate_held = "Confirm? (yes/no)" in reply1 and "Ariel wants to" in reply1

    # Turn 2 — confirm or reject
    reply2     = orch.chat(confirm_with)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

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
            content_match = False

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
        "expect_no_write": expect_no_write,
    }


def main():
    import requests.exceptions

    parser = argparse.ArgumentParser(description="lmf-ollama-obsidian testing harness")
    parser.add_argument("--vault", default="synthetic",
                        help="'synthetic' or path to real vault")
    parser.add_argument("--model", default=None,
                        help="Override model from operator/config.yaml")
    parser.add_argument("--models", nargs="+", default=None,
                        help="Compare across multiple models")
    parser.add_argument("--gpu", action="store_true", default=False,
                        help="Flag that inference is GPU-accelerated (default: False)")
    parser.add_argument("--host", default=None,
                        help="Override inference host name in results (default: hostname)")
    parser.add_argument("--ollama-url", default=None,
                        help="Override Ollama base URL (e.g. http://10.0.0.78:11434)")
    parser.add_argument("--snapshot", action="store_true", default=False,
                        help="Copy vault to a temp dir before running; delete after. Safe for live vaults.")
    parser.add_argument("--battery", default="prompts",
                        help="Prompt battery file stem in battery/ dir (default: prompts)")
    parser.add_argument("--orchestrator", default="base", choices=["base", "ariel"],
                        help="Orchestrator class to test: 'base' (default) or 'ariel'")
    args = parser.parse_args()

    config_path = REPO_ROOT / "operator" / "config.yaml"
    prompts_path = Path(__file__).parent / "battery" / f"{args.battery}.yaml"

    if args.vault == "synthetic":
        vault_path = Path(__file__).parent / "synthetic" / "vault"
        vault_type = "synthetic"
        if not vault_path.exists():
            print("Synthetic vault not found — generating...")
            from synthetic.seeder import seed_vault
            seed_vault(Path(__file__).parent / "synthetic" / "seed_spec.yaml", vault_path)
    else:
        vault_path = Path(args.vault).expanduser()
        vault_type = "operator"
        if not vault_path.exists():
            sys.exit(f"[harness] Vault path does not exist: {vault_path}")

    try:
        _init_config(config_path)
    except SystemExit:
        sys.exit(f"[harness] Config not found at {config_path} — run python3 init.py first.")

    if args.ollama_url:
        base = args.ollama_url.rstrip("/")
        orch_module.OLLAMA_URL     = f"{base}/api/chat"
        orch_module.OLLAMA_PS_URL  = f"{base}/api/ps"

    if not prompts_path.exists():
        sys.exit(f"[harness] Battery not found: {prompts_path}")

    prompts = load_prompts(prompts_path, vault_type)

    # Resolve model name from config's priority-0 backend
    if args.model:
        model_name = args.model
    elif args.models:
        model_name = args.models[0]
    else:
        model_name = None
        raw_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        for b in raw_cfg.get("backends", []):
            if b.get("priority", 99) == 0:
                model_name = b.get("model", b["name"])
                break
        if not model_name:
            model_name = orch_module.OLLAMA_MODEL
    models = args.models or [model_name]

    tmp_dir = None
    try:
        if args.snapshot and vault_type == "operator":
            tmp_dir = Path(tempfile.mkdtemp(prefix="ariel-test-vault-"))
            print(f"  Snapshotting vault → {tmp_dir} ...", flush=True)
            shutil.copytree(
                vault_path, tmp_dir / "vault",
                ignore=shutil.ignore_patterns('.knowledge-loom-index'),
            )
            vault_path = tmp_dir / "vault"
            print(f"  Snapshot ready. Original vault untouched.", flush=True)

        tools_config = REPO_ROOT / "core" / "tools.config.yaml"
        for model in models:
            orch_module.OLLAMA_MODEL = model
            if args.orchestrator == "ariel":
                from ariel.persona import ArielOrchestrator
                orch = ArielOrchestrator(str(vault_path), test_mode=True,
                                         tools_config_path=tools_config if tools_config.exists() else None)
            else:
                orch = Orchestrator(str(vault_path), test_mode=True,
                                    tools_config_path=tools_config if tools_config.exists() else None)
            print(f"\nRunning battery — model={model} vault={vault_type} prompts={len(prompts)}")

            try:
                results = run_battery(orch, prompts, vault_path)
            except requests.exceptions.ConnectionError:
                sys.exit(f"[harness] Ollama not reachable — is it running?")

            scores = score_results(results)

            out_dir = Path(__file__).parent / "results" / vault_type
            out_path = write_results(scores, results, model, vault_type, out_dir,
                                     inference_host=args.host, gpu_accelerated=args.gpu)

            print(f"\n  tool_accuracy:       {scores['tool_accuracy']:.0%}")
            print(f"  grounding_rate:      {scores['grounding_rate']:.0%}")
            print(f"  hallucination_rate:  {scores['hallucination_rate']:.0%}")
            print(f"  tool_enforcement:    {'PASS' if scores['tool_enforcement_pass'] else 'FAIL'}")
            print(f"  avg_response_ms:     {scores['avg_response_ms']}")
            if scores.get("write_gate_rate") is not None:
                print(f"  write_gate_rate:     {scores['write_gate_rate']:.0%}")
                print(f"  write_confirm_rate:  {scores['write_confirm_rate']:.0%}")
                print(f"  content_match_rate:  {scores['content_match_rate']:.0%}")
            print(f"\n  Results: {out_path}")
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir)
            print(f"  Snapshot deleted.", flush=True)


if __name__ == "__main__":
    main()
