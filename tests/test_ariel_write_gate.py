import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
import orchestrator as orch_module
from ariel.persona import ArielOrchestrator


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "LOCAL_MIND_FOUNDATION.md").write_text("# LMF\n")
    (v / "Inbox.md").write_text("# Inbox\n\n")
    (v / "Tasks").mkdir()
    (v / "Insights").mkdir()
    (v / "Projects").mkdir()
    return v


@pytest.fixture
def ariel(vault):
    orch_module.OLLAMA_URL     = "http://localhost:11434/api/chat"
    orch_module.OLLAMA_MODEL   = "qwen2.5:1.5b"
    orch_module.OLLAMA_TIMEOUT = 30
    orch_module.OLLAMA_NUM_CTX = 8192

    with patch("ariel.persona.ArielMemory") as mock_mem_cls, \
         patch("ariel.persona.SessionYAMLHandler") as mock_sess_cls:
        mem = MagicMock()
        mem.get_pending_insight.return_value = (None, None)
        mem.needs_summarization.return_value = False
        mock_mem_cls.return_value = mem

        sess = MagicMock()
        sess.load_session_context.return_value = {}
        sess.format_session_prompt.return_value = ""
        mock_sess_cls.return_value = sess

        orch = ArielOrchestrator(str(vault), test_mode=True)

    # Prevent real LLM calls in tests that reach Think
    orch._call_backend = MagicMock(return_value="Thought: No external lookup needed.")
    orch._call_backend_with_history = MagicMock(return_value="Here is your answer.")
    return orch


# --- Pending write: confirmation ---

def test_pending_write_confirmation_dispatches(ariel, vault):
    ariel.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "hello world"},
        "proposal": "Ariel wants to append to `Inbox.md`:\n\nhello world\n\nConfirm? (yes/no)",
    }
    reply = ariel.chat("yes")
    assert "✓ Written to" in reply
    assert ariel.pending_write is None
    assert "hello world" in (vault / "Inbox.md").read_text()


def test_pending_write_confirmation_clears_think(ariel):
    """Confirm turn must not reach Think."""
    ariel.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "x"},
        "proposal": "...",
    }
    ariel.chat("yes")
    ariel._call_backend.assert_not_called()


def test_pending_write_rejection_cancels(ariel, vault):
    inbox_before = (vault / "Inbox.md").read_text()
    ariel.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "should not appear"},
        "proposal": "...",
    }
    reply = ariel.chat("no")
    assert "won't" in reply.lower() or "okay" in reply.lower()
    assert ariel.pending_write is None
    assert (vault / "Inbox.md").read_text() == inbox_before


def test_pending_write_unrelated_cancels(ariel, vault):
    inbox_before = (vault / "Inbox.md").read_text()
    ariel.pending_write = {
        "name": "append_to_file",
        "args": {"file_path": "Inbox.md", "content": "should not appear"},
        "proposal": "...",
    }
    ariel.chat("actually never mind")
    assert ariel.pending_write is None
    assert (vault / "Inbox.md").read_text() == inbox_before


# --- Write intent detection ---

def test_inbox_intent_sets_pending_write(ariel):
    reply = ariel.chat("Add 'test entry' to my inbox")
    assert "Ariel wants to" in reply
    assert "Confirm? (yes/no)" in reply
    assert ariel.pending_write is not None
    assert ariel.pending_write["name"] == "append_to_file"
    assert ariel.pending_write["args"]["file_path"] == "Inbox.md"
    ariel._call_backend.assert_not_called()


def test_create_task_intent_sets_pending_write(ariel):
    reply = ariel.chat("Create a task for write gate verification")
    assert "Ariel wants to" in reply
    assert "Confirm? (yes/no)" in reply
    assert ariel.pending_write is not None
    assert ariel.pending_write["name"] == "create_file"
    assert ariel.pending_write["args"]["file_path"].startswith("Tasks/")
    ariel._call_backend.assert_not_called()


