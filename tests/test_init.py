import sys
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_init_writes_config(tmp_path):
    from init import write_config
    config_path = tmp_path / "operator" / "config.yaml"
    config_path.parent.mkdir()
    cfg = {
        "vault_path": "/my/vault",
        "model": "qwen2.5:3b",
        "port": 9000,
        "num_ctx": 4096,
        "ollama_url": "http://localhost:11434/api/chat",
        "timeout_s": 300,
    }
    write_config(config_path, cfg)
    result = yaml.safe_load(config_path.read_text())
    assert result["vault_path"] == "/my/vault"
    assert result["model"] == "qwen2.5:3b"
    assert result["port"] == 9000


def test_init_exits_if_config_exists(tmp_path):
    from init import main
    config_path = tmp_path / "config.yaml"
    config_path.write_text("vault_path: /existing")
    with pytest.raises(SystemExit) as exc:
        main(config_path=config_path)
    assert exc.value.code == 0


def test_init_reset_flag_allows_overwrite(tmp_path):
    from init import main
    config_path = tmp_path / "config.yaml"
    config_path.write_text("vault_path: /old")
    inputs = ["/new/vault", "qwen2.5:1.5b", "8742", "8192"]
    with patch("builtins.input", side_effect=inputs):
        main(config_path=config_path, reset=True)
    result = yaml.safe_load(config_path.read_text())
    assert result["vault_path"] == "/new/vault"
