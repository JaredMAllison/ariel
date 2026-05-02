#!/usr/bin/env python3
"""lmf-ollama-obsidian testing harness — runs prompt battery against Orchestrator directly."""

import sys
import time
import yaml
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "core"))
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator, load_config, _init_config
import orchestrator as orch_module
from metrics import score_results, write_results, _prompt_passed


def load_prompts(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_battery(orch: Orchestrator, prompts: list[dict]) -> list[dict]:
    results = []
    for prompt in prompts:
        orch.reset()
        t0 = time.monotonic()
        reply = orch.chat(prompt["query"])
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        results.append({
            "id": prompt["id"],
            "type": prompt["type"],
            "query": prompt["query"],
            "response": reply,
            "response_ms": elapsed_ms,
            "tool_calls_made": list(orch.last_tool_calls),
            "expected_tool": prompt.get("expected_tool"),
            "grounding_term": prompt.get("grounding_term"),
        })
        status = "." if _prompt_passed(results[-1]) else "F"
        print(f"  [{prompt['id']}] {status} {elapsed_ms}ms", flush=True)
    return results


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
    args = parser.parse_args()

    config_path = REPO_ROOT / "operator" / "config.yaml"
    prompts_path = Path(__file__).parent / "battery" / "prompts.yaml"

    if args.vault == "synthetic":
        vault_path = Path(__file__).parent / "synthetic" / "vault"
        vault_type = "synthetic"
        if not vault_path.exists():
            print("Synthetic vault not found — generating...")
            from synthetic.seeder import seed_vault
            seed_vault(Path(__file__).parent / "synthetic" / "seed_spec.yaml", vault_path)
    else:
        vault_path = Path(args.vault)
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

    prompts = load_prompts(prompts_path)
    models = args.models or [args.model or orch_module.OLLAMA_MODEL]

    for model in models:
        orch_module.OLLAMA_MODEL = model
        orch = Orchestrator(str(vault_path))
        print(f"\nRunning battery — model={model} vault={vault_type} prompts={len(prompts)}")

        try:
            results = run_battery(orch, prompts)
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
        print(f"\n  Results: {out_path}")


if __name__ == "__main__":
    main()