def test_create_insight_intent_sets_pending_write(ariel):
    reply = ariel.chat("Create an insight about write gate reliability")
    assert "Ariel wants to" in reply
    assert "Confirm? (yes/no)" in reply
    assert ariel.pending_write is not None
    assert ariel.pending_write["name"] == "create_file"
    assert ariel.pending_write["args"]["file_path"].startswith("Insights/")
    ariel._call_backend.assert_not_called()


def test_no_write_intent_reaches_think(ariel):
    reply = ariel.chat("What tasks do I have today?")
    assert ariel.pending_write is None
    ariel._call_backend.assert_called_once()


# --- Two-turn flow ---

def test_two_turn_confirmed_write(ariel, vault):
    # Turn 1 — proposal
    reply1 = ariel.chat("Add 'Gate test confirmed' to my inbox")
    assert "Confirm? (yes/no)" in reply1
    assert ariel.pending_write is not None

    # Turn 2 — confirm (no reset between turns)
    reply2 = ariel.chat("yes")
    assert "✓ Written to" in reply2
    assert ariel.pending_write is None
    assert "Gate test confirmed" in (vault / "Inbox.md").read_text()


def test_two_turn_rejected_write(ariel, vault):
    inbox_before = (vault / "Inbox.md").read_text()

    # Turn 1 — proposal
    ariel.chat("Add 'SHOULD NOT APPEAR' to my inbox")

    # Turn 2 — reject
    reply2 = ariel.chat("no")
    assert "won't" in reply2.lower() or "okay" in reply2.lower()
    assert (vault / "Inbox.md").read_text() == inbox_before


# --- Capture flow integration ---

def test_capture_flow_pronoun_triggers_state(ariel):
    """'capture that' triggers capture flow state, returns prompt, no pending_write."""
    reply = ariel.chat("capture that")
    assert reply == "Task, project, or inbox?"
    assert ariel._capture_pending is not None
    assert ariel._capture_pending["content"] == "that"
    assert ariel._capture_pending["target"] is None
    # No pending write — capture flow doesn't set one
    assert ariel.pending_write is None


def test_capture_flow_left_leadin_triggers_state(ariel):
    """'please capture that' with left library word."""
    reply = ariel.chat("please capture that")
    assert reply == "Task, project, or inbox?"
    assert ariel._capture_pending is not None
    assert ariel.pending_write is None


def test_capture_flow_meaningful_content_triggers_state(ariel):
    """'capture these notes' — content present, still sets capture state."""
    reply = ariel.chat("capture these notes about conversational flow")
    assert reply == "Task, project, or inbox?"
    assert ariel._capture_pending is not None
    assert ariel._capture_pending["content"] == "these notes about conversational flow"
    assert ariel.pending_write is None


def test_capture_flow_state_second_turn_inbox(ariel):
    """Capture flow second turn: user says 'inbox' → writes with verification."""
    ariel.chat("capture these notes")
    assert ariel._capture_pending is not None
    reply2 = ariel.chat("inbox")
    assert "✓ Appended to Inbox.md" in reply2
    assert ariel._capture_pending is None


def test_capture_flow_does_not_block_write_intent(ariel):
    """Specific write intents still work — capture flow only catches generic patterns."""
    reply = ariel.chat("Add 'hello' to my inbox")
    assert "Ariel wants to" in reply
    assert ariel.pending_write is not None
    ariel._call_backend_with_history.assert_not_called()


def test_capture_flow_does_not_block_insight(ariel):
    """'capture this as an insight' — still routes to write gate."""
    reply = ariel.chat("Capture this as an insight")
    assert "Ariel wants to" in reply
    assert ariel.pending_write is not None
    ariel._call_backend_with_history.assert_not_called()


def test_capture_flow_inbox_pronoun_triggers_state(ariel):
    """'capture that to inbox' — pronoun with inbox target, sets capture state."""
    reply = ariel.chat("capture that to inbox")
    assert reply == "Task, project, or inbox?"
    assert ariel._capture_pending is not None
    assert ariel._capture_pending["content"] == "that"
    assert ariel.pending_write is None
