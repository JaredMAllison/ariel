#!/usr/bin/env python3
"""
Markdown Knowledge Base — core search and I/O layer.

Shared between kb_mcp.py (Claude Code MCP server) and Ariel's orchestrator
(imported directly as a Python module). No MCP dependency here.

Environment:
  KB_ROOT — root directory of Markdown files (required when used standalone)
"""

import os
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from rank_bm25 import BM25Okapi


# ─────────────────────────────────────────────────────────────────────────────
# Data Models

@dataclass
class Chunk:
    """A meaningful text unit (typically a section under a heading)."""
    file: str
    heading: str
    line_start: int
    line_end: int
    text: str
    tokens: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.tokens:
            self.tokens = tokenize(self.text)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities

def tokenize(text: str) -> list[str]:
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def read_file(file_path: Path) -> list[str]:
    try:
        return file_path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []


def find_markdown_files(root: Path) -> list[Path]:
    return sorted(root.glob("**/*.md"))


def parse_chunks(file_path: Path, root: Path) -> list[Chunk]:
    lines = read_file(file_path)
    rel_path = file_path.relative_to(root).as_posix()
    chunks = []
    heading_stack = []
    i = 0

    while i < len(lines):
        line = lines[i]
        match = re.match(r'^(#{1,6})\s+(.+)$', line)

        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text, i + 1))

            breadcrumb = " > ".join(h[1] for h in heading_stack)

            j = i + 1
            content_lines = []
            while j < len(lines) and not re.match(r'^#{1,6}\s+', lines[j]):
                content_lines.append(lines[j])
                j += 1

            content = "\n".join(content_lines).strip()
            if content:
                chunks.append(Chunk(
                    file=rel_path,
                    heading=breadcrumb,
                    line_start=i + 1,
                    line_end=j - 1 if j > i + 1 else i + 1,
                    text=content
                ))
            i = j
        else:
            i += 1

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base

class KnowledgeBase:
    """
    In-memory BM25-indexed knowledge base over a directory of Markdown files.

    Usage (Claude Code MCP server):
        kb = KnowledgeBase(Path(os.environ["KB_ROOT"]))

    Usage (Ariel orchestrator):
        from kb_core import KnowledgeBase
        kb = KnowledgeBase(Path("/path/to/your/vault"))
    """

    def __init__(self, root: Path):
        self.root = root
        self.chunks: list[Chunk] = []
        self.bm25 = None
        self.all_lines: dict[str, list[str]] = {}
        self.rebuild()

    def rebuild(self):
        self.chunks = []
        self.all_lines = {}
        for fp in find_markdown_files(self.root):
            rel = fp.relative_to(self.root).as_posix()
            self.all_lines[rel] = read_file(fp)
            self.chunks.extend(parse_chunks(fp, self.root))
        if self.chunks:
            self.bm25 = BM25Okapi([c.tokens for c in self.chunks])

    def search(self, query: str, top_k: int = 5, file_filter: Optional[str] = None) -> list[dict]:
        if not self.bm25:
            return []
        query_tokens = tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        results = []
        for chunk, score in zip(self.chunks, scores):
            if file_filter and file_filter not in chunk.file:
                continue
            if score > 0:
                snippet = chunk.text
                for token in query_tokens:
                    idx = snippet.lower().find(token)
                    if idx >= 0:
                        start = max(0, idx - 50)
                        end = min(len(snippet), idx + 150)
                        snippet = snippet[start:end].strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(chunk.text):
                            snippet = snippet + "..."
                        break
                results.append({
                    "file": chunk.file,
                    "heading": chunk.heading,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                    "snippet": snippet,
                    "score": float(score)
                })
        return sorted(results, key=lambda r: r["score"], reverse=True)[:top_k]

    def list_files(self) -> list[dict]:
        files = []
        for fp in find_markdown_files(self.root):
            rel = fp.relative_to(self.root).as_posix()
            lines = self.all_lines.get(rel, [])
            size_kb = round(fp.stat().st_size / 1024, 1)
            files.append({"file": rel, "line_count": len(lines), "size_kb": size_kb})
        return sorted(files, key=lambda f: f["file"])

    def outline(self, file_path: str) -> list[dict]:
        lines = self.all_lines.get(Path(file_path).as_posix(), [])
        result = []
        for i, line in enumerate(lines, 1):
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                result.append({"level": len(m.group(1)), "heading": m.group(2).strip(), "line_number": i})
        return result

    def grep(self, pattern: str, file_filter: Optional[str] = None, limit: int = 50) -> list[dict]:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return [{"error": f"Invalid regex: {e}"}]
        results = []
        for rel, lines in self.all_lines.items():
            if file_filter and file_filter not in rel:
                continue
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    results.append({"file": rel, "line_number": i, "line_text": line[:500]})
                    if len(results) >= limit:
                        return results
        return results

    def read_section(self, file_path: str, heading: str) -> Optional[dict]:
        heading_lower = heading.lower()
        for chunk in self.chunks:
            if chunk.file == file_path and heading_lower in chunk.heading.lower():
                return {
                    "file": chunk.file,
                    "heading": chunk.heading,
                    "heading_line": chunk.line_start,
                    "content_start": chunk.line_start + 1,
                    "content_end": chunk.line_end,
                    "content": chunk.text
                }
        return None

    def read_lines(self, file_path: str, start_line: int, end_line: int) -> Optional[dict]:
        rel = Path(file_path).as_posix()
        lines = self.all_lines.get(rel)
        if not lines:
            return None
        start_line = max(1, start_line)
        end_line = min(len(lines), end_line)
        return {
            "file": rel,
            "start_line": start_line,
            "end_line": end_line,
            "content": "\n".join(lines[start_line - 1:end_line])
        }

    def replace_lines(self, file_path: str, start_line: int, end_line: int, new_content: str) -> dict:
        rel = Path(file_path).as_posix()
        full_path = self.root / rel
        lines = read_file(full_path)
        start_line = max(1, start_line)
        end_line = min(len(lines), end_line)
        new_lines = lines[:start_line - 1] + new_content.splitlines() + lines[end_line:]
        full_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
        self.rebuild()
        return {"file": rel, "replaced_lines": end_line - start_line + 1, "new_line_count": len(new_lines)}

    def insert_after_heading(self, file_path: str, heading: str, content: str) -> dict:
        rel = Path(file_path).as_posix()
        full_path = self.root / rel
        lines = read_file(full_path)
        heading_lower = heading.lower()
        insert_at = None
        for i, line in enumerate(lines):
            if re.match(r'^#{1,6}\s+', line) and heading_lower in line.lower():
                insert_at = i + 1
                break
        if insert_at is None:
            return {"error": f"Heading '{heading}' not found in {rel}"}
        new_lines = lines[:insert_at] + [""] + content.splitlines() + lines[insert_at:]
        full_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
        self.rebuild()
        return {"file": rel, "inserted_at_line": insert_at + 1}

    def append_to_file(self, file_path: str, content: str) -> dict:
        rel = Path(file_path).as_posix()
        full_path = self.root / rel
        full_path.parent.mkdir(parents=True, exist_ok=True)
        current = read_file(full_path) if full_path.exists() else []
        new_lines = current + ["", content]
        full_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
        self.rebuild()
        return {"file": rel, "appended_at_line": len(new_lines)}

    def create_file(self, file_path: str, content: str) -> dict:
        target = self.root / file_path
        if target.exists():
            return {"error": f"file already exists: {file_path}"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.rebuild()
        return {"file": file_path, "created": True, "line_count": len(content.splitlines())}
