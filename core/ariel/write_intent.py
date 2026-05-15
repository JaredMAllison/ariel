import re
from dataclasses import dataclass


@dataclass
class WriteIntent:
    tool: str   # "append_to_file" | "create_file"
    args: dict  # ready to pass to _dispatch_tool


class WriteIntentParser:

    # --- Word libraries for [Library] capture [Library] pattern ---
    # Lead-in words that can precede "capture" (left library)
    _LEFT_LEADINS = r"(?:please|just|for\s+now|can\s+you|could\s+you|would\s+you)\s+"
    # Pronouns/reference words that trigger history resolution (right library)
    _REFERENCE_WORDS = frozenset(["this", "it", "that"])

    # Most specific first: explicit file path in message
    _APPEND_FILE = re.compile(
        r"append\s+['\"]?(.+?)['\"]?\s+to\s+(?:the\s+file\s+)?([\w\/.-]+\.md)",
        re.IGNORECASE,
    )
    # Create at explicit path: "create X note at path.md with title/content 'Y'"
    _CREATE_AT = re.compile(
        r"create\s+(?:a\s+new\s+)?(?:\w+\s+)?(?:note|file)\s+at\s+([\w\/.-]+\.md)"
        r"(?:.*?(?:title|content):?\s+['\"]([^'\"]+)['\"])?",
        re.IGNORECASE | re.DOTALL,
    )
    # Capture X as insight — handle "capture:" or "capture " variants
    _INSIGHT_CAPTURE = re.compile(
        r"capture[\s:]*(.+?)\s+as\s+(?:an?\s+)?insight",
        re.IGNORECASE,
    )
    # Create an insight about/called/for X
    _INSIGHT_CREATE = re.compile(
        r"create\s+(?:an?\s+)?(?:new\s+)?insight\s+(?:about|called|named|titled|for)\s+(.+)",
        re.IGNORECASE,
    )
    # Create a task for/called X
    _TASK_CREATE = re.compile(
        r"create\s+(?:a\s+)?(?:new\s+)?task\s+(?:for|called|named|titled)\s+(.+)",
        re.IGNORECASE,
    )
    # "add/append/capture X to (my) inbox" — content before "to inbox"
    # Handles "capture:" or "capture " variants
    _INBOX_BEFORE = re.compile(
        r"(?:add|append|capture)[\s:]*(.+?)\s+to\s+(?:my\s+)?inbox",
        re.IGNORECASE,
    )
    # "add this to my inbox: 'content'" — content after colon
    _INBOX_COLON = re.compile(
        r"to\s+(?:my\s+)?inbox:?\s+['\"](.+?)['\"]",
        re.IGNORECASE,
    )
    # [Library] capture [Library] — generic trigger, checked last.
    # Left library: lead-in words. Right library: content or reference pronoun.
    # Handles "capture:" or "capture " variants
    _CAPTURE_INBOX = re.compile(
        rf"(?:{_LEFT_LEADINS})?capture[\s:]*(.+)",
        re.IGNORECASE,
    )

    def _is_reference_word(self, text: str) -> bool:
        return text.lower() in self._REFERENCE_WORDS

    def detect_capture_flow(self, message: str) -> str | None:
        """Check if message matches generic [Library] capture [Library] pattern.
        Returns the captured content string if matched, None otherwise.
        Allows through pronoun-only inbox-before matches (e.g. 'capture that to inbox')
        since parse() returns None for those — they need capture flow to disambiguate."""
        msg = message.strip()
        # Exclude messages with specific target types (handled by parse())
        if self._INSIGHT_CAPTURE.search(msg):
            return None
        if self._INSIGHT_CREATE.search(msg):
            return None
        if self._TASK_CREATE.search(msg):
            return None
        if self._INBOX_COLON.search(msg):
            return None
        if self._APPEND_FILE.search(msg):
            return None
        if self._CREATE_AT.search(msg):
            return None
        # Inbox-before with non-pronoun content — handled by parse(), exclude.
        # Pronoun inbox-before — parse() returns None, route to capture flow directly.
        m = self._INBOX_BEFORE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            if not self._is_reference_word(content):
                return None  # Has real content — handled by parse()
            return content  # Pronoun — route to capture flow, don't fall through to _CAPTURE_INBOX
        # Generic [Library] capture [Library] (no specific target like "to inbox")
        m = self._CAPTURE_INBOX.search(msg)
        if m:
            return m.group(1).strip().strip("'\"")
        return None

    def parse(self, message: str) -> "WriteIntent | None":
        msg = message.strip()

        # 1. Explicit file append — most specific, has .md path
        m = self._APPEND_FILE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            file_path = m.group(2).strip()
            return WriteIntent(
                tool="append_to_file",
                args={"file_path": file_path, "content": content},
            )

        # 2. Create at explicit path
        m = self._CREATE_AT.search(msg)
        if m:
            file_path = m.group(1).strip()
            content = (m.group(2) or msg).strip().strip("'\"")
            return WriteIntent(
                tool="create_file",
                args={"file_path": file_path, "content": content},
            )

        # 3. Capture X as insight
        m = self._INSIGHT_CAPTURE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            slug = _slugify(content[:60])
            return WriteIntent(
                tool="create_file",
                args={"file_path": f"Insights/{slug}.md", "content": content},
            )

        # 4. Create insight
        m = self._INSIGHT_CREATE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            slug = _slugify(content[:60])
            return WriteIntent(
                tool="create_file",
                args={"file_path": f"Insights/{slug}.md", "content": content},
            )

        # 5. Create task
        m = self._TASK_CREATE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            slug = _slugify(content[:60])
            return WriteIntent(
                tool="create_file",
                args={"file_path": f"Tasks/{slug}.md", "content": content},
            )

        # 6. Inbox — content after colon (e.g. "Add this to my inbox: 'X'")
        m = self._INBOX_COLON.search(msg)
        if m:
            content = m.group(1).strip()
            return WriteIntent(
                tool="append_to_file",
                args={"file_path": "Inbox.md", "content": content},
            )

        # 7. Inbox — content before "to inbox" (e.g. "Add X to my inbox")
        m = self._INBOX_BEFORE.search(msg)
        if m:
            content = m.group(1).strip().strip("'\"")
            if not self._is_reference_word(content):
                return WriteIntent(
                    tool="append_to_file",
                    args={"file_path": "Inbox.md", "content": content},
                )

        return None


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "note"
