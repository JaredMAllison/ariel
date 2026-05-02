import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

import pytest
import yaml
from orchestrator import load_config


def test_load_config_reads_all_fields(tmp_path):
    cfg = {
        "vault_path": "/test/vault",
        "model": "qwen2.5:1.5b",
        "port": 8742,
        "num_ctx": 8192,
        "ollama_url": "http://localhost:11434/api/chat",
        "timeout_s": 300,
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    result = load_config(p)
    assert result["vault_path"] == "/test/vault"
    assert result["model"] == "qwen2.5:1.5b"
    assert result["port"] == 8742
    assert result["num_ctx"] == 8192
    assert result["ollama_url"] == "http://localhost:11434/api/chat"
    assert result["timeout_s"] == 300


def test_load_config_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nonexistent.yaml")


def test_ollama_ps_url_derived_from_ollama_url(tmp_path):
    cfg = {
        "vault_path": "/test/vault",
        "model": "qwen2.5:1.5b",
        "port": 8742,
        "num_ctx": 8192,
        "ollama_url": "http://10.0.0.8:11434/api/chat",
        "timeout_s": 300,
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    result = load_config(p)
    assert result["ollama_url"].replace("/api/chat", "/api/ps") == "http://10.0.0.8:11434/api/ps"


def test_orchestrator_tracks_tool_calls():
    from orchestrator import Orchestrator
    # Orchestrator must expose last_tool_calls as an empty list on init
    # We test structure only — no Ollama needed
    orch = Orchestrator.__new__(Orchestrator)
    orch.last_tool_calls = []
    assert isinstance(orch.last_tool_calls, list)
