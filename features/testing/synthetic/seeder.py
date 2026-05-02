#!/usr/bin/env python3
"""Synthetic vault seeder — generates a test vault from seed_spec.yaml."""

import re
import yaml
from pathlib import Path


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _write_note(path: Path, frontmatter: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
    path.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def seed_vault(spec_path: Path, vault_path: Path) -> None:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    for project in spec.get("projects", []):
        slug = _slugify(project["name"])
        _write_note(
            vault_path / "Projects" / f"{slug}.md",
            {
                "title": project["name"],
                "type": "project",
                "status": project["status"],
                "priority": project["priority"],
                "created": "2026-01-01",
                "brief": project["brief"],
                "tags": ["project", project["status"]],
            },
        )

    for task in spec.get("tasks", []):
        slug = _slugify(task["title"])
        fm = {
            "title": task["title"],
            "type": "task",
            "status": task["status"],
            "project": f"[[{task['project']}]]",
            "created": "2026-01-01",
            "context": task["context"],
            "duration": task["duration"],
            "tags": ["task", task["status"]],
        }
        if "goal_date" in task:
            fm["goal_date"] = task["goal_date"]
        if "completed" in task:
            fm["completed"] = task["completed"]
        _write_note(vault_path / "Tasks" / f"{slug}.md", fm)

    for insight in spec.get("insights", []):
        slug = _slugify(insight["title"])
        _write_note(
            vault_path / "Insights" / f"{slug}.md",
            {
                "title": insight["title"],
                "type": "insight",
                "created": "2026-01-01",
                "tags": ["insight"],
            },
            body=insight["body"],
        )

    for note in spec.get("daily_notes", []):
        _write_note(
            vault_path / "Daily" / f"{note['date']}.md",
            {"date": note["date"], "type": "daily"},
            body=note["body"],
        )


if __name__ == "__main__":
    import sys
    spec = Path(__file__).parent / "seed_spec.yaml"
    out = Path(__file__).parent / "vault"
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    print(f"Seeding vault at {out}")
    seed_vault(spec, out)
    print(f"Done — {len(list(out.rglob('*.md')))} notes written")
