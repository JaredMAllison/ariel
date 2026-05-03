#!/usr/bin/env python3
"""lmf-ollama-obsidian bootstrap — writes operator/config.yaml on first run."""

import sys
import yaml
from pathlib import Path

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "operator" / "config.yaml"

DEFAULTS = {
    "vault_path": str(Path.home() / "Documents/Obsidian/Marlin"),
    "model": "qwen2.5:1.5b",
    "port": 8742,
    "num_ctx": 8192,
    "ollama_url": "http://localhost:11434/api/chat",
    "timeout_s": 300,
}


def _prompt(label: str, default) -> str:
    val = input(f"{label} [{default}]: ").strip()
    return val if val else str(default)


def write_config(config_path: Path, cfg: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def main(config_path: Path | None = None, reset: bool = False) -> None:
    if config_path is None:
        config_path = _DEFAULT_CONFIG_PATH

    if not reset and config_path.exists():
        print(f"Config already exists at {config_path}")
        print("Run with --reset to reconfigure.")
        sys.exit(0)

    print("\nlmf-ollama-obsidian — first run setup")
    print("─" * 30)

    cfg = {
        "vault_path": _prompt("Vault path", DEFAULTS["vault_path"]),
        "model": _prompt("Ollama model", DEFAULTS["model"]),
        "port": int(_prompt("Port", DEFAULTS["port"])),
        "num_ctx": int(_prompt("Num context tokens", DEFAULTS["num_ctx"])),
        "ollama_url": DEFAULTS["ollama_url"],
        "timeout_s": DEFAULTS["timeout_s"],
        "verbose_writes": False,
        "allow_external_writes": False,
    }

    write_config(config_path, cfg)
    print(f"\nWriting {config_path}... done.")
    print("Run: python3 core/orchestrator.py")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
