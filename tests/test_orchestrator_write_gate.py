import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from orchestrator import is_confirmation, _WRITE_TOOLS, _format_proposal


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
