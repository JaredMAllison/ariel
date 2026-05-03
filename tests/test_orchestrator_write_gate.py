import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from orchestrator import is_confirmation, _WRITE_TOOLS, _format_proposal
import orchestrator as orch_module
from orchestrator import Orchestrator


# --- Helpers for mocking Ollama responses ---

def _text(content):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"message": {"role": "assistant", "content": content}}
    return r


def _tool_call(name, args):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}}],
    }}
    return r


@pytest.fixture
def orch(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    orch_module.OLLAMA_URL     = "http://localhost:11434/api/chat"
    orch_module.OLLAMA_MODEL   = "qwen2.5:1.5b"
    orch_module.OLLAMA_TIMEOUT = 30
    orch_module.OLLAMA_NUM_CTX = 8192
    return Orchestrator(str(vault))


def test_is_confirmation_affirmatives():
    for word in ["yes", "YES", "Yes", "y", "yeah", "yep", "sure", "ok",
                 "go ahead", "confirm", "do it"]:
        assert is_confirmation(word), f"Expected '{word}' to be affirmative"


def test_is_confirmation_negatives():
    for word in ["no", "NO", "n", "nope", "cancel", "stop", "reject"]:
        assert not is_confirmation(word), f"Expected '{word}' to be negative"


def test_is_confirmation_unrelated_is_negative():
    assert not is_confirmation("what time is it?")
    assert not is_confirmation("tell me about the project")
    assert not is_confirmation("")


def test_is_confirmation_strips_whitespace_and_punctuation():
    assert is_confirmation("  yes.  ")
    assert is_confirmation("yes!")
    assert not is_confirmation("  no.  ")


def test_write_tools_set_contains_expected():
    assert "append_to_file"       in _WRITE_TOOLS
    assert "replace_lines"        in _WRITE_TOOLS
    assert "create_file"          in _WRITE_TOOLS
    assert "insert_after_heading" in _WRITE_TOOLS
    assert "search_vault"         not in _WRITE_TOOLS
    assert "read_section"         not in _WRITE_TOOLS


def test_format_proposal_append():
    p = _format_proposal("append_to_file", {"file_path": "Inbox.md", "content": "- buy milk"})
    assert "append to" in p
    assert "`Inbox.md`" in p
    assert "- buy milk" in p
    assert "Confirm? (yes/no)" in p


def test_format_proposal_create():
    p = _format_proposal("create_file", {"file_path": "Tasks/new.md", "content": "---\ntitle: New\n---"})
    assert "create" in p
    assert "`Tasks/new.md`" in p
    assert "Confirm? (yes/no)" in p


def test_format_proposal_unknown_tool():
    p = _format_proposal("unknown_tool", {"file_path": "test.md", "content": "data"})
    assert "Confirm? (yes/no)" in p


# --- Gate behaviour tests (Task 3) ---

def test_gate_fires_on_write_tool_call(orch):
    with patch("requests.post",
               return_value=_tool_call("append_to_file",
                                       {"file_path": "Inbox.md", "content": "- test item"})):
        reply = orch.chat("add 'test item' to my inbox")

    assert orch.pending_write is not None
    assert orch.pending_write["name"] == "append_to_file"
    assert "`Inbox.md`" in reply
    assert "Confirm? (yes/no)" in reply


def test_gate_dispatches_on_yes(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "Ariel wants to append to `Inbox.md`:\n\n- test item\n\nConfirm? (yes/no)",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 42}') as mock:
        reply = orch.chat("yes")

    mock.assert_called_once_with("append_to_file", {"file_path": "Inbox.md", "content": "- test item"})
    assert orch.pending_write is None
    assert "Done" in reply


def test_gate_clears_on_no(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "...",
    }
    with patch("requests.post", return_value=_text("Understood, cancelled.")):
        orch.chat("no")
    assert orch.pending_write is None


def test_gate_clears_on_unrelated_message(orch):
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test item"},
        "proposal": "...",
    }
    with patch("requests.post", return_value=_text("Here is what I know.")):
        orch.chat("tell me about my projects")
    assert orch.pending_write is None


def test_read_tools_dispatch_immediately(orch):
    with patch.object(orch, "_dispatch_tool", return_value='{"results": []}') as mock:
        with patch("requests.post", side_effect=[
            _tool_call("search_vault", {"query": "tasks"}),
            _text("I found some tasks."),
        ]):
            orch.chat("what tasks do I have?")
    mock.assert_called_once_with("search_vault", {"query": "tasks"})
    assert orch.pending_write is None


# --- verbose_writes / test_mode / path validation tests (Task 4) ---

def test_verbose_writes_appends_summary(orch):
    orch.verbose_writes = True
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 5}'):
        reply = orch.chat("yes")
    assert "✓ Written to `Inbox.md`" in reply


def test_test_mode_implies_verbose(orch):
    orch.test_mode = True
    orch.pending_write = {
        "name": "create_file",
        "args": {"file_path": "Tasks/new.md", "content": "---\ntitle: New\n---"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Tasks/new.md", "created": true, "line_count": 3}'):
        reply = orch.chat("yes")
    assert "✓ Written to `Tasks/new.md`" in reply


def test_no_verbose_no_summary(orch):
    orch.verbose_writes = False
    orch.test_mode      = False
    orch.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "- test"},
        "proposal": "...",
    }
    with patch.object(orch, "_dispatch_tool",
                      return_value='{"file": "Inbox.md", "appended_at_line": 5}'):
        reply = orch.chat("yes")
    assert "✓" not in reply
    assert "Done" in reply


def test_path_validation_rejects_traversal(orch):
    orch.allow_external_writes = False
    result = json.loads(orch._dispatch_tool(
        "append_to_file", {"file_path": "../../etc/passwd", "content": "bad"}
    ))
    assert "error" in result
    assert "external writes disabled" in result["error"]


def test_path_validation_rejects_absolute(orch):
    orch.allow_external_writes = False
    result = json.loads(orch._dispatch_tool(
        "create_file", {"file_path": "/tmp/escape.md", "content": "bad"}
    ))
    assert "error" in result


def test_path_validation_allows_when_toggled(orch, tmp_path):
    orch.allow_external_writes = True
    external = tmp_path / "outside.md"
    with patch.object(orch.kb, "append_to_file",
                      return_value={"file": str(external), "appended_at_line": 1}):
        result = json.loads(orch._dispatch_tool(
            "append_to_file", {"file_path": str(external), "content": "hello"}
        ))
    assert "error" not in result
