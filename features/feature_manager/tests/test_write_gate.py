import pytest

from features.write_gate import (
    WriteProposal,
    Decision,
    GateResult,
    ApprovalBackend,
    MockBackend,
    WriteGate,
    StdioBackend,
    CockpitBackend,
)


def test_write_proposal_create():
    p = WriteProposal(
        path="Tasks/brush-teeth.md",
        content="# Brush teeth\n",
        operation="create",
        description="Create Tasks/brush-teeth.md",
    )
    assert p.path == "Tasks/brush-teeth.md"
    assert p.operation == "create"


def test_write_proposal_all_operations():
    for op in ("create", "update", "delete"):
        p = WriteProposal(path="f.md", content="", operation=op, description="desc")
        assert p.operation == op


def test_decision_all_verdict():
    d = Decision(verdict="all", approved_indices=[])
    assert d.verdict == "all"
    assert d.approved_indices == []


def test_decision_partial_verdict():
    d = Decision(verdict="partial", approved_indices=[0, 2])
    assert d.approved_indices == [0, 2]


def test_gate_result_fields():
    p1 = WriteProposal(path="a.md", content="", operation="create", description="A")
    p2 = WriteProposal(path="b.md", content="", operation="update", description="B")
    r = GateResult(approved=[p1], rejected=[p2])
    assert r.approved == [p1]
    assert r.rejected == [p2]


def _make_proposal(path="Tasks/a.md", operation="create"):
    return WriteProposal(path=path, content="# test\n", operation=operation, description=f"Test {path}")


def test_mock_backend_records_present():
    decision = Decision(verdict="all", approved_indices=[])
    backend = MockBackend(decision)
    proposals = [_make_proposal()]
    backend.present(proposals)
    assert backend.presented == proposals


def test_mock_backend_returns_preset_decision():
    decision = Decision(verdict="none", approved_indices=[])
    backend = MockBackend(decision)
    backend.present([_make_proposal()])
    result = backend.await_decision()
    assert result is decision


def test_mock_backend_presented_none_before_present():
    decision = Decision(verdict="all", approved_indices=[])
    backend = MockBackend(decision)
    assert backend.presented is None


def _three_proposals():
    return [
        WriteProposal("a.md", "A", "create", "Create a.md"),
        WriteProposal("b.md", "B", "update", "Update b.md"),
        WriteProposal("c.md", "C", "delete", "Delete c.md"),
    ]


def test_apply_decision_all():
    gate = WriteGate(backend=MockBackend(Decision(verdict="all")))
    proposals = _three_proposals()
    result = gate._apply_decision(proposals, Decision(verdict="all"))
    assert result.approved == proposals
    assert result.rejected == []


def test_apply_decision_none():
    gate = WriteGate(backend=MockBackend(Decision(verdict="none")))
    proposals = _three_proposals()
    result = gate._apply_decision(proposals, Decision(verdict="none"))
    assert result.approved == []
    assert result.rejected == proposals


def test_apply_decision_partial():
    gate = WriteGate(backend=MockBackend(Decision(verdict="all")))
    proposals = _three_proposals()
    result = gate._apply_decision(proposals, Decision(verdict="partial", approved_indices=[0, 2]))
    assert result.approved == [proposals[0], proposals[2]]
    assert result.rejected == [proposals[1]]


def test_apply_decision_approved_and_rejected_are_exhaustive():
    gate = WriteGate(backend=MockBackend(Decision(verdict="all")))
    proposals = _three_proposals()
    result = gate._apply_decision(proposals, Decision(verdict="partial", approved_indices=[1]))
    # approved + rejected must account for every proposal exactly once
    assert len(result.approved) + len(result.rejected) == len(proposals)
    assert result.approved == [proposals[1]]
    assert result.rejected == [proposals[0], proposals[2]]


def test_propose_empty_list_returns_empty_without_calling_backend():
    backend = MockBackend(Decision(verdict="all"))
    gate = WriteGate(backend)
    result = gate.propose([])
    assert result.approved == []
    assert result.rejected == []
    assert backend.presented is None  # present() was never called


def test_propose_all_approved():
    proposals = _three_proposals()
    backend = MockBackend(Decision(verdict="all"))
    gate = WriteGate(backend)
    result = gate.propose(proposals)
    assert result.approved == proposals
    assert result.rejected == []
    assert backend.presented == proposals  # present() was called


def test_propose_all_rejected():
    proposals = _three_proposals()
    backend = MockBackend(Decision(verdict="none"))
    gate = WriteGate(backend)
    result = gate.propose(proposals)
    assert result.approved == []
    assert result.rejected == proposals


