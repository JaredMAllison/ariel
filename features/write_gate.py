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


class CockpitBackend:
    """
    Approval backend routing proposals to Cockpit subscreen 3.
    Not yet wired — raises NotImplementedError until the Cockpit
    write-gate webhook endpoint is implemented.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url

    def present(self, proposals: list[WriteProposal]) -> None:
        raise NotImplementedError(
            "CockpitBackend not yet wired. "
            "Subscreen 3 webhook endpoint (/api/write-gate/propose) is pending. "
            "Use StdioBackend or MockBackend until Cockpit wiring is complete."
        )

    def await_decision(self) -> Decision:
        raise NotImplementedError(
            "CockpitBackend not yet wired. "
            "Use StdioBackend or MockBackend until Cockpit wiring is complete."
        )


class StdioBackend:
    def __init__(self, input_fn=None, output_fn=None):
        self._input = input_fn if input_fn is not None else input
        self._output = output_fn if output_fn is not None else print
        self._proposals: list[WriteProposal] = []

    def present(self, proposals: list[WriteProposal]) -> None:
        self._proposals = proposals
        self._output(f"\nProposed writes ({len(proposals)}):\n")
        for i, p in enumerate(proposals, 1):
            self._output(f"  [{i}] {p.operation:<8}  {p.path}")
            self._output(f"       {p.description}")
        self._output("")

    def await_decision(self) -> Decision:
        n = len(self._proposals)
        while True:
            raw = self._input("Approve? [yes/no/1 3 5/skip 2]: ").strip().lower()
            if raw in ("yes", "all"):
                return Decision(verdict="all", approved_indices=[])
            if raw in ("no", "cancel"):
                return Decision(verdict="none", approved_indices=[])
            if raw.startswith("skip "):
                parts = raw[5:].split()
                if all(p.isdigit() for p in parts):
                    skip_0based = {int(p) - 1 for p in parts}
                    approved = [i for i in range(n) if i not in skip_0based]
                    return Decision(verdict="partial", approved_indices=approved)
            parts = raw.split()
            if parts and all(p.isdigit() for p in parts):
                approved = [int(p) - 1 for p in parts]
                return Decision(verdict="partial", approved_indices=approved)
            self._output("  Invalid input. Enter: yes / no / 1 3 5 / skip 2 4")


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
