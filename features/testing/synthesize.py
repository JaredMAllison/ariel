#!/usr/bin/env python3
"""Synthesize multiple test runs into an aggregated analysis.

Usage:
  python3 features/testing/synthesize.py                          # auto: latest model run
  python3 features/testing/synthesize.py --model llama-3.1-8b-instant
  python3 features/testing/synthesize.py --dir results/operator/  # all files in dir
"""

import argparse
import re
import sys
from pathlib import Path
from statistics import mean, stdev, StatisticsError

import yaml


REPO_ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = REPO_ROOT / "features" / "testing" / "results"


def load_results(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def find_result_files(model: str | None = None, vault: str = "operator") -> list[Path]:
    """Find all result YAML files, optionally filtered by model."""
    results_dir = RESULTS_DIR / vault
    if not results_dir.exists():
        sys.exit(f"Results directory not found: {results_dir}")

    all_files = sorted(results_dir.glob("*.yaml"))
    if model:
        all_files = [f for f in all_files if model.replace(":", "-") in f.stem]
    return all_files


def aggregate(files: list[Path]) -> dict:
    """Aggregate metrics across multiple result files."""
    records = []
    prompt_map: dict[str, list[dict]] = {}

    for f in files:
        data = load_results(f)
        records.append({
            "file": f,
            "model": data.get("model", "?"),
            "vault_type": data.get("vault_type", "?"),
            "date": data.get("date", "?"),
            "tool_accuracy": data.get("tool_accuracy", 0),
            "grounding_rate": data.get("grounding_rate", 0),
            "hallucination_rate": data.get("hallucination_rate", 0),
            "tool_enforcement_pass": data.get("tool_enforcement_pass", True),
            "avg_response_ms": data.get("avg_response_ms", 0),
            "write_gate_rate": data.get("write_gate_rate"),
            "write_confirm_rate": data.get("write_confirm_rate"),
            "content_match_rate": data.get("content_match_rate"),
        })

        for pr in data.get("prompt_results", []):
            pid = pr["id"]
            if pid not in prompt_map:
                prompt_map[pid] = []
            prompt_map[pid].append({
                "run": f.stem,
                "passed": pr.get("passed", False),
                "type": pr.get("type", "?"),
                "tool_calls_made": pr.get("tool_calls_made", []),
                "response_ms": pr.get("response_ms", 0),
            })

    n = len(records)
    if n == 0:
        return {"error": "No result files found", "n": 0}

    def _vals(key):
        return [r[key] for r in records]

    def _stats(key):
        vals = _vals(key)
        if not vals:
            return None
        return {
            "mean": round(mean(vals), 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
            "spread": round(max(vals) - min(vals), 3),
        }

    # Compute prompt-level pass rates
    prompt_summary = {}
    for pid, entries in sorted(prompt_map.items()):
        passed = sum(1 for e in entries if e["passed"])
        ptype = entries[0]["type"]
        times = [e["response_ms"] for e in entries]
        prompt_summary[pid] = {
            "type": ptype,
            "pass_rate": round(passed / len(entries), 3),
            "pass_count": passed,
            "total": len(entries),
            "avg_ms": int(mean(times)),
            "fastest_ms": min(times),
            "slowest_ms": max(times),
            "tools_used": list(set(
                t for e in entries for t in e["tool_calls_made"]
            )),
        }

    enforcement_pass_rate = sum(
        1 for r in records if r["tool_enforcement_pass"]
    ) / n if n else 0

    return {
        "n": n,
        "model": records[0]["model"],
        "vault_type": records[0]["vault_type"],
        "files": [str(f) for f in files],
        "tool_accuracy": _stats("tool_accuracy"),
        "grounding_rate": _stats("grounding_rate"),
        "hallucination_rate": _stats("hallucination_rate"),
        "tool_enforcement_pass_rate": round(enforcement_pass_rate, 3),
        "avg_response_ms": _stats("avg_response_ms"),
        "write_gate_rate": _stats("write_gate_rate") if any(r["write_gate_rate"] is not None for r in records) else None,
        "write_confirm_rate": _stats("write_confirm_rate") if any(r["write_confirm_rate"] is not None for r in records) else None,
        "prompts": prompt_summary,
    }


def format_report(agg: dict) -> str:
    lines = []
    if "error" in agg:
        lines.append(f"ERROR: {agg['error']}")
        return "\n".join(lines)

    n = agg["n"]
    lines.append(f"Synthesis Report — {agg['model']} on {agg['vault_type']} vault")
    lines.append(f"  {n} runs{'  ' + ('─' * 40)}")
    lines.append(f"")
    lines.append(f"  Metric               Mean    Min     Max     Spread")
    lines.append(f"  {'─' * 60}")

    def _fmt(label: str, key: str, pct: bool = True, ms: bool = False):
        s = agg.get(key)
        if not s:
            return
        if pct:
            lines.append(f"  {label:<20} {s['mean']:>6.1%}  {s['min']:>6.1%}  {s['max']:>6.1%}  {s['spread']:>6.1%}")
        elif ms:
            lines.append(f"  {label:<20} {s['mean']:>6.0f}  {s['min']:>6.0f}  {s['max']:>6.0f}  {s['spread']:>6.0f}")

    _fmt("Tool accuracy", "tool_accuracy")
    _fmt("Grounding rate", "grounding_rate")
    _fmt("Hallucination rate", "hallucination_rate")
    _fmt("Avg response ms", "avg_response_ms", pct=False, ms=True)

    if agg.get("write_gate_rate"):
        _fmt("Write gate rate", "write_gate_rate")
        _fmt("Write confirm rate", "write_confirm_rate")

    lines.append(f"  Tool enforcement:    {agg['tool_enforcement_pass_rate']:.0%} pass rate ({agg['n']} runs)")
    lines.append(f"")

    # Per-prompt breakdown
    lines.append(f"  Per-Prompt Pass Rates")
    lines.append(f"  {'─' * 60}")
    lines.append(f"  {'ID':<10} {'Type':<22} {'Pass':>5} {'Rate':>7} {'Avg':>7} {'Tools':<30}")
    lines.append(f"  {'─' * 60}")
    for pid, p in agg["prompts"].items():
        tools = ", ".join(p["tools_used"][:3])
        lines.append(
            f"  {pid:<10} {p['type']:<22} "
            f"{p['pass_count']}/{p['total']:<3} "
            f"{p['pass_rate']:>6.0%} "
            f"{p['avg_ms']:>6}ms "
            f"{tools:<30}"
        )

    lines.append(f"")
    lines.append(f"  Files: {len(agg['files'])} results in {agg['files'][0]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Synthesize multiple test runs")
    parser.add_argument("--model", default=None, help="Filter by model name")
    parser.add_argument("--vault", default="operator", help="Vault type subdirectory (operator|synthetic)")
    parser.add_argument("--output", "-o", default=None, help="Output file")
    parser.add_argument("--auto", action="store_true", help="Auto-name output next to results dir")
    args = parser.parse_args()

    files = find_result_files(model=args.model, vault=args.vault)
    if len(files) < 2:
        print(f"Need at least 2 result files; found {len(files)} in results/{args.vault}/")
        if files:
            print(f"  Run more tests first: python3 features/testing/harness.py ...")
        return

    agg = aggregate(files)
    report = format_report(agg)

    if args.output:
        out_path = Path(args.output)
    elif args.auto:
        model_slug = agg["model"].replace(":", "-")
        out_path = RESULTS_DIR / args.vault / f"synthesis-{model_slug}-n{agg['n']}.txt"
    else:
        print(report)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n  Written: {out_path}")


if __name__ == "__main__":
    main()