def test_propose_partial_approval():
    proposals = _three_proposals()
    backend = MockBackend(Decision(verdict="partial", approved_indices=[0, 2]))
    gate = WriteGate(backend)
    result = gate.propose(proposals)
    assert result.approved == [proposals[0], proposals[2]]
    assert result.rejected == [proposals[1]]


def test_propose_calls_present_then_await_decision():
    """present() is called before await_decision() — confirmed via call-order tracking."""
    proposals = _three_proposals()
    call_order = []

    class TrackingBackend:
        def present(self, p):
            call_order.append("present")
        def await_decision(self):
            call_order.append("await_decision")
            return Decision(verdict="all")

    gate = WriteGate(TrackingBackend())
    gate.propose(proposals)
    assert call_order == ["present", "await_decision"]


def test_stdio_present_outputs_proposal_count(capsys):
    backend = StdioBackend()
    backend.present(_three_proposals())
    captured = capsys.readouterr()
    assert "3" in captured.out


def test_stdio_present_outputs_all_paths(capsys):
    backend = StdioBackend()
    proposals = _three_proposals()
    backend.present(proposals)
    captured = capsys.readouterr()
    for p in proposals:
        assert p.path in captured.out


def test_stdio_present_outputs_all_descriptions(capsys):
    backend = StdioBackend()
    proposals = _three_proposals()
    backend.present(proposals)
    captured = capsys.readouterr()
    for p in proposals:
        assert p.description in captured.out


def test_stdio_present_outputs_1based_numbering(capsys):
    backend = StdioBackend()
    backend.present(_three_proposals())
    captured = capsys.readouterr()
    assert "[1]" in captured.out
    assert "[2]" in captured.out
    assert "[3]" in captured.out
    assert "[0]" not in captured.out


def test_stdio_present_stores_proposals_for_await():
    backend = StdioBackend()
    proposals = _three_proposals()
    backend.present(proposals)
    assert backend._proposals == proposals


def _stdio_with_inputs(*responses):
    """Return a StdioBackend that reads from the given response sequence."""
    it = iter(responses)
    lines = []
    def fake_output(text=""):
        lines.append(text)
    return StdioBackend(input_fn=lambda _: next(it), output_fn=fake_output), lines


def test_stdio_await_yes():
    backend, _ = _stdio_with_inputs("yes")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "all"
    assert d.approved_indices == []


def test_stdio_await_all():
    backend, _ = _stdio_with_inputs("all")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "all"


def test_stdio_await_no():
    backend, _ = _stdio_with_inputs("no")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "none"
    assert d.approved_indices == []


def test_stdio_await_cancel():
    backend, _ = _stdio_with_inputs("cancel")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "none"


def test_stdio_await_indices():
    backend, _ = _stdio_with_inputs("1 3")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "partial"
    assert d.approved_indices == [0, 2]  # 1-based input → 0-based indices


def test_stdio_await_single_index():
    backend, _ = _stdio_with_inputs("2")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "partial"
    assert d.approved_indices == [1]


def test_stdio_await_skip():
    backend, _ = _stdio_with_inputs("skip 2")
    backend.present(_three_proposals())  # 3 proposals: indices 0,1,2
    d = backend.await_decision()
    assert d.verdict == "partial"
    assert d.approved_indices == [0, 2]  # skip 1-based "2" → skip 0-based 1


def test_stdio_await_skip_multiple():
    backend, _ = _stdio_with_inputs("skip 1 3")
    backend.present(_three_proposals())  # 3 proposals
    d = backend.await_decision()
    assert d.verdict == "partial"
    assert d.approved_indices == [1]  # skip 0-based 0 and 2


def test_stdio_await_malformed_then_valid():
    """Invalid input re-prompts; second valid input returns a decision."""
    backend, output_lines = _stdio_with_inputs("garbage", "yes")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "all"
    assert any("Invalid" in line for line in output_lines)


def test_stdio_await_case_insensitive():
    backend, _ = _stdio_with_inputs("YES")
    backend.present(_three_proposals())
    d = backend.await_decision()
    assert d.verdict == "all"


def test_cockpit_backend_present_raises_not_implemented():
    backend = CockpitBackend(base_url="http://localhost:7832")
    with pytest.raises(NotImplementedError) as exc_info:
        backend.present(_three_proposals())
    assert "subscreen 3" in str(exc_info.value).lower() or "wired" in str(exc_info.value).lower()


def test_cockpit_backend_await_decision_raises_not_implemented():
    backend = CockpitBackend(base_url="http://localhost:7832")
    with pytest.raises(NotImplementedError):
        backend.await_decision()


def test_cockpit_backend_stores_base_url():
    backend = CockpitBackend(base_url="http://10.0.0.8:7832")
    assert backend.base_url == "http://10.0.0.8:7832"
