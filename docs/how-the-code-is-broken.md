# How the Ariel Orchestrator Code Is Broken — Plain Language

**Read this whenever.** It explains what the spec says to fix and why.

---

## The Big Picture

Ariel works in three phases per conversation turn:

1. **Think** — a fast model (currently qwen2.5:3b) reads the user's message and plans what information to look up in the vault.
2. **Read** — Ariel executes those lookups and collects the results.
3. **Respond** — Ariel sends the user's message + vault context to the main model for a final answer.

Each phase calls a backend model (Ollama, Groq, etc.) to do the thinking/generating.

## Bug 1: The Tool Names Don't Match

The Think prompt tells the model to say things like:

```
Tool: loom_search("tasks", "overdue")
```

But the code that *runs* the tool only understands names like `search_vault`. There is no handler for `loom_search`. So every vault lookup silently returns:

```json
{"error": "Unknown tool: loom_search"}
```

**The Read phase has never worked.** Ariel has never actually read from your vault during a conversation. Every response has been pure model knowledge with no vault context.

## Bug 2: The Model Sees Its Own Homework

Each phase calls `super().chat()` — a method inherited from the base Orchestrator. That method automatically saves *every* input/output pair into conversation history.

After one turn, the history looks like this:

```
[user said "think about this"]  ← internal monologue prompt
[model's thinking response]      ← internal monologue output
[user said "respond to this with context"]  ← grounded prompt
[model's final response]         ← what the user should see
```

But it should look like:

```
[user message]
[Ariel's response]
```

The model can see its own internal monologue from previous turns, which pollutes the context window and makes it sound like it's talking to itself.

## What Knowledge Loom Is — and Why We're Ditching It

Knowledge Loom is a Rust search engine that runs as a Docker container. It indexes the vault and provides a BM25 search API at `http://knowledge-loom:8888/api/search`. The base orchestrator calls it only for `search_vault`. All other vault tools (`read_section`, `grep_vault`, `outline`, etc.) read files directly from disk — no Loom needed.

Loom was set up as an MCP server (ADR-029), but it's flaky, requires Docker, and only one tool actually depends on it. If Loom is down, search silently returns nothing.

## What kb_core Is

`kb_core.py` is a single Python file at `~/.local/share/obsidian-mcp/kb_core.py`. It's a pure-Python BM25 search engine over markdown files. It does everything Loom does — search, grep, read sections, list files — with no Docker, no HTTP, no sidecar. Just `from kb_core import KnowledgeBase` and you're done.

It was the original search system before Loom replaced it (see ADR-024 → ADR-029). We're going back to it.

## Fix Status (as of 2026-05-11)

| # | What | Status |
|---|---|---|
| 0 | Fix tool names: `search_vault` not `loom_search` | ✅ Done |
| 1 | Stop history pollution: don't use `super().chat()` for internal steps | ✅ Done |
| 2 | Route Think phase to Groq for better tool selection | ✅ Done |
| 3 | Retry loop: if search returns nothing, try again with different terms | ❌ TODO |
| 4 | Loom removed, kb_core in its place | ✅ Done — Loom dependency dropped entirely |
| 5 | Teach Think prompt about skills as search targets | ✅ Done |
| 6 | Don't interrupt mid-task with "want me to save this insight?" | ✅ Done |

## Where the Code Lives

```
~/git/ariel/
├── core/ariel/
│   ├── persona.py       ← ArielOrchestrator (Think→Read→Respond loop)
│   ├── thinking.py      ← Parses "Thought: ... Tool: ..." output
│   └── memory.py        ← Token budget tracking
├── operator/config.yaml ← Backend routing (Ollama, Groq, OpenRouter)
└── ORCHESTRATOR_SPEC.md ← The improvement spec you wrote
```

Base orchestrator (read-only unless noted):
```
~/git/lmf/stack/lmf/orchestrator.py
```

kb_core (imported directly):
```
~/.local/share/obsidian-mcp/kb_core.py
```
