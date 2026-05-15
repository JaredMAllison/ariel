import re
from dataclasses import dataclass


@dataclass
class WriteIntent:
    tool: str   # "append_to_file" | "create_file"
    args: dict  # ready to pass to _dispatch_tool


class WriteIntentParser:
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
    # Capture X as insight
    _INSIGHT_CAPTURE = re.compile(
        r"capture\s+(.+?)\s+as\s+(?:an?\s+)?insight",
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
    _INBOX_BEFORE = re.compile(
        r"(?:add|append|capture)\s+(.+?)\s+to\s+(?:my\s+)?inbox",
        re.IGNORECASE,
    )
    # "add this to my inbox: 'content'" — content after colon
    _INBOX_COLON = re.compile(
        r"to\s+(?:my\s+)?inbox:?\s+['\"](.+?)['\"]",
        re.IGNORECASE,
    )

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
            if content.lower() not in ("this", "it", "that"):
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
