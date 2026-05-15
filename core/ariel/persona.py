import json
import logging
import os
from pathlib import Path
from .guard import ArielGuard
from .memory import ArielMemory
from .thinking import ArielThinking
from .session_yaml import SessionYAMLHandler
from .write_intent import WriteIntentParser
from kb_core import KnowledgeBase
from lmf.orchestrator import Orchestrator, is_confirmation, _format_proposal

class ArielOrchestrator(Orchestrator):
    """Ariel‑specific orchestrator implementing Think‑Read‑Respond.
    Uses kb_core for vault search (replaces Knowledge Loom).
    """
    def __init__(self, vault_path: str, test_mode: bool = False, tools_config_path=None):
        super().__init__(vault_path, test_mode, tools_config_path=tools_config_path)
        self.guard = ArielGuard()
        self.memory = ArielMemory(vault_path, self.loom_url)
        self.thinker = ArielThinking()
        self.session_yaml = SessionYAMLHandler(vault_path)
        self.ai_name = "Ariel"

        # Initialize kb_core for vault search (replaces Loom dependency)
        self.kb = KnowledgeBase(Path(vault_path))
        self._write_parser = WriteIntentParser()

        # Groq toggle — prefer Groq for Think/Respond if available
        # Default: on (Groq preferred). Off = use priority-ordered backends (Ollama first)
        raw = os.environ.get("PREFER_GROQ_FOR_THINK", "true")
        self.prefer_groq_for_think = raw.strip().lower() in ("true", "1", "yes")
        logging.info(f"[Ariel] kb_core initialized — {len(self.kb.chunks)} chunks indexed")
        logging.info(f"[Ariel] prefer_groq_for_think={self.prefer_groq_for_think}")

        # Prepend session context (if any) to the system prompt
        if not self.is_init_mode:
            session_context = self.session_yaml.load_session_context()
            session_prompt = self.session_yaml.format_session_prompt(session_context)
            if session_prompt:
                self.system_prompt = f"{session_prompt}\n\n{self.system_prompt}"

    def _call_backend(self, prompt: str, timeout: int = 300, prefer_backend: str | None = None) -> str:
        """Single backend call — does NOT append to history."""
        from lmf.orchestrator import BACKENDS
        from lmf.backends import BackendError, RateLimitError
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}]

        ordered = BACKENDS[:]
        if prefer_backend:
            ordered = sorted(BACKENDS, key=lambda x: (0 if x[1].name == prefer_backend else 1, x[0]))

        for _, backend in ordered:
            if not backend.is_available:
                continue
            try:
                result = backend.chat(messages, tools=None, timeout=timeout)
                return result.content
            except RateLimitError as e:
                logging.warning(f"[Ariel] {backend.name} rate limited: {e}")
                continue
            except BackendError as e:
                logging.warning(f"[Ariel] {backend.name} error: {e}")
                continue
        logging.warning("[Ariel] All backends exhausted")
        return "[All backends exhausted]"

    def _call_backend_with_history(self, user_message: str, timeout: int = 300, prefer_backend: str | None = None) -> str:
        """Backend call with conversation history — does NOT auto-append to history."""
        from lmf.orchestrator import BACKENDS
        from lmf.backends import BackendError, RateLimitError
        messages = [{"role": "system", "content": self.system_prompt}]
        messages += self.history
        messages.append({"role": "user", "content": user_message})
        ordered = BACKENDS[:]
        if prefer_backend:
            ordered = sorted(BACKENDS, key=lambda x: (0 if x[1].name == prefer_backend else 1, x[0]))
        for _, backend in ordered:
            if not backend.is_available:
                continue
            try:
                result = backend.chat(messages, tools=None, timeout=timeout)
                return result.content
            except RateLimitError as e:
                logging.warning(f"[Ariel] {backend.name} rate limited: {e}")
                continue
            except BackendError as e:
                logging.warning(f"[Ariel] {backend.name} error: {e}")
                continue
        logging.warning("[Ariel] All backends exhausted")
        return "[All backends exhausted]"

    def _is_lightweight_turn(self, message: str) -> bool:
        """True if message is short enough that an insight interrupt is non-disruptive."""
        return len(message.split()) < 15 and not any(
            kw in message.lower() for kw in ["build", "write", "create", "fix", "update", "add", "run"]
        )

    def chat(self, user_message: str, timeout: int = 300) -> str:
        # === Pending Insight Confirmation ===
        pending, updates = self.memory.get_pending_insight()
        if pending:
            lowered = user_message.strip().lower()
            if lowered in ("yes", "y", "sure", "ok", "affirmative"):
                note_title_line = pending['note_content'].split('\n')[1]
                title = note_title_line.split(':', 1)[1].strip().strip('"')
                safe_fname = title.replace(' ', '_') + ".md"
                note_path = self.vault / "Insights" / safe_fname
                note_path.parent.mkdir(parents=True, exist_ok=True)
                return f"__CREATE_INSIGHT__||{note_path}||{pending['note_content']}"
            else:
                self.memory.pending_insight = None
                self.memory.pending_session_updates = None
                return "✅ Insight creation declined."

        # === Pending Write Confirmation ===
        if self.pending_write:
            if is_confirmation(user_message):
                name = self.pending_write["name"]
                args = self.pending_write["args"]
                self.pending_write = None
                raw = self._dispatch_tool(name, args)
                if self.verbose_writes or self.test_mode:
                    return f"Done. ✓ Written to `{args.get('file_path', 'file')}`"
                return f"Done. {raw}"
            else:
                self.pending_write = None
                return "Okay, I won't make that change."

        # === Write Intent Detection ===
        intent = self._write_parser.parse(user_message)
        if intent:
            proposal = _format_proposal(intent.tool, intent.args)
            self.pending_write = {"name": intent.tool, "args": intent.args, "proposal": proposal}
            return proposal

        # === 1. Sanitize & Warn ===
        sanitized_input, warning_detected = self.guard.sanitize(user_message)

        # === 2. Think (internal monologue) — Groq preferred (toggle via PREFER_GROQ_FOR_THINK) ===
        thinking_prompt = f"""You are Ariel's internal reasoning module.
Analyze the user's message and identify what knowledge is missing to provide a grounded, neuro‑informed response.
If you need to look up information in the vault, specify the tool calls you would make using these exact tool names:

  search_vault("query", "top_k")     — full-text search across vault notes
  read_section("path", "heading")    — read a named section from a specific file
  read_lines("path", start, end)     — read a line range from a file
  outline("path")                    — get heading structure of a file
  grep_vault("pattern")              — regex search across all files
  list_files()                       — list all vault notes

The vault also contains skill definitions at System/Skills/. If the user's request
involves a task or workflow (capturing, enriching, building, planning), use
search_vault("skill: <topic>") or grep_vault("skill-name") to check whether a
relevant skill exists before responding.

Output your reasoning in this format:

Thought: [your reasoning about what information is needed]
Tool: tool_name("arguments")
(You can specify multiple Tool lines if needed.)

If no external knowledge is needed, just output:
Thought: No external lookup needed.

User message: {sanitized_input}"""
        thinking_response = self._call_backend(thinking_prompt, timeout, prefer_backend="groq" if self.prefer_groq_for_think else None)
        thought, tool_calls = self.thinker.extract_thoughts_and_tools(thinking_response)

        # === 3. Read (kb_core for search, base dispatch for I/O tools) with retry loop ===
        MAX_RETRIEVAL_ROUNDS = 3
        vault_context_parts = []
        remaining_calls = list(tool_calls) if tool_calls else []
        rounds = 0

        while remaining_calls and rounds < MAX_RETRIEVAL_ROUNDS:
            rounds += 1
            before_len = len(vault_context_parts)

            for tc in remaining_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                try:
                    if tool_name == "search_vault":
                        query = tool_args[0] if len(tool_args) >= 1 else ""
                        top_k = int(tool_args[1]) if len(tool_args) >= 2 and str(tool_args[1]).isdigit() else 5
                        results = self.kb.search(query, top_k=top_k)
                        for res in results:
                            vault_context_parts.append(
                                f"Source: {res['file']} - {res['heading']}\n{res['snippet']}"
                            )
                        continue

                    # Build args dict for _dispatch_tool (direct I/O tools)
                    args_dict = {}
                    if tool_name == "read_section" and len(tool_args) >= 2:
                        args_dict = {"file_path": tool_args[0], "heading": tool_args[1]}
                    elif tool_name == "read_lines" and len(tool_args) >= 3:
                        args_dict = {"file_path": tool_args[0], "start_line": int(tool_args[1]), "end_line": int(tool_args[2])}
                    elif tool_name == "outline" and len(tool_args) >= 1:
                        args_dict = {"file_path": tool_args[0]}
                    elif tool_name == "grep_vault" and len(tool_args) >= 1:
                        args_dict = {"pattern": tool_args[0], "file_filter": tool_args[1] if len(tool_args) >= 2 else None}
                    elif tool_name == "list_files":
                        args_dict = {}
                    else:
                        vault_context_parts.append(f"[Error: Unknown tool {tool_name}]")
                        continue

                    result_json = self._dispatch_tool(tool_name, args_dict)
                    result = json.loads(result_json)

                    # Extract useful content based on result shape
                    if isinstance(result, dict):
                        if "results" in result and isinstance(result["results"], list):
                            for res in result["results"]:
                                file_info = res.get('file', 'unknown')
                                heading = res.get('heading', '')
                                content = res.get('content', '')
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
                    elif isinstance(result, list):
                        vault_context_parts.append(str(result))
                    else:
                        vault_context_parts.append(str(result))
                except Exception as e:
                    logging.error(f"Tool {tool_name} failed: {e}")
                    vault_context_parts.append(f"[Error calling {tool_name}: {e}]")

            # Quality check: did this round produce any non-error content?
            new_parts = vault_context_parts[before_len:]
            useful = [p for p in new_parts if not p.startswith("[Error")]
            if useful:
                break  # Got useful results — done

            # Thin/no results — ask Think to try a different approach
            if rounds < MAX_RETRIEVAL_ROUNDS:
                retry_prompt = f"""Your previous retrieval returned no useful results.
        Original query: {sanitized_input}
        Tools tried: {[tc['name'] for tc in remaining_calls]}
        Try different search terms or a different tool. Output new Tool: calls only."""
                retry_response = self._call_backend(retry_prompt, timeout, prefer_backend="groq" if self.prefer_groq_for_think else None)
                _, remaining_calls = self.thinker.extract_thoughts_and_tools(retry_response)
                if not remaining_calls:
                    break
        vault_context = "\n\n---\n\n".join(vault_context_parts) if vault_context_parts else ""

        # === 4. Respond (grounded) ===
        grounded_input = f"{sanitized_input}\n\n[Relevant Vault Context]:\n{vault_context}" if vault_context else sanitized_input
        response = self._call_backend_with_history(grounded_input, timeout, prefer_backend="groq" if self.prefer_groq_for_think else None)

        # === 5. Post-process warnings ===
        if warning_detected:
            response = f"⚠️ **Potential Injection Detected**\n\n{response}"

        # === 6. Manually append clean history ===
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": response})
        # Trim to sliding window (10 turns = 20 messages)
        max_messages = 20
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

        # === 7. Summarization / Ask & Confirm (lightweight turns only) ===
        if self.memory.needs_summarization(self.history) and self._is_lightweight_turn(user_message):
            if not self.memory.pending_insight:
                recent = self.history[-self.memory.get_pruning_index(self.history):]
                user_msgs = [m.get('content', '') for m in recent if m.get('role') == 'user']
                snippet = "\n---\n".join(user_msgs)
                summarization_prompt = f"""You are summarizing a conversation for the operator's executive brain. Extract the *key insights*, patterns, and actionable takeaways from the following user messages. Limit the summary to ~150 words and present it as a concise bullet list.

User messages:\n{snippet}\n"""
                insight_text = self._call_backend(summarization_prompt, timeout)
                self.memory.set_pending_insight(insight_text.strip(), session_topic="General")
                return "I have extracted a key insight from our recent conversation. Would you like me to create an Insight note for it? (yes/no)"
            else:
                return response

        return response
