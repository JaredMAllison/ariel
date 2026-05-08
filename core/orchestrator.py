"""
orchestrator.py — Ariel conversation orchestrator.

HTTP server that sits between the user and Ollama.
Each turn: parses skill triggers, assembles context, calls Ollama, returns response.

Usage:
  python3 orchestrator.py [vault_path]

Endpoints:
  GET  /        → serves ui/ariel.html (browser UI)
  POST /chat   { "message": "..." }  → { "response": "..." }
  POST /reset                        → resets conversation history
  GET  /health                       → { "status": "ok" }
  GET  /status                       → model state, prompt stats, inference status
"""

import json
import re
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
import yaml

# kb_core lives in the MCP server directory — shared library per ADR-003
_KB_CORE_DIR = Path.home() / ".local/share/obsidian-mcp"
_KB_VENV_SITE = _KB_CORE_DIR / ".venv/lib/python3.12/site-packages"
for _p in (str(_KB_CORE_DIR), str(_KB_VENV_SITE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from kb_core import KnowledgeBase
    KB_AVAILABLE = True
except ImportError as _e:
    print(f"[orchestrator] Warning: kb_core unavailable — {_e}. Tools disabled.", file=sys.stderr)
    KB_AVAILABLE = False

from build_prompt import build_prompt

# Write tool names — used for tool gating in init mode
_WRITE_TOOLS = {"append_to_file", "replace_lines", "create_file", "insert_after_heading"}

_CONFIRMATION_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "go ahead", "confirm", "do it"}

INIT_STATE_PATH = "operator/.init_state.json"
DEPLOY_CONFIG_PATH = "operator/deploy.yaml"


def is_confirmation(message: str) -> bool:
    return message.strip().lower().rstrip(".,!?") in _CONFIRMATION_YES


def load_deploy_config(vault: Path) -> dict:
    """Read deploy.yaml from vault operator/ dir, with all-defaults fallback."""
    default = {"instance_name": "LMF", "trust_profile": "personal", "onboarding_mode": "guided"}
    path = vault / DEPLOY_CONFIG_PATH
    if path.exists():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {**default, **cfg}
    return default


def load_config(config_path: Path | None = None) -> dict:
    """Load operator config from YAML. Calls sys.exit if the file is missing."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "operator" / "config.yaml"
    if not config_path.exists():
        sys.exit("[orchestrator] No operator config found — run python3 init.py to set up.")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


# Sentinel values — overwritten by _init_config() at startup, never at import time
OLLAMA_URL        = ""
OLLAMA_PS_URL     = ""
OLLAMA_MODEL      = ""
OLLAMA_TIMEOUT    = 300
OLLAMA_NUM_CTX    = 8192
MAX_HISTORY_TURNS = 10    # max user+assistant pairs kept; oldest dropped when exceeded
MAX_TOOL_LOOPS    = 5     # max tool call rounds per turn before forcing a text response
HOST              = "0.0.0.0"
PORT              = 8742
SKILLS_DIR        = "System/Skills"
UI_FILE           = Path(__file__).parent.parent / "features" / "ui" / "ariel.html"


def _init_config(config_path: Path | None = None) -> None:
    """Read operator config and populate runtime globals. Called only inside run()."""
    global OLLAMA_URL, OLLAMA_PS_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_NUM_CTX, PORT
    cfg = load_config(config_path)
    OLLAMA_URL     = cfg["ollama_url"]
    OLLAMA_PS_URL  = cfg["ollama_url"].replace("/api/chat", "/api/ps")
    OLLAMA_MODEL   = cfg["model"]
    OLLAMA_TIMEOUT = int(cfg["timeout_s"])
    OLLAMA_NUM_CTX = int(cfg["num_ctx"])
    PORT           = int(cfg["port"])


def load_skill(vault: Path, name: str) -> str | None:
    """Look up a skill file by name. Returns content or None."""
    candidates = [
        vault / SKILLS_DIR / f"{name}.md",
        vault / SKILLS_DIR / name / f"{name}.md",
        vault / SKILLS_DIR / name / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None


def parse_skill_trigger(message: str) -> str | None:
    """Return skill name if message starts with /skill-name, else None."""
    match = re.match(r"^/([a-z0-9_-]+)", message.strip())
    return match.group(1) if match else None


class Orchestrator:
    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        self.is_init_mode = self._is_first_run()
        self.history: list[dict] = []
        self.inference_in_progress: bool = False
        self.last_response_ms: int | None = None

        if self.is_init_mode:
            self._enter_init_mode()
        else:
            self.system_prompt, self.prompt_stats = build_prompt(vault_path)
            self.kb = KnowledgeBase(self.vault) if KB_AVAILABLE else None
            tools_config = Path(__file__).parent / "tools.config.yaml"
            self.tools = self._build_tools(tools_config) if self.kb else []

        print(f"[orchestrator] Vault: {self.vault}")
        print(f"[orchestrator] System prompt: {len(self.system_prompt)} chars")
        if self.is_init_mode:
            print(f"[orchestrator] Mode: init (first run)")
        elif self.tools:
            print(f"[orchestrator] Tools: {[t['function']['name'] for t in self.tools]}")
        else:
            print("[orchestrator] Tools: none (Phase 1 mode)")
        print(f"[orchestrator] Listening on {HOST}:{PORT}")

    def _is_first_run(self) -> bool:
        return not (self.vault / "LOCAL_MIND_FOUNDATION.md").exists()

    def _enter_init_mode(self):
        deploy_cfg = load_deploy_config(self.vault)
        init_prompt_path = Path(__file__).parent / "prompts" / "init.md"
        template = init_prompt_path.read_text(encoding="utf-8")

        init_state = self._load_init_state()
        if init_state.get("phase") != "interview":
            resume_context = (
                "The operator partially completed setup. "
                "Do not repeat questions already answered. "
                "Resume from where they left off."
            )
        else:
            resume_context = ""

        self.system_prompt = template.format(
            instance_name=deploy_cfg["instance_name"],
            trust_profile=deploy_cfg["trust_profile"],
            onboarding_mode=deploy_cfg["onboarding_mode"],
            resume_context=resume_context,
        )
        self.prompt_stats = {"memory_files_loaded": 0, "skills_in_index": 0}
        self.kb = None
        self.tools = []
        self.init_state = init_state
        self.init_handoff = None

    def reset(self):
        self.history = []
        if self.is_init_mode:
            self._clear_init_state()

    # --- Init state management --------------------------------------------------

    def _load_init_state(self) -> dict:
        path = self.vault / INIT_STATE_PATH
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"phase": "interview", "answered_questions": [], "profile_draft": {}}

    def _save_init_state(self):
        path = self.vault / INIT_STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.init_state, indent=2), encoding="utf-8")

    def _clear_init_state(self):
        path = self.vault / INIT_STATE_PATH
        if path.exists():
            path.unlink()

    # --- Init → Ariel handoff ---------------------------------------------------

    def _extract_profile(self, reply: str) -> dict:
        """Extract YAML frontmatter from between --- markers after [INIT_COMPLETE]."""
        after_signal = reply.split("[INIT_COMPLETE]", 1)[-1]
        match = re.search(r'^---\s*\n(.*?)\n---', after_signal, re.DOTALL | re.MULTILINE)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _build_foundation_md(self, profile: dict) -> str:
        fields = {
            "title": "LOCAL_MIND_FOUNDATION",
            "type": "profile",
            "instance_name": profile.get("instance_name", "LMF"),
            "trust_profile": profile.get("trust_profile", "personal"),
            "init_date": datetime.now().strftime("%Y-%m-%d"),
        }
        for key in ("operator_name", "primary_need", "attention_profile", "work_separate", "household_size"):
            if key in profile and profile[key]:
                fields[key] = profile[key]

        lines = ["---"]
        for k, v in fields.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _seed_vault_directories(self):
        for d in ["Tasks", "Projects", "Daily"]:
            (self.vault / d).mkdir(parents=True, exist_ok=True)
        inbox = self.vault / "Inbox.md"
        if not inbox.exists():
            inbox.write_text("", encoding="utf-8")

    def _complete_initiation(self) -> str:
        profile = self.init_handoff["profile_draft"]

        foundation = self._build_foundation_md(profile)
        (self.vault / "LOCAL_MIND_FOUNDATION.md").write_text(foundation, encoding="utf-8")

        self._seed_vault_directories()

        self.system_prompt, self.prompt_stats = build_prompt(str(self.vault))
        self.is_init_mode = False
        self.init_handoff = None
        self.kb = KnowledgeBase(self.vault) if KB_AVAILABLE else None
        tools_config = Path(__file__).parent / "tools.config.yaml"
        self.tools = self._build_tools(tools_config) if self.kb else []
        self._clear_init_state()

        cfg = load_config()
        ai_name = cfg.get("ai_name", "your assistant")
        print(f"[orchestrator] Initiation complete — handed off to {ai_name}")
        return f"Setup complete. Let me introduce you to {ai_name}."

    # --- Tool manifest ----------------------------------------------------------

    _TOOL_PARAM_SCHEMAS: dict = {
        "search_vault": {
            "type": "object",
            "properties": {
                "query":  {"type": "string",  "description": "Search query"},
                "top_k":  {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
        "read_section": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Vault-relative path (e.g. Tasks/my-task.md)"},
                "heading":   {"type": "string", "description": "Section heading — substring match OK"},
            },
            "required": ["file_path", "heading"],
        },
        "read_lines": {
            "type": "object",
            "properties": {
                "file_path":  {"type": "string",  "description": "Vault-relative path"},
                "start_line": {"type": "integer", "description": "Start line (1-indexed)"},
                "end_line":   {"type": "integer", "description": "End line (inclusive)"},
            },
            "required": ["file_path", "start_line", "end_line"],
        },
        "outline": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Vault-relative path"},
            },
            "required": ["file_path"],
        },
        "grep_vault": {
            "type": "object",
            "properties": {
                "pattern":     {"type": "string", "description": "Regex pattern"},
                "file_filter": {"type": "string", "description": "Optional path substring (e.g. Tasks/)"},
            },
            "required": ["pattern"],
        },
        "append_to_file": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Vault-relative path"},
                "content":   {"type": "string", "description": "Content to append"},
            },
            "required": ["file_path", "content"],
        },
        "replace_lines": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string",  "description": "Vault-relative path"},
                "start_line":  {"type": "integer", "description": "Start line (1-indexed)"},
                "end_line":    {"type": "integer", "description": "End line (inclusive)"},
                "new_content": {"type": "string",  "description": "Replacement content"},
            },
            "required": ["file_path", "start_line", "end_line", "new_content"],
        },
    }

    def _build_tools(self, config_path: Path) -> list[dict]:
        if not config_path.exists():
            return []
        conf = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        result = []
        for name, tool_conf in conf.get("tools", {}).items():
            if not tool_conf.get("enabled", False):
                continue
            schema = self._TOOL_PARAM_SCHEMAS.get(name)
            if schema is None:
                continue
            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_conf.get("description", ""),
                    "parameters": schema,
                },
            })
        return result

    def _dispatch_tool(self, name: str, args: dict) -> str:
        try:
            # Init mode write gate — only append_to_file to Inbox.md
            if self.is_init_mode:
                if name == "append_to_file" and args.get("file_path") == "Inbox.md":
                    inbox = self.vault / "Inbox.md"
                    inbox.parent.mkdir(parents=True, exist_ok=True)
                    with open(inbox, "a", encoding="utf-8") as f:
                        f.write(args["content"].strip() + "\n")
                    return json.dumps({"status": "appended to Inbox.md"})
                if name in _WRITE_TOOLS:
                    return json.dumps({"error": "In init mode, write tools are limited to Inbox.md"})
                return json.dumps({"error": "Vault tools are unavailable during init mode"})

            kb = self.kb
            if name == "search_vault":
                return json.dumps(kb.search(args["query"], top_k=args.get("top_k", 5)))
            if name == "read_section":
                r = kb.read_section(args["file_path"], args["heading"])
                return json.dumps(r if r else {"error": "Section not found"})
            if name == "read_lines":
                r = kb.read_lines(args["file_path"], args["start_line"], args["end_line"])
                return json.dumps(r if r else {"error": "File not found"})
            if name == "outline":
                return json.dumps(kb.outline(args["file_path"]))
            if name == "grep_vault":
                return json.dumps(kb.grep(args["pattern"], file_filter=args.get("file_filter")))
            if name == "append_to_file":
                return json.dumps(kb.append_to_file(args["file_path"], args["content"]))
            if name == "replace_lines":
                return json.dumps(kb.replace_lines(
                    args["file_path"], args["start_line"], args["end_line"], args["new_content"]
                ))
            return json.dumps({"error": f"Unknown tool: {name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Chat -------------------------------------------------------------------

    def chat(self, user_message: str, timeout: int = OLLAMA_TIMEOUT) -> str:
        # Init mode: check for handoff confirmation
        if self.is_init_mode and self.init_handoff:
            if is_confirmation(user_message):
                return self._complete_initiation()
            else:
                self.init_handoff = None

        messages = [{"role": "system", "content": self.system_prompt}]

        # Inject skill if triggered
        skill_name = parse_skill_trigger(user_message)
        if skill_name:
            skill_content = load_skill(self.vault, skill_name)
            if skill_content:
                messages.append({
                    "role": "user",
                    "content": f"[Skill loaded: /{skill_name}]\n\n{skill_content}"
                })
                messages.append({
                    "role": "assistant",
                    "content": f"Skill /{skill_name} loaded. Following its instructions now."
                })

        messages += self.history
        messages.append({"role": "user", "content": user_message})

        self.inference_in_progress = True
        t0 = time.monotonic()
        reply = ""
        try:
            for _ in range(MAX_TOOL_LOOPS):
                payload: dict = {
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_ctx": OLLAMA_NUM_CTX},
                }
                if self.tools:
                    payload["tools"] = self.tools

                response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
                response.raise_for_status()
                msg = response.json()["message"]

                tool_calls = msg.get("tool_calls")
                if not tool_calls:
                    reply = msg.get("content", "")
                    break

                messages.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    if isinstance(fn_args, str):
                        fn_args = json.loads(fn_args)
                    messages.append({"role": "tool", "content": self._dispatch_tool(fn_name, fn_args)})
            else:
                reply = "[Tool loop limit reached — please rephrase your request.]"
        finally:
            self.inference_in_progress = False
            self.last_response_ms = int((time.monotonic() - t0) * 1000)

        # Init mode: detect completion signal
        if self.is_init_mode and "[INIT_COMPLETE]" in reply:
            profile = self._extract_profile(reply)
            self.init_handoff = {"reply": reply, "profile_draft": profile}
            self.init_state["phase"] = "handoff"
            self.init_state["profile_draft"] = profile
            self._save_init_state()

        # Only clean text exchanges go into history — tool call traces are transient
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})

        # Trim to sliding window — each turn is 2 messages (user + assistant)
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

        return reply


class Handler(BaseHTTPRequestHandler):
    orchestrator: Orchestrator = None

    def log_message(self, format, *args):
        pass  # quiet default logging

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def _serve_ui(self):
        if not UI_FILE.exists():
            self._respond(404, {"error": "ui/ariel.html not found"})
            return
        content = UI_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/ui"):
            self._serve_ui()
        elif self.path == "/health":
            self._respond(200, {"status": "ok"})
        elif self.path == "/status":
            self._handle_status()
        else:
            self._respond(404, {"error": "not found"})

    def _handle_status(self):
        orch = self.orchestrator
        ollama_ok = False
        model_loaded = False
        model_name = OLLAMA_MODEL

        try:
            ps = requests.get(OLLAMA_PS_URL, timeout=3)
            ps.raise_for_status()
            ollama_ok = True
            models = ps.json().get("models", [])
            for m in models:
                if m.get("name", "").startswith(OLLAMA_MODEL.split(":")[0]):
                    model_loaded = True
                    model_name = m.get("name", OLLAMA_MODEL)
                    break
        except Exception:
            pass

        prompt_chars = len(orch.system_prompt)
        history_turns = len(orch.history) // 2

        self._respond(200, {
            "orchestrator": "ok",
            "ollama": "ok" if ollama_ok else "unreachable",
            "model": model_name,
            "model_loaded": model_loaded,
            "num_ctx": OLLAMA_NUM_CTX,
            "system_prompt_chars": prompt_chars,
            "system_prompt_tokens_est": prompt_chars // 4,
            "init_mode": orch.is_init_mode,
            "memory_files_loaded": orch.prompt_stats["memory_files_loaded"],
            "skills_in_index": orch.prompt_stats["skills_in_index"],
            "history_turns": history_turns,
            "inference_in_progress": orch.inference_in_progress,
            "last_response_ms": orch.last_response_ms,
        })

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/chat":
            message = body.get("message", "").strip()
            if not message:
                self._respond(400, {"error": "message required"})
                return
            timeout = int(body.get("timeout_s", OLLAMA_TIMEOUT))
            try:
                reply = self.orchestrator.chat(message, timeout=timeout)
                self._respond(200, {"response": reply})
            except requests.exceptions.Timeout:
                self._respond(504, {"error": f"model did not respond within {timeout}s"})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == "/reset":
            self.orchestrator.reset()
            body = {"status": "conversation reset"}
            if self.orchestrator.is_init_mode:
                body["init_mode"] = True
                body["message"] = "Init state cleared. You can start over."
            self._respond(200, body)

        else:
            self._respond(404, {"error": "not found"})


def run(vault_path: str):
    _init_config()
    orch = Orchestrator(vault_path)
    Handler.orchestrator = orch
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[orchestrator] Stopped.")


if __name__ == "__main__":
    _cfg = load_config()
    vault = sys.argv[1] if len(sys.argv) > 1 else _cfg.get("vault_path", str(Path.home() / "Documents/Obsidian/Marlin"))
    run(vault)
