import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "features" / "testing" / "synthetic"))

from seeder import seed_vault


@pytest.fixture
def spec_path():
    """Path to the seed_spec.yaml file."""
    return Path(__file__).parent.parent / "features" / "testing" / "synthetic" / "seed_spec.yaml"


def test_seeder_creates_task_files(spec_path, tmp_path):
    seed_vault(spec_path, tmp_path)
    task_files = list((tmp_path / "Tasks").glob("*.md"))
    assert len(task_files) == 4


def test_task_file_has_correct_frontmatter(spec_path, tmp_path):
    seed_vault(spec_path, tmp_path)
    task_file = tmp_path / "Tasks" / "review-quarterly-budget.md"
    assert task_file.exists()
    content = task_file.read_text()
    assert "status: queued" in content
    assert "project: '[[Alpha Initiative]]'" in content
    assert "type: task" in content


def test_seeder_creates_project_files(spec_path, tmp_path):
    seed_vault(spec_path, tmp_path)
    project_files = list((tmp_path / "Projects").glob("*.md"))
    assert len(project_files) == 2


def test_seeder_creates_insight_files(spec_path, tmp_path):
    seed_vault(spec_path, tmp_path)
    insight_files = list((tmp_path / "Insights").glob("*.md"))
    assert len(insight_files) == 2


def test_seeder_is_deterministic(spec_path, tmp_path):
    vault_a = tmp_path / "a"
    vault_b = tmp_path / "b"
    seed_vault(spec_path, vault_a)
    seed_vault(spec_path, vault_b)
    files_a = sorted(p.read_text() for p in vault_a.rglob("*.md"))
    files_b = sorted(p.read_text() for p in vault_b.rglob("*.md"))
    assert files_a == files_b
