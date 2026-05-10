#!/usr/bin/env python3
"""Analyze test battery results — merge results YAML with prompts YAML for readable output."""

import argparse
import sys
from pathlib import Path

import yaml


PASS_SYM = "PASS"
FAIL_SYM = "FAIL"

TYPE_LABELS = {
    "tool_exercise": "Tool Exercise",
    "grounding": "Grounding",
    "hallucination_boundary": "Hallucination Boundary",
    "tool_enforcement": "Tool Enforcement",
    "write_exercise": "Write Exercise",
}


def load(path: Path) -> list | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def find_results(results_dir: Path) -> list[Path]:
    return sorted(results_dir.rglob("*.yaml"), reverse=True)


def build_prompt_map(prompts: list[dict]) -> dict:
    return {p["id"]: p for p in prompts}


def truncate(text: str, width: int = 500) -> str:
    """Truncate long responses, keeping key structure."""
    text = text.replace("\\n", "\n")
    if len(text) <= width:
        return text
    half = width // 2
    return text[:half] + "\n  ... [truncated] ...\n" + text[-half:]


def analyze_one(prompt: dict, result: dict) -> list[str]:
    lines = []
    pid = result["id"]
    ptype = result["type"]
    passed = result.get("passed", False)
    badge = f"{PASS_SYM}" if passed else f"{FAIL_SYM}"

    lines.append(f"  [{pid}] {badge}  {TYPE_LABELS.get(ptype, ptype)}")
    lines.append(f"  {'─' * 60}")

    if prompt:
        lines.append(f"  Query: {prompt.get('query', '?')}")

    lines.append(f"  Response: {result.get('response_ms', '?')}ms")

    tools = result.get("tool_calls_made", [])
    if tools:
        lines.append(f"  Tools called: {', '.join(tools)}")
    else:
        lines.append(f"  Tools called: (none)")

    if ptype == "tool_exercise":
        exp = result.get("expected_tool")
        if isinstance(exp, list):
            lines.append(f"  Expected (any of): {', '.join(exp)}")
        else:
            lines.append(f"  Expected tool: {exp}")

    if ptype == "grounding":
        term = result.get("grounding_term")
        if term:
            found = term.lower() in result.get("response", "").lower()
            lines.append(f"  Grounding term: \"{term}\" — {'found' if found else 'NOT found'}")

    if ptype == "hallucination_boundary":
        uncert = any(
            p in result.get("response", "").lower()
            for p in [
                "i don't", "i couldn't find", "not found", "no mention",
                "unable to find", "there is no", "doesn't appear",
                "i cannot find", "did not contain",
            ]
        )
        lines.append(f"  Expressed uncertainty: {'yes' if uncert else 'NO — likely hallucination'}")

    if ptype == "tool_enforcement":
        lines.append(f"  Result: passed" if passed else "  Result: FAILED — prohibited tool was called")

    if ptype == "write_exercise":
        lines.append(f"  Gate held: {result.get('gate_held', '?')}")
        lines.append(f"  Write confirmed: {result.get('write_confirmed', '?')}")
        lines.append(f"  Content matched: {result.get('content_match', '?')}")

    response_text = result.get("response", "")
    if response_text:
        # Collapse single-line JSON to save space
        first = response_text.strip()
        if first.startswith("{") or first.startswith("["):
            lines.append(f"  Raw response: {truncate(first, 300)}")
        else:
            preview = truncate(first, 600)
            lines.append(f"  Raw response (first {min(len(first),600)} chars):")
            for para in preview.split("\n"):
                lines.append(f"    {para}")
    lines.append("")
    return lines


