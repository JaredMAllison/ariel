"""Unit tests for init mode — orchestrator level."""
import json
import tempfile
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from orchestrator import Orchestrator, load_deploy_config, is_confirmation


def test_init_mode_detection():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        orch = Orchestrator(str(tmpdir))
        assert orch.is_init_mode == True
        assert orch.kb is None
        assert orch.tools == []
        print("PASS: Empty vault -> init mode")
    finally:
        shutil.rmtree(tmpdir)


def test_normal_mode():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        (tmpdir / "LOCAL_MIND_FOUNDATION.md").write_text("---\ntitle: test\n---")
        orch = Orchestrator(str(tmpdir))
        assert orch.is_init_mode == False
        print("PASS: Seeded vault -> normal mode")
    finally:
        shutil.rmtree(tmpdir)


def test_deploy_yaml():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        op_dir = tmpdir / "operator"
        op_dir.mkdir()
        (op_dir / "deploy.yaml").write_text(
            "instance_name: TestInst\ntrust_profile: professional\nonboarding_mode: quick\n"
        )
        cfg = load_deploy_config(tmpdir)
        assert cfg["instance_name"] == "TestInst"
        assert cfg["trust_profile"] == "professional"
        assert cfg["onboarding_mode"] == "quick"
        print("PASS: deploy.yaml read correctly")
    finally:
        shutil.rmtree(tmpdir)


def test_deploy_defaults():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        cfg = load_deploy_config(tmpdir)
        assert cfg["instance_name"] == "LMF"
        assert cfg["trust_profile"] == "personal"
        assert cfg["onboarding_mode"] == "guided"
        print("PASS: deploy.yaml defaults")
    finally:
        shutil.rmtree(tmpdir)


def test_init_state_resume():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        op_dir = tmpdir / "operator"
        op_dir.mkdir()
        (op_dir / ".init_state.json").write_text(
            json.dumps({"phase": "handoff", "answered_questions": ["name"], "profile_draft": {"operator_name": "Alex"}})
        )
        orch = Orchestrator(str(tmpdir))
        assert orch.init_state["phase"] == "handoff"
        assert orch.init_state["profile_draft"]["operator_name"] == "Alex"
        assert "partially completed" in orch.system_prompt
        print("PASS: Resume context injected into system prompt")
    finally:
        shutil.rmtree(tmpdir)


def test_reset_clears_init_state():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        orch = Orchestrator(str(tmpdir))
        orch._save_init_state()
        assert (tmpdir / "operator" / ".init_state.json").exists()
        orch.reset()
        assert not (tmpdir / "operator" / ".init_state.json").exists()
        print("PASS: reset() clears init state in init mode")
    finally:
        shutil.rmtree(tmpdir)


def test_is_confirmation():
    assert is_confirmation("yes") == True
    assert is_confirmation("y") == True
    assert is_confirmation("sure") == True
    assert is_confirmation("no") == False
    assert is_confirmation("maybe") == False
    print("PASS: is_confirmation()")


def test_extract_profile():
    orch = Orchestrator(str(Path(tempfile.mkdtemp())))
    orch.is_init_mode = True
    reply = """Hello! Let me ask you a few questions.

[INIT_COMPLETE]

---
operator_name: Alex
primary_need: task management
attention_profile: short
work_separate: yes
household_size: "2"
trust_profile: personal
instance_name: My LMF
init_date: 2026-05-07
---

Here's what I've learned so far...
"""
    profile = orch._extract_profile(reply)
    assert profile["operator_name"] == "Alex"
    assert profile["primary_need"] == "task management"
    assert profile["attention_profile"] == "short"
    assert profile["trust_profile"] == "personal"
    print("PASS: _extract_profile()")
    return orch, profile


def test_build_foundation_md():
    orch = Orchestrator(str(Path(tempfile.mkdtemp())))
    profile = {
        "operator_name": "Alex",
        "primary_need": "task management",
        "attention_profile": "short",
        "work_separate": "yes",
        "household_size": "2",
        "trust_profile": "personal",
        "instance_name": "My LMF",
    }
    md = orch._build_foundation_md(profile)
    assert "LOCAL_MIND_FOUNDATION" in md
    assert "operator_name: Alex" in md
    assert "init_date:" in md
    print(f"PASS: _build_foundation_md()\n{md}")


if __name__ == "__main__":
    test_is_confirmation()
    test_deploy_yaml()
    test_deploy_defaults()
    test_init_mode_detection()
    test_normal_mode()
    test_init_state_resume()
    test_reset_clears_init_state()
    test_extract_profile()
    test_build_foundation_md()
    print("\nAll tests passed!")
