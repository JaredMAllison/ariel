import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from ariel.write_intent import WriteIntentParser, WriteIntent


def _parse(msg):
    return WriteIntentParser().parse(msg)


# --- Inbox append patterns ---

def test_inbox_add_this_colon_form():
    """'Add this to my inbox: content' — content after colon."""
    result = _parse("Add this to my inbox: 'Test entry from write gate battery run.'")
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Inbox.md"
    assert "Test entry from write gate battery run" in result.args["content"]


def test_inbox_add_content_before():
    """'Add X to my inbox' — content before to-inbox."""
    result = _parse("Add this important thing to my inbox")
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Inbox.md"


def test_inbox_append_quoted():
    """'Append 'X' to my inbox' — quoted content."""
    result = _parse("Append 'SHOULD NOT APPEAR' to my inbox.")
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Inbox.md"


def test_inbox_append_unquoted():
    """'Append X to my inbox' — unquoted."""
    result = _parse("Append something to my inbox")
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Inbox.md"


# --- Explicit file append ---

def test_append_to_explicit_file():
    """'Append X to the file path/to/file.md'."""
    result = _parse(
        "Append 'Write gate battery run — confirmed.' to the file Projects/ariel-von-marlin.md."
    )
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Projects/ariel-von-marlin.md"
    assert "Write gate battery run" in result.args["content"]


# --- Create at explicit path ---

def test_create_at_explicit_path_with_title():
    """'Create a new task note at Tasks/foo.md with title 'Bar''."""
    result = _parse(
        "Create a new task note at Tasks/test-write-gate-task.md with title "
        "'Test write gate task', status queued, context computer, duration short."
    )
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"] == "Tasks/test-write-gate-task.md"
    assert "Test write gate task" in result.args["content"]


def test_create_at_explicit_path_with_content():
    """'Create a new insight note at Insights/foo.md with the content: 'Bar''."""
    result = _parse(
        "Create a new insight note at Insights/write-gate-battery-test.md with "
        "the content: 'Write gate wired and confirmed. Operator approval enforced.'"
    )
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"] == "Insights/write-gate-battery-test.md"
    assert "Operator approval enforced" in result.args["content"]


# --- Task create ---

def test_create_task_for():
    """'Create a task for X'."""
    result = _parse("Create a task for write gate verification")
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"].startswith("Tasks/")
    assert "write-gate-verification" in result.args["file_path"]


def test_create_task_called():
    """'Create a task called X'."""
    result = _parse("Create a task called review quarterly budget")
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"].startswith("Tasks/")


# --- Insight create ---

def test_create_insight_about():
    """'Create an insight about X'."""
    result = _parse("Create an insight about write gate reliability")
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"].startswith("Insights/")


def test_capture_as_insight():
    """'Capture X as an insight'."""
    result = _parse("Capture this as an insight")
    assert result is not None
    assert result.tool == "create_file"
    assert result.args["file_path"].startswith("Insights/")


# --- Non-matches pass through ---

def test_no_match_question():
    assert _parse("What tasks do I have today?") is None


def test_no_match_read_request():
    assert _parse("Show me my inbox") is None


def test_no_match_general_chat():
    assert _parse("How are you doing?") is None


def test_no_match_short_message():
    assert _parse("yes") is None


# --- Slugify ---

def test_slugify_spaces_to_hyphens():
    from ariel.write_intent import _slugify
    assert _slugify("write gate test") == "write-gate-test"


def test_slugify_strips_punctuation():
    from ariel.write_intent import _slugify
    assert _slugify("hello, world!") == "hello-world"


def test_slugify_empty_falls_back():
    from ariel.write_intent import _slugify
    assert _slugify("!@#$") == "note"


# --- Capture flow detection ---

def _parser():
    return WriteIntentParser()

def test_detect_capture_flow_reference_pronoun():
    """'capture that' — generic capture with pronoun, triggers flow."""
    result = _parser().detect_capture_flow("capture that")
    assert result is not None
    assert result == "that"


def test_detect_capture_flow_left_leadin():
    """'please capture that' — left library word + capture + pronoun."""
    result = _parser().detect_capture_flow("please capture that")
    assert result is not None
    assert result == "that"


def test_detect_capture_flow_multiword_leadin():
    """'for now capture that' — multi-word leadin."""
    result = _parser().detect_capture_flow("for now capture that")
    assert result is not None
    assert result == "that"


def test_detect_capture_flow_meaningful_content():
    """'capture these notes about X' — generic capture with content."""
    result = _parser().detect_capture_flow("capture these notes about conversational flow")
    assert result is not None
    assert "these notes about conversational flow" in result


def test_detect_capture_flow_excludes_insight():
    """'capture this as an insight' — already handled by parse()."""
    result = _parser().detect_capture_flow("capture this as an insight")
    assert result is None


def test_detect_capture_flow_excludes_task():
    """'create a task for X' — already handled by parse()."""
    result = _parser().detect_capture_flow("create a task for write gate")
    assert result is None


def test_detect_capture_flow_excludes_inbox_colon():
    """'add to inbox: content' — colon form, handled by parse()."""
    result = _parser().detect_capture_flow("Add this to my inbox: 'test entry'")
    assert result is None


def test_detect_capture_flow_no_match():
    """Non-capture messages return None."""
    assert _parser().detect_capture_flow("What tasks do I have?") is None
    assert _parser().detect_capture_flow("hello") is None
    assert _parser().detect_capture_flow("yes") is None


def test_is_reference_word():
    parser = _parser()
    assert parser._is_reference_word("this")
    assert parser._is_reference_word("that")
    assert parser._is_reference_word("it")
    assert parser._is_reference_word("THIS")
    assert not parser._is_reference_word("these notes")
    assert not parser._is_reference_word("hello")


def test_inbox_before_reference_pronoun_returns_none():
    """parse('capture that to inbox') returns None — pronoun excluded, capture flow handles it."""
    result = _parser().parse("capture that to inbox")
    assert result is None


def test_inbox_before_meaningful_content_returns_write():
    """parse('capture these notes to inbox') returns WriteIntent — not a pronoun."""
    result = _parser().parse("capture these notes to inbox")
    assert result is not None
    assert result.tool == "append_to_file"
    assert result.args["file_path"] == "Inbox.md"
    assert "these notes" in result.args["content"]


def test_inbox_before_pronoun_routes_to_capture_flow():
    """detect_capture_flow('capture that to inbox') returns content — pronoun needs disambiguation."""
    result = _parser().detect_capture_flow("capture that to inbox")
    assert result is not None
    assert result == "that"


def test_inbox_before_meaningful_content_excluded_from_flow():
    """detect_capture_flow('capture these notes to inbox') returns None — has real content."""
    result = _parser().detect_capture_flow("capture these notes to inbox")
    assert result is None
