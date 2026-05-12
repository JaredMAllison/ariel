from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class WriteProposal:
    path: str
    content: str
    operation: Literal["create", "update", "delete"]
    description: str


@dataclass
class Decision:
    verdict: Literal["all", "none", "partial"]
    approved_indices: list[int] = field(default_factory=list)


@dataclass
class GateResult:
    approved: list[WriteProposal]
    rejected: list[WriteProposal]


class ApprovalBackend(Protocol):
    def present(self, proposals: list[WriteProposal]) -> None: ...
    def await_decision(self) -> Decision: ...


class MockBackend:
    def __init__(self, decision: Decision):
        self._decision = decision
        self.presented: list[WriteProposal] | None = None

    def present(self, proposals: list[WriteProposal]) -> None:
        self.presented = proposals

    def await_decision(self) -> Decision:
        return self._decision


class WriteGate:
    def __init__(self, backend: ApprovalBackend):
        self.backend = backend

    def propose(self, proposals: list[WriteProposal]) -> GateResult:
        if not proposals:
            return GateResult(approved=[], rejected=[])
        self.backend.present(proposals)
        decision = self.backend.await_decision()
        return self._apply_decision(proposals, decision)

    def _apply_decision(self, proposals: list[WriteProposal], decision: Decision) -> GateResult:
        if decision.verdict == "all":
            return GateResult(approved=list(proposals), rejected=[])
        if decision.verdict == "none":
            return GateResult(approved=[], rejected=list(proposals))
        approved = [p for i, p in enumerate(proposals) if i in decision.approved_indices]
        rejected = [p for i, p in enumerate(proposals) if i not in decision.approved_indices]
        return GateResult(approved=approved, rejected=rejected)
