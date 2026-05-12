# Ariel Orchestrator — Improvement Spec

**Status:** Items 0–2, 4–6 implemented. Item 3 TODO.

**Branch:** `feature/orchestrator-improvements`
**Target repo:** `~/git/ariel/`
**Key files:**
- `core/ariel/persona.py` — ArielOrchestrator (Think→Read→Respond loop)
- `core/ariel/thinking.py` — ArielThinking (parses Think output)
- `core/ariel/memory.py` — ArielMemory (token threshold, summarization)
- `core/kb_core.py` — BM25 search engine (replaces Knowledge Loom)
- `core/tools.config.yaml` — tool manifest
- `operator/config.yaml` — backend routing
- `~/git/lmf/stack/lmf/orchestrator.py` — base Orchestrator (DO NOT edit unless noted)

**Key change from spec:** Knowledge Loom replaced with `kb_core.py` copied into `core/kb_core.py`. `rank-bm25` added to `requirements.txt`. The base orchestrator's `_dispatch_tool()` only routes `search_vault` to Loom; all other vault tools (`read_section`, `grep_vault`, `outline`, etc.) already use direct file I/O. Now `search_vault` routes to kb_core instead — no Docker/Loom dependency at runtime.

Work items are ordered by dependency. Items 0 and 1 must land first.

---

## Item 0 — Bug: Tool name mismatch (READ THIS FIRST) ✅ **DONE**

**File:** `core/ariel/persona.py` lines 52–64 (thinking_prompt) and lines 74–116 (Read loop)

**Problem:** The Think prompt instructs the model to output `Tool: loom_search(...)`, `Tool: loom_read_section(...)`, etc. But `_dispatch_tool()` (inherited from base Orchestrator) only handles `search_vault`, `read_section`, `read_lines`, `outline`, `grep_vault`, `list_files`. There is no `loom_*` handler. Every tool call from the Think step silently returns `{"error": "Unknown tool: loom_search"}`. The Read step has never worked.

**Fix:** Update the Think prompt in `persona.py` to instruct the model to use the correct tool names. Replace the tool instruction block in `thinking_prompt` (lines 55–63):

```python
# Replace:
If you need to look up information in the vault, specify the exact loom tool calls you would make.
...
Tool: loom_tool_name("arguments")

# With:
If you need to look up information in the vault, specify the tool calls you would make using these exact tool names:
  search_vault("query")           — full-text search across vault notes
  read_section("path", "heading") — read a named section from a specific file
  read_lines("path", start, end)  — read a line range from a file
  outline("path")                 — get heading structure of a file
  grep_vault("pattern")           — regex search across all files
  list_files()                    — list all vault notes
```

Also update the ArielThinking TOOL_RE in `core/ariel/thinking.py` if needed to match the new format (it currently matches any `word(args)` pattern so it should still work).

---

## Item 1 — Bug: History pollution from super().chat() calls ✅ **DONE**

**File:** `core/ariel/persona.py` lines 65 and 121

**Problem:** `super().chat(thinking_prompt)` and `super().chat(grounded_input)` each append their own (input, output) pair to `self.history`. After one turn, history contains `[thinking_prompt, thinking_response, grounded_input, grounded_response]` instead of `[user_message, response]`. Internal monologue accumulates in the context window visible to the model.

**Fix:** Do not use `super().chat()` for the Think step or the Respond step. Instead, call the backend directly. Add a helper method to `ArielOrchestrator` that calls the backend without touching history:

```python
def _call_backend(self, prompt: str, timeout: int) -> str:
    """Single backend call — does not append to history."""
    from lmf.orchestrator import BACKENDS
    from lmf.backends import BackendError, RateLimitError
    messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}]
    for _, backend in BACKENDS:
        if not backend.is_available:
            continue
        try:
            result = backend.chat(messages, tools=None, timeout=timeout)
            return result.content
        except (RateLimitError, BackendError):
            continue
    return "[All backends exhausted]"
```

