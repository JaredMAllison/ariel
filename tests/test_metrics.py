import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "features" / "testing"))

from metrics import score_results, write_results
import yaml


def _make_result(id, type, response, tool_calls_made=None, response_ms=500,
                 expected_tool=None, grounding_term=None):
    return {
        "id": id, "type": type, "query": "test", "response": response,
        "tool_calls_made": tool_calls_made or [],
        "response_ms": response_ms,
        "expected_tool": expected_tool,
        "grounding_term": grounding_term,
    }


def test_tool_accuracy_full_hit():
    results = [
        _make_result("T001", "tool_exercise", "found it",
                     tool_calls_made=["search_vault"], expected_tool="search_vault"),
    ]
    scores = score_results(results)
    assert scores["tool_accuracy"] == 1.0


def test_tool_accuracy_miss():
    results = [
        _make_result("T001", "tool_exercise", "found it",
                     tool_calls_made=["outline"], expected_tool="search_vault"),
    ]
    scores = score_results(results)
    assert scores["tool_accuracy"] == 0.0


def test_grounding_rate_term_present():
    results = [
        _make_result("G001", "grounding", "The task status is queued",
                     grounding_term="queued"),
    ]
    scores = score_results(results)
    assert scores["grounding_rate"] == 1.0


def test_grounding_rate_term_absent():
    results = [
        _make_result("G001", "grounding", "I could not find that information",
                     grounding_term="queued"),
    ]
    scores = score_results(results)
    assert scores["grounding_rate"] == 0.0


def test_hallucination_rate_model_refuses():
    results = [
        _make_result("H001", "hallucination_boundary",
                     "I don't have any information about the Omega Initiative."),
    ]
    scores = score_results(results)
    assert scores["hallucination_rate"] == 0.0


def test_hallucination_rate_model_fabricates():
    results = [
        _make_result("H001", "hallucination_boundary",
                     "The Omega Initiative is a top-secret AI project worth $5M."),
    ]
    scores = score_results(results)
    assert scores["hallucination_rate"] == 1.0


def test_tool_enforcement_pass():
    results = [
        _make_result("E001", "tool_enforcement", "I cannot write to files.",
                     tool_calls_made=[]),
    ]
    scores = score_results(results)
    assert scores["tool_enforcement_pass"] is True


def test_tool_enforcement_fail():
    results = [
        _make_result("E001", "tool_enforcement", "Done.",
                     tool_calls_made=["append_to_file"]),
    ]
    scores = score_results(results)
    assert scores["tool_enforcement_pass"] is False


def test_tool_accuracy_list_hit():
    results = [
        _make_result("T001", "tool_exercise", "found it",
                     tool_calls_made=["grep_vault"], expected_tool=["search_vault", "grep_vault"]),
    ]
    scores = score_results(results)
    assert scores["tool_accuracy"] == 1.0


def test_tool_accuracy_list_miss():
    results = [
        _make_result("T001", "tool_exercise", "found it",
                     tool_calls_made=["outline"], expected_tool=["search_vault", "grep_vault"]),
    ]
    scores = score_results(results)
    assert scores["tool_accuracy"] == 0.0


def test_write_results_creates_yaml(tmp_path):
    results = [_make_result("T001", "tool_exercise", "ok", tool_calls_made=["search_vault"],
                             expected_tool="search_vault")]
    scores = score_results(results)
    out = write_results(scores, results, model="qwen2.5:1.5b",
                        vault_type="synthetic", output_dir=tmp_path)
    data = yaml.safe_load(out.read_text())
    assert data["model"] == "qwen2.5:1.5b"
    assert data["vault_type"] == "synthetic"
    assert "tool_accuracy" in data
    assert data["prompt_results"][0]["response"] == "ok"
    assert "-r1.yaml" in out.name


def test_write_results_run_counter_increments(tmp_path):
    results = [_make_result("T001", "tool_exercise", "ok", tool_calls_made=["search_vault"],
                             expected_tool="search_vault")]
    scores = score_results(results)
    r1 = write_results(scores, results, model="qwen2.5:1.5b",
                       vault_type="synthetic", output_dir=tmp_path)
    r2 = write_results(scores, results, model="qwen2.5:1.5b",
                       vault_type="synthetic", output_dir=tmp_path)
    assert "-r1.yaml" in r1.name
    assert "-r2.yaml" in r2.name
    assert r1 != r2
