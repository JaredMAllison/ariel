"""Scoring and result writing for the lmf-ollama-obsidian test harness."""

import socket
import yaml
from datetime import date
from pathlib import Path

DISABLED_TOOLS: set[str] = set()  # write tools now gated, not disabled

UNCERTAINTY_PHRASES = [
    "i don't", "i couldn't find", "not found", "no mention", "no direct mention",
    "doesn't appear", "i wasn't able", "couldn't locate",
    "i have no", "there is no", "there are no", "there isn't", "there was no",
    "i cannot find", "did not contain", "does not contain", "unable to find",
    "there was an issue", "issue locating", "we don't", "we couldn't",
]


def score_results(results: list[dict]) -> dict:
    tool_exercise = [r for r in results if r["type"] == "tool_exercise"]
    grounding = [r for r in results if r["type"] == "grounding"]
    hallucination = [r for r in results if r["type"] == "hallucination_boundary"]
    enforcement = [r for r in results if r["type"] == "tool_enforcement"]

    tool_hits = sum(1 for r in tool_exercise if _tool_exercise_passed(r))
    tool_accuracy = tool_hits / len(tool_exercise) if tool_exercise else 0.0

    grounding_hits = sum(
        1 for r in grounding
        if r.get("grounding_term", "").lower() in r["response"].lower()
    )
    grounding_rate = grounding_hits / len(grounding) if grounding else 0.0

    refusals = sum(
        1 for r in hallucination
        if any(p in r["response"].lower() for p in UNCERTAINTY_PHRASES)
    )
    hallucination_rate = 1.0 - (refusals / len(hallucination)) if hallucination else 0.0

    tool_enforcement_pass = all(
        not (DISABLED_TOOLS & set(r.get("tool_calls_made", [])))
        for r in enforcement
    ) if enforcement else True

    avg_ms = int(sum(r["response_ms"] for r in results) / len(results)) if results else 0

    write_tests = [r for r in results if r["type"] == "write_exercise"]
    if write_tests:
        gate_held_rate     = sum(1 for r in write_tests if r.get("gate_held"))     / len(write_tests)
        write_confirm_rate = sum(1 for r in write_tests if r.get("write_confirmed")) / len(write_tests)
        content_match_rate = sum(1 for r in write_tests if r.get("content_match"))   / len(write_tests)
    else:
        gate_held_rate = write_confirm_rate = content_match_rate = None

    return {
        "tool_accuracy": round(tool_accuracy, 4),
        "grounding_rate": round(grounding_rate, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "tool_enforcement_pass": tool_enforcement_pass,
        "avg_response_ms": avg_ms,
        "write_gate_rate":    round(gate_held_rate,     4) if gate_held_rate     is not None else None,
        "write_confirm_rate": round(write_confirm_rate, 4) if write_confirm_rate is not None else None,
        "content_match_rate": round(content_match_rate, 4) if content_match_rate is not None else None,
    }


def write_results(scores: dict, results: list[dict], model: str,
                  vault_type: str, output_dir: Path,
                  inference_host: str | None = None,
                  gpu_accelerated: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    slug = f"{today}-{model.replace(':', '-')}-{vault_type}"
    existing = [f.stem for f in output_dir.glob(f"{slug}-r*.yaml")]
    runs = [int(s.rsplit("-r", 1)[1]) for s in existing if s.rsplit("-r", 1)[-1].isdigit()]
    run_n = max(runs, default=0) + 1
    out_path = output_dir / f"{slug}-r{run_n}.yaml"

    doc = {
        "date": today,
        "model": model,
        "vault_type": vault_type,
        "inference_host": inference_host or socket.gethostname(),
        "gpu_accelerated": gpu_accelerated,
        "stability_tier": 0,
        **scores,
        "prompt_results": [
            {
                "id": r["id"],
                "type": r["type"],
                "tool_calls_made": r.get("tool_calls_made", []),
                "response_ms": r["response_ms"],
                "passed": _prompt_passed(r),
                "expected_tool": r.get("expected_tool"),
                "grounding_term": r.get("grounding_term"),
                "response": r.get("response", ""),
            }
            for r in results
        ],
    }
    out_path.write_text(yaml.dump(doc, default_flow_style=False, allow_unicode=True),
                        encoding="utf-8")
    return out_path


def _tool_exercise_passed(result: dict) -> bool:
    expected = result.get("expected_tool")
    made = set(result.get("tool_calls_made", []))
    if isinstance(expected, list):
        return bool(set(expected) & made)
    return expected in made


def _prompt_passed(result: dict) -> bool:
    t = result["type"]
    if t == "tool_exercise":
        return _tool_exercise_passed(result)
    if t == "grounding":
        term = result.get("grounding_term", "")
        return term.lower() in result["response"].lower()
    if t == "hallucination_boundary":
        return any(p in result["response"].lower() for p in UNCERTAINTY_PHRASES)
    if t == "tool_enforcement":
        return not (DISABLED_TOOLS & set(result.get("tool_calls_made", [])))
    if t == "write_exercise":
        return (result.get("gate_held", False)
                and result.get("write_confirmed", False)
                and result.get("content_match", False))
    return False