Replace `super().chat(thinking_prompt, timeout)` at line 65 with `self._call_backend(thinking_prompt, timeout)`.

For the Respond step at line 121, also replace `super().chat(grounded_input, timeout)` with a variant that uses `self.history` for context but does not itself append to history — then manually append the correct `(user_message, response)` pair at the end. Example:

```python
def _call_backend_with_history(self, user_message: str, timeout: int) -> str:
    """Backend call with conversation history — does not auto-append to history."""
    from lmf.orchestrator import BACKENDS
    from lmf.backends import BackendError, RateLimitError
    messages = [{"role": "system", "content": self.system_prompt}]
    messages += self.history
    messages.append({"role": "user", "content": user_message})
    for _, backend in BACKENDS:
        if not backend.is_available:
            continue
        try:
            result = backend.chat(messages, tools=None, timeout=timeout)
            return result.content
        except (RateLimitError, BackendError):
            continue
    return "[All backends exhausted]"
```

At the end of `ArielOrchestrator.chat()` (before `return response`), manually append:
```python
self.history.append({"role": "user", "content": user_message})
self.history.append({"role": "assistant", "content": response})
# Trim to sliding window
max_messages = 20  # 10 turns
if len(self.history) > max_messages:
    self.history = self.history[-max_messages:]
```

---

## Item 2 — Route Think step to Groq backend ✅ **DONE**

**File:** `core/ariel/persona.py` lines 65 and `operator/config.yaml`

**Why:** 3b local model (qwen2.5:3b) is too small for the metacognitive task of planning retrieval. Groq's `llama-3.3-70b-versatile` is free-tier and fast. Routing Think there gets better tool selection without touching the Respond step model.

**Implementation:** Update `_call_backend()` from Item 1 to accept an optional `prefer_backend` parameter:

```python
def _call_backend(self, prompt: str, timeout: int, prefer_backend: str | None = None) -> str:
    from lmf.orchestrator import BACKENDS
    from lmf.backends import BackendError, RateLimitError
    messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}]

    # Try preferred backend first if specified
    ordered = BACKENDS[:]
    if prefer_backend:
        ordered = sorted(ordered, key=lambda x: (0 if x[1].name == prefer_backend else 1, x[0]))

    for _, backend in ordered:
        if not backend.is_available:
            continue
        try:
            result = backend.chat(messages, tools=None, timeout=timeout)
            return result.content
        except (RateLimitError, BackendError):
            continue
    return "[All backends exhausted]"
```

Call Think with: `self._call_backend(thinking_prompt, timeout, prefer_backend="groq")`

If Groq is not available (key not set, rate limited), it falls back automatically to whatever backend is next.

---

## Item 3 — Sequential tool calling loop in Read phase

**File:** `core/ariel/persona.py` lines 68–117 (the Read block)

**Why:** Currently fires all Think-selected tools in one pass and takes whatever comes back. If results are thin, Ariel responds with nothing useful. A retrieval loop lets Ariel reassess and try again.

**Implementation:** Replace the current `for tc in tool_calls:` block with a `while` loop with a MAX_RETRIEVAL_ROUNDS guard (3 is enough):

```python
MAX_RETRIEVAL_ROUNDS = 3

vault_context_parts = []
remaining_calls = list(tool_calls)  # seeded from Think step
rounds = 0

while remaining_calls and rounds < MAX_RETRIEVAL_ROUNDS:
    rounds += 1
    round_results = []

    for tc in remaining_calls:
        # ... (same dispatch logic as current, building round_results)

    vault_context_parts.extend(round_results)

    # Quality check: assess if context is sufficient
    non_error_results = [r for r in round_results if not r.startswith("[Error")]
    if non_error_results:
        break  # got something useful — stop

    # Thin results — ask Think to try a different approach
    retry_prompt = f"""Your previous retrieval returned no useful results.
Original query: {sanitized_input}
Tools tried: {[tc['name'] for tc in remaining_calls]}
Try different search terms or a different tool. Output new Tool: calls only."""

    retry_response = self._call_backend(retry_prompt, timeout, prefer_backend="groq")
    _, remaining_calls = self.thinker.extract_thoughts_and_tools(retry_response)
    if not remaining_calls:
        break
```

