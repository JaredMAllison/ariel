import json
import logging
from pathlib import Path
from .guard import ArielGuard
from .memory import ArielMemory
from .thinking import ArielThinking
from .session_yaml import SessionYAMLHandler
from lmf.orchestrator import Orchestrator

class ArielOrchestrator(Orchestrator):
    """Ariel‑specific orchestrator implementing Think‑Read‑Respond.
    Integrates Knowledge Loom for targeted vault retrieval.
    """
    def __init__(self, vault_path: str, test_mode: bool = False, tools_config_path=None):
        super().__init__(vault_path, test_mode, tools_config_path=tools_config_path)
        self.guard = ArielGuard()
        self.memory = ArielMemory(vault_path, self.loom_url)
        self.thinker = ArielThinking()
        self.session_yaml = SessionYAMLHandler(vault_path)
        self.ai_name = "Ariel"

        # Prepend session context (if any) to the system prompt
        if not self.is_init_mode:
            session_context = self.session_yaml.load_session_context()
            session_prompt = self.session_yaml.format_session_prompt(session_context)
            if session_prompt:
                self.system_prompt = f"{session_prompt}\n\n{self.system_prompt}"

    def chat(self, user_message: str, timeout: int = 300) -> str:
        # === Pending Insight Confirmation ===
        pending, updates = self.memory.get_pending_insight()
        if pending:
            lowered = user_message.strip().lower()
            if lowered in ("yes", "y", "sure", "ok", "affirmative"):
                # Build note path & return marker for the outer assistant to write
                note_title_line = pending['note_content'].split('\n')[1]
                title = note_title_line.split(':', 1)[1].strip().strip('"')
                safe_fname = title.replace(' ', '_') + ".md"
                note_path = self.vault / "Insights" / safe_fname
                note_path.parent.mkdir(parents=True, exist_ok=True)
                return f"__CREATE_INSIGHT__||{note_path}||{pending['note_content']}"
            else:
                # Decline
                self.memory.pending_insight = None
                self.memory.pending_session_updates = None
                return "✅ Insight creation declined."

        # === 1. Sanitize & Warn ===
        sanitized_input, warning_detected = self.guard.sanitize(user_message)

        # === 2. Think (internal monologue) ===
        thinking_prompt = f"""You are Ariel's internal reasoning module.
        Analyze the user's message and identify what knowledge is missing to provide a grounded, neuro‑informed response.
        If you need to look up information in the vault, specify the exact loom tool calls you would make.
        Output your reasoning in this format:

        Thought: [your reasoning about what information is needed]
        Tool: loom_tool_name("arguments")
        (You can specify multiple Tool lines if needed.)

        If no external knowledge is needed, just output:
        Thought: No external lookup needed.

        User message: {sanitized_input}"""
        thinking_response = super().chat(thinking_prompt, timeout)
        thought, tool_calls = self.thinker.extract_thoughts_and_tools(thinking_response)

        # === 3. Read (Loom integration) ===
        vault_context_parts = []
        if tool_calls:
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                try:
                    tool_args_dict = {}
                    if tool_name == "loom_search" and len(tool_args) >= 1:
                        tool_args_dict = {"query": tool_args[0], "top_k": int(tool_args[1]) if len(tool_args) > 1 and tool_args[1].isdigit() else 5}
                    elif tool_name == "loom_read_section" and len(tool_args) >= 2:
                        tool_args_dict = {"file_path": tool_args[0], "heading": tool_args[1]}
                    elif tool_name == "loom_read_lines" and len(tool_args) >= 3:
                        tool_args_dict = {"file_path": tool_args[0], "start_line": int(tool_args[1]), "end_line": int(tool_args[2])}
                    elif tool_name == "loom_outline" and len(tool_args) >= 1:
                        tool_args_dict = {"file_path": tool_args[0]}
                    elif tool_name == "loom_grep" and len(tool_args) >= 1:
                        tool_args_dict = {"pattern": tool_args[0], "file_filter": tool_args[1] if len(tool_args) > 1 else None}
                    elif tool_name == "loom_list_files":
                        tool_args_dict = {}
                    result_json = self._dispatch_tool(tool_name, tool_args_dict)
                    result = json.loads(result_json)
                    # Extract useful content based on shape
                    if isinstance(result, dict):
                        if "results" in result and isinstance(result["results"], list):
                            for res in result["results"]:
                                if isinstance(res, dict) and "content" in res:
                                    file_info = res.get('file', 'unknown')
                                    heading = res.get('heading', '')
                                    content = res['content']
                                    prefix = f"Source: {file_info}"
                                    if heading:
                                        prefix += f" - {heading}"
                                    vault_context_parts.append(f"{prefix}\n{content}")
                        elif "content" in result:
                            file_info = result.get('file', 'unknown')
                            heading = result.get('heading', '')
                            content = result['content']
                            prefix = f"Source: {file_info}"
                            if heading:
                                prefix += f" - {heading}"
                            vault_context_parts.append(f"{prefix}\n{content}")
                        elif "error" in result:
                            vault_context_parts.append(f"[Error: {result['error']}]")
                    else:
                        vault_context_parts.append(str(result))
                except Exception as e:
                    logging.error(f"Tool {tool_name} failed: {e}")
                    vault_context_parts.append(f"[Error calling {tool_name}: {e}]")
        vault_context = "\n\n---\n\n".join(vault_context_parts) if vault_context_parts else ""

        # === 4. Respond (grounded) ===
        grounded_input = f"{sanitized_input}\n\n[Relevant Vault Context]:\n{vault_context}" if vault_context else sanitized_input
        response = super().chat(grounded_input, timeout)

        # === 5. Post‑process warnings ===
        if warning_detected:
            response = f"⚠️ **Potential Injection Detected**\n\n{response}"

        # === 6. Summarization / Ask & Confirm ===
        if self.memory.needs_summarization(self.history):
            if not self.memory.pending_insight:
                recent = self.history[-self.memory.get_pruning_index(self.history):]
                user_msgs = [m.get('content','') for m in recent if m.get('role')=='user']
                snippet = "\n---\n".join(user_msgs)
                summarization_prompt = f"""You are summarizing a conversation for the operator's executive brain. Extract the *key insights*, patterns, and actionable takeaways from the following user messages. Limit the summary to ~150 words and present it as a concise bullet list.

User messages:\n{snippet}\n"""
                insight_text = super().chat(summarization_prompt, timeout)
                self.memory.set_pending_insight(insight_text.strip(), session_topic="General")
                return "I have extracted a key insight from our recent conversation. Would you like me to create an Insight note for it? (yes/no)"
            else:
                # Pending insight already exists – wait for user confirmation
                return response

        return response
