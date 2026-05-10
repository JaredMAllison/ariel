import yaml
from pathlib import Path

class SessionYAMLHandler:
    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        self.session_file = self.vault / ".session" / "current_topic.yaml"

    def load_session_context(self) -> dict:
        if self.session_file.exists():
            return yaml.safe_load(self.session_file.read_text(encoding="utf-8")) or {}
        return {}

    def format_session_prompt(self, data: dict) -> str:
        if not data:
            return ""
        lines = ["## Session Context"]
        for k, v in data.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    def update_session_context(self, updates: dict):
        current = self.load_session_context()
        current.update(updates)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
