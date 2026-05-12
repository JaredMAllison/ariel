from features.write_gate import (
    WriteProposal,
    Decision,
    GateResult,
    ApprovalBackend,
    MockBackend,
    WriteGate,
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