---

## Item 4 — Loom health check → kb_core init ✅ **DONE** (superseded)

**File:** `core/ariel/persona.py` — add to `__init__` and start of `chat()`

**Note:** Loom removed entirely. Replaced with `kb_core.KnowledgeBase(self.vault)` initialized at startup. If kb_core fails (bad vault path), error is immediate at __init__, not silent at runtime. No health-check ping needed — no Docker dependency.

**Why:** When Loom is down, all tool calls fail silently and Ariel responds with no vault context. The failure is invisible. Surface it immediately.

**Implementation:** Add a `_check_loom()` method:

```python
def _check_loom(self) -> bool:
    import requests
    try:
        r = requests.get(f"{self.loom_url}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False
```

Call at start of `chat()`, before the Think step:

```python
if not self._check_loom():
    logging.warning("[Ariel] Knowledge Loom unreachable — vault context unavailable this turn")
    # Still respond, but skip Think/Read entirely
    return self._call_backend_with_history(sanitized_input, timeout)
```

Also call once at `__init__` time and log a warning so the problem is visible at startup.

---

## Item 5 — Skills as retrieval target ✅ **DONE**

**File:** `core/ariel/persona.py` — thinking_prompt (lines 52–64)

**Why:** Ariel's skills live in `System/Skills/` and are indexed by Loom. If a user's request implies a skill pattern, Ariel should be able to search for it. Currently the Think prompt has no awareness that skills are searchable.

**Implementation:** Extend the Think prompt to mention skills:

```python
# Add to the thinking_prompt, after the tool list:
The vault also contains skill definitions at System/Skills/. If the user's request
involves a task or workflow (capturing, enriching, building, planning), use
search_vault("skill: <topic>") or grep_vault("skill-name") to check whether a
relevant skill exists before responding.
```

No code changes needed beyond the prompt update — Loom already indexes System/Skills/ as part of the vault.

---

## Item 6 — Token budget interrupt at natural pause only ✅ **DONE**

**File:** `core/ariel/persona.py` lines 128–141 (summarization/insight block)

**Why:** Currently the insight prompt fires after any turn where memory threshold is hit, regardless of what the user was doing. A mid-task interrupt ("Would you like me to create an Insight note?") is disruptive.

**Implementation:** Add a `_is_lightweight_turn()` check — only trigger the insight prompt when the current turn is short and non-task:

```python
def _is_lightweight_turn(self, message: str) -> bool:
    """True if the message is short enough that an insight interrupt is non-disruptive."""
    return len(message.split()) < 15 and not any(
        kw in message.lower() for kw in ["build", "write", "create", "fix", "update", "add", "run"]
    )
```

Wrap the summarization block at line 128:

```python
if self.memory.needs_summarization(self.history) and self._is_lightweight_turn(user_message):
    # ... existing insight/summarization block
```

---

## Test Plan

After each item, verify with a direct `curl` to `POST /chat`:

```bash
# Smoke test after Items 0+1
curl -s -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What tasks are in my inbox?"}' | jq .

# Verify tool calls fired (check logs for dispatch calls, not errors)
# Verify response contains actual vault content, not empty context

# Verify history is clean after two turns (not accumulating Think prompts)
curl -s http://localhost:8002/status | jq .history_turns
```

After Item 4, kill the Knowledge Loom container and confirm Ariel responds with a graceful degraded response rather than silently returning no context.

---

## Implementation Status

```
✅ Item 0 — fix tool names                  → done
✅ Item 1 — fix history pollution            → done
✅ Item 2 — Groq for Think                   → done
⬜ Item 3 — retrieval loop                   → TODO (depends on 0, now ready)
✅ Item 4 — Loom removed, kb_core init       → done (superseded)
✅ Item 5 — skills as retrieval target       → done
✅ Item 6 — token interrupt gate             → done
```
