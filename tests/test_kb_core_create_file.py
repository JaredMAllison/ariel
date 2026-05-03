# tests/test_kb_core_create_file.py
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".local/share/obsidian-mcp"))
from kb_core import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    (tmp_path / "vault").mkdir()
    return KnowledgeBase(tmp_path / "vault")


def test_create_file_creates_new_file(kb, tmp_path):
    result = kb.create_file("Tasks/new-task.md", "---\ntitle: New Task\n---\n")
    assert result["created"] is True
    assert (tmp_path / "vault" / "Tasks" / "new-task.md").exists()
    assert result["line_count"] == 3


def test_create_file_creates_parent_dirs(kb, tmp_path):
    result = kb.create_file("Deep/Nested/note.md", "content")
    assert (tmp_path / "vault" / "Deep" / "Nested" / "note.md").exists()
    assert result["created"] is True


def test_create_file_refuses_overwrite(kb, tmp_path):
    (tmp_path / "vault" / "existing.md").write_text("original")
    result = kb.create_file("existing.md", "new content")
    assert "error" in result
    assert (tmp_path / "vault" / "existing.md").read_text() == "original"


def test_create_file_returns_file_path(kb):
    result = kb.create_file("Notes/test.md", "hello")
    assert result["file"] == "Notes/test.md"
