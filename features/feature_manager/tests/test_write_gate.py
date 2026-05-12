from features.write_gate import (
    WriteProposal,
    Decision,
    GateResult,
    ApprovalBackend,
    MockBackend,
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
