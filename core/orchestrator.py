"""
orchestrator.py — Ariel entry point.

Imports the canonical base from the lmf package and wires ArielOrchestrator
as the concrete implementation.

Start the server:
  python3 core/orchestrator.py [vault_path]
"""
import sys
from pathlib import Path

from lmf.orchestrator import (  # noqa: F401  re-exported for test compat
    Orchestrator,
    Handler,
    run_with,
    is_confirmation,
    _WRITE_TOOLS,
    load_config,
    load_deploy_config,
    _init_config,
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    OLLAMA_NUM_CTX,
)

_ARIEL_TOOLS_CONFIG = Path(__file__).parent / "tools.config.yaml"


def run(vault_path: str):
    from ariel.persona import ArielOrchestrator
    run_with(
        ArielOrchestrator,
        vault_path,
        tools_config_path=_ARIEL_TOOLS_CONFIG,
        ui_file=Path(__file__).parent.parent / "features" / "ui" / "ariel.html",
    )


if __name__ == "__main__":
    cfg = load_config()
    vault = sys.argv[1] if len(sys.argv) > 1 else cfg.get("vault_path", str(Path.home() / "Documents" / "vault"))
    run(vault)
