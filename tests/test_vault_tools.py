"""Unit tests for orchestrator vault I/O helpers (no Loom needed)."""
import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from orchestrator import Orchestrator


def _make_vault(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "LOCAL_MIND_FOUNDATION.md").write_text("---\ntitle: test\n---")
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


def test_list_files():
    vault = _make_vault({
        "Tasks/a.md": "line1\nline2\n",
        "Tasks/b.md": "only one\n",
        "Inbox.md": "",
    })
    try:
        orch = Orchestrator(str(vault))
        files = orch._tool_list_files()
        names = [f["file"] for f in files]
        assert "Inbox.md" in names
        assert "Tasks/a.md" in names
        assert "Tasks/b.md" in names
        a_entry = next(f for f in files if f["file"] == "Tasks/a.md")
        assert a_entry["line_count"] == 2
        b_entry = next(f for f in files if f["file"] == "Tasks/b.md")
        assert b_entry["line_count"] == 1
        assert all(f["size_kb"] >= 0 for f in files)
        print("PASS: list_files")
    finally:
        shutil.rmtree(vault)


def test_outline():
    vault = _make_vault({
        "note.md": (
            "# Title\n"
            "some text\n"
            "## Section A\n"
            "stuff\n"
            "## Section B\n"
            "### Sub B1\n"
            "details\n"
        ),
    })
    try:
        orch = Orchestrator(str(vault))
        result = orch._tool_outline("note.md")
        headings = [(h["level"], h["heading"]) for h in result]
        assert headings == [(1, "Title"), (2, "Section A"), (2, "Section B"), (3, "Sub B1")]
        print("PASS: outline")
    finally:
        shutil.rmtree(vault)


def test_outline_missing_file():
    vault = _make_vault({})
    try:
        orch = Orchestrator(str(vault))
        result = orch._tool_outline("nonexistent.md")
        assert "error" in result
        print("PASS: outline missing file")
    finally:
        shutil.rmtree(vault)


def test_read_lines():
    vault = _make_vault({"file.md": "a\nb\nc\nd\ne\n"})
    try:
        orch = Orchestrator(str(vault))
        r = orch._tool_read_lines("file.md", 2, 4)
        assert r["content"] == "b\nc\nd"
        assert r["start_line"] == 2
        assert r["end_line"] == 4

        r2 = orch._tool_read_lines("file.md", 1, 100)
        assert r2["content"] == "a\nb\nc\nd\ne"
        assert r2["end_line"] == 5

        r3 = orch._tool_read_lines("file.md", 0, 2)
        assert r3["start_line"] == 1

        assert orch._tool_read_lines("missing.md", 1, 1) is None
        print("PASS: read_lines")
    finally:
        shutil.rmtree(vault)


def test_read_section():
    content = (
        "# Top\n"
        "intro\n"
        "## Alpha\n"
        "alpha body\n"
        "more alpha\n"
        "## Beta\n"
        "beta body\n"
    )
    vault = _make_vault({"doc.md": content})
    try:
        orch = Orchestrator(str(vault))
        r = orch._tool_read_section("doc.md", "Alpha")
        assert r is not None
        assert r["heading"] == "Top > Alpha"
        assert "alpha body" in r["content"]
        assert "beta body" not in r["content"]

        r2 = orch._tool_read_section("doc.md", "nonexistent")
        assert r2 is None

        r3 = orch._tool_read_section("missing.md", "x")
        assert "error" in r3
        print("PASS: read_section")
    finally:
        shutil.rmtree(vault)


def test_grep():
    vault = _make_vault({
        "Tasks/a.md": "buy milk\nwalk dog\n",
        "Tasks/b.md": "feed cat\nbuy food\n",
        "Inbox.md": "random thought\n",
    })
    try:
        orch = Orchestrator(str(vault))
        r = orch._tool_grep("buy")
        assert len(r) == 2
        assert all("buy" in m["line_text"] for m in r)

        r2 = orch._tool_grep("buy", file_filter="Tasks/")
        assert len(r2) == 2

        r3 = orch._tool_grep("buy", file_filter="Inbox")
        assert len(r3) == 0

        r4 = orch._tool_grep("[invalid")
        assert "error" in r4[0]
        print("PASS: grep")
    finally:
        shutil.rmtree(vault)


def test_append_to_file():
    vault = _make_vault({"log.md": "existing\n"})
    try:
        orch = Orchestrator(str(vault))
        r = orch._tool_append_to_file("log.md", "new line")
        assert r["file"] == "log.md"
        assert r["appended_at_line"] == 3
        assert (vault / "log.md").read_text() == "existing\n\nnew line\n"

        r2 = orch._tool_append_to_file("new_file.md", "first line")
        assert r2["appended_at_line"] == 2
        assert (vault / "new_file.md").exists()
        print("PASS: append_to_file")
    finally:
        shutil.rmtree(vault)


def test_replace_lines():
    vault = _make_vault({"doc.md": "a\nb\nc\nd\ne\n"})
    try:
        orch = Orchestrator(str(vault))
        r = orch._tool_replace_lines("doc.md", 2, 4, "x\ny")
        assert r["replaced_lines"] == 3
        assert r["new_line_count"] == 4
        assert (vault / "doc.md").read_text() == "a\nx\ny\ne\n"

        r2 = orch._tool_replace_lines("doc.md", 1, 1, "first")
        assert r2["replaced_lines"] == 1
        print("PASS: replace_lines")
    finally:
        shutil.rmtree(vault)


def test_dispatch_read_lines():
    vault = _make_vault({"f.md": "hello\nworld\n"})
    try:
        orch = Orchestrator(str(vault))
        result = json.loads(orch._dispatch_tool("read_lines", {"file_path": "f.md", "start_line": 1, "end_line": 2}))
        assert result["content"] == "hello\nworld"
        print("PASS: dispatch read_lines via _dispatch_tool")
    finally:
        shutil.rmtree(vault)


def test_dispatch_list_files():
    vault = _make_vault({"a.md": "x\n"})
    try:
        orch = Orchestrator(str(vault))
        result = json.loads(orch._dispatch_tool("list_files", {}))
        names = [f["file"] for f in result]
        assert "a.md" in names
        assert "LOCAL_MIND_FOUNDATION.md" in names
        print("PASS: dispatch list_files via _dispatch_tool")
    finally:
        shutil.rmtree(vault)


if __name__ == "__main__":
    test_list_files()
    test_outline()
    test_outline_missing_file()
    test_read_lines()
    test_read_section()
    test_grep()
    test_append_to_file()
    test_replace_lines()
    test_dispatch_read_lines()
    test_dispatch_list_files()
    print("\nAll vault tool tests passed!")
