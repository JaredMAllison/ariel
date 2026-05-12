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