def format_summary(scores: dict) -> str:
    lines = []
    lines.append(f"\n  {'=' * 60}")
    lines.append(f"  SUMMARY")
    lines.append(f"  {'=' * 60}")
    lines.append(f"  Tool accuracy:      {scores.get('tool_accuracy', '?'):>6}")
    lines.append(f"  Grounding rate:     {scores.get('grounding_rate', '?'):>6}")
    lines.append(f"  Hallucination rate: {scores.get('hallucination_rate', '?'):>6}")
    lines.append(f"  Tool enforcement:   {scores.get('tool_enforcement_pass', '?')}")
    lines.append(f"  Avg response:       {scores.get('avg_response_ms', '?')}ms")
    if scores.get("write_gate_rate") is not None:
        lines.append(f"  Write gate rate:    {scores['write_gate_rate']:.0%}")
        lines.append(f"  Write confirm rate: {scores['write_confirm_rate']:.0%}")
        lines.append(f"  Content match rate: {scores['content_match_rate']:.0%}")
    lines.append(f"  Model:     {scores.get('model', '?')}")
    lines.append(f"  Vault:     {scores.get('vault_type', '?')}")
    lines.append(f"  Host:      {scores.get('inference_host', '?')}")
    lines.append(f"  Date:      {scores.get('date', '?')}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze test battery results")
    parser.add_argument("result", nargs="?", help="Result YAML file (default: latest in features/testing/results/)")
    parser.add_argument("--prompts", default=None, help="Prompts battery YAML (default: auto-detect)")
    parser.add_argument("--results-dir", default=None, help="Results directory (default: features/testing/results/)")
    parser.add_argument("--output", "-o", default=None, help="Output file path")
    parser.add_argument("--auto", action="store_true", help="Auto-name output file next to result (result.yaml → result.txt)")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent.parent
    results_dir = Path(args.results_dir) if args.results_dir else repo_root / "features" / "testing" / "results"

    out: list[str] = []

    if args.result:
        result_path = Path(args.result)
        if not result_path.exists():
            sys.exit(f"Result file not found: {result_path}")
    else:
        all_results = []
        for vd in results_dir.iterdir():
            if vd.is_dir():
                all_results.extend(find_results(vd))
        if not all_results:
            sys.exit("No result files found.")
        result_path = all_results[0]
        out.append(f"  Using latest result: {result_path}\n")

    result_data = load(result_path)
    if not isinstance(result_data, dict):
        sys.exit("Result file must be a top-level mapping.")

    scores = {k: result_data[k] for k in [
        "tool_accuracy", "grounding_rate", "hallucination_rate",
        "tool_enforcement_pass", "avg_response_ms",
        "write_gate_rate", "write_confirm_rate", "content_match_rate",
        "model", "vault_type", "inference_host", "date",
    ] if k in result_data}

    prompt_results = result_data.get("prompt_results", [])
    if not prompt_results:
        sys.exit("No prompt_results found in result file.")

    # Find matching prompts battery
    prompts_path = None
    if args.prompts:
        prompts_path = Path(args.prompts)
    else:
        vault_type = result_data.get("vault_type", "operator")
        candidates = [
            repo_root / "features" / "testing" / "battery" / f"{vault_type}_prompts.yaml",
            repo_root / "features" / "testing" / "battery" / "prompts.yaml",
            repo_root / "features" / "testing" / "battery" / "init_prompts.yaml",
        ]
        for c in candidates:
            if c.exists():
                prompts_path = c
                break

    prompt_map = {}
    if prompts_path:
        prompts = load(prompts_path)
        if isinstance(prompts, list):
            prompt_map = build_prompt_map(prompts)
        out.append(f"  Using prompts battery: {prompts_path}\n")
    else:
        out.append("  (no prompts file found — analysis limited to result data)\n")

    passed = 0
    failed = 0
    for pr in prompt_results:
        pid = pr["id"]
        prompt = prompt_map.get(pid, {})
        out.extend(analyze_one(prompt, pr))
        if pr.get("passed", False):
            passed += 1
        else:
            failed += 1

    out.append(f"  {'=' * 60}")
    out.append(f"  TOTAL: {passed} passed, {failed} failed ({passed + failed} prompts)")
    out.append("")

    out.append(format_summary(scores))

    text = "\n".join(out)

    if args.auto:
        stem = result_path.stem
        out_path = result_path.with_name(f"{stem}.txt")
    elif args.output:
        out_path = Path(args.output)
    else:
        print(text)
        return

    out_path.write_text(text, encoding="utf-8")
    print(f"  Written: {out_path}")


if __name__ == "__main__":
    main()
