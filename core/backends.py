"""
backends.py — Inference backend abstraction for the orchestrator.

BaseBackend + OpenAI-compatible + Ollama implementations.
Each backend normalizes its response to {content, tool_calls, usage}.
"""

import json
import time
from abc import ABC, abstractmethod

import requests


class BackendError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(BackendError):
    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class BackendResult:
    """Normalized result from any backend."""
    def __init__(self, content: str, tool_calls: list | None = None, usage: dict | None = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}


class BaseBackend(ABC):
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.last_error: str | None = None
        self._consecutive_failures = 0

    @abstractmethod
    def chat(self, messages: list, tools: list | None = None, timeout: int = 300) -> BackendResult:
        ...

    @property
    def is_available(self) -> bool:
        return self._consecutive_failures < 3

    def _record_failure(self, error: str):
        self.last_error = error
        self._consecutive_failures += 1

    def _record_success(self):
        self._consecutive_failures = 0


class OpenAICompatibleBackend(BaseBackend):
    """Groq, OpenRouter, Cerebras, etc. — any OpenAI-format API."""

    def chat(self, messages: list, tools: list | None = None, timeout: int = 300) -> BackendResult:
        url = self.config["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config['api_key']}",
            "User-Agent": "ArielOrchestrator/1.0",
        }
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        t0 = time.monotonic()
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            elapsed = int((time.monotonic() - t0) * 1000)

            if resp.status_code == 429:
                retry_after = None
                try:
                    retry_after = float(resp.headers.get("retry-after", 0))
                except (ValueError, TypeError):
                    pass
                raise RateLimitError(
                    f"{self.name} 429 — {resp.text[:200]}",
                    retry_after=retry_after,
                )
            resp.raise_for_status()

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # Extract rate limit info from headers for logging
            rl_info = {
                "rl_remaining_requests": resp.headers.get("x-ratelimit-remaining-requests"),
                "rl_remaining_tokens": resp.headers.get("x-ratelimit-remaining-tokens"),
                "rl_reset_requests": resp.headers.get("x-ratelimit-reset-requests"),
                "rl_reset_tokens": resp.headers.get("x-ratelimit-reset-tokens"),
            }

            tool_calls = None
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_calls = []
                for tc in msg["tool_calls"]:
                    fn = tc["function"]
                    args = fn["arguments"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    tool_calls.append({
                        "function": {"name": fn["name"], "arguments": args},
                    })

            usage = data.get("usage", {})
            usage["elapsed_ms"] = elapsed
            usage["rate_limit"] = rl_info

            self._record_success()
            return BackendResult(
                content=msg.get("content", "") or "",
                tool_calls=tool_calls,
                usage=usage,
            )

        except requests.exceptions.Timeout:
            self._record_failure("timeout")
            raise BackendError(f"{self.name} timed out after {timeout}s")
        except requests.exceptions.ConnectionError:
            self._record_failure("connection error")
            raise BackendError(f"{self.name} unreachable")
        except RateLimitError:
            self._record_failure("rate limited")
            raise
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            detail = e.response.text[:200] if e.response is not None else ""
            self._record_failure(f"HTTP {status}")
            raise BackendError(f"{self.name} HTTP {status}: {detail}", status_code=status)
        except (KeyError, json.JSONDecodeError) as e:
            self._record_failure("bad response")
            raise BackendError(f"{self.name} bad response: {e}")


class OllamaBackend(BaseBackend):
    """Local Ollama inference via /api/chat."""

    def chat(self, messages: list, tools: list | None = None, timeout: int = 300) -> BackendResult:
        url = self.config["base_url"].rstrip("/") + "/api/chat"
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": int(self.config.get("num_ctx", 8192))},
        }
        if tools:
            payload["tools"] = tools

        t0 = time.monotonic()
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            elapsed = int((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            data = resp.json()
            msg = data["message"]

            tool_calls = None
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_calls = []
                for tc in msg["tool_calls"]:
                    fn = tc["function"]
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    tool_calls.append({
                        "function": {"name": fn["name"], "arguments": args},
                    })

            content = msg.get("content", "") or ""
            self._record_success()
            return BackendResult(content=content, tool_calls=tool_calls, usage={"elapsed_ms": elapsed})

        except requests.exceptions.Timeout:
            self._record_failure("timeout")
            raise BackendError(f"{self.name} timed out after {timeout}s")
        except requests.exceptions.ConnectionError:
            self._record_failure("connection error")
            raise BackendError(f"{self.name} unreachable")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            detail = e.response.text[:200] if e.response is not None else ""
            self._record_failure(f"HTTP {status}")
            raise BackendError(f"{self.name} HTTP {status}: {detail}", status_code=status)
        except (KeyError, json.JSONDecodeError) as e:
            self._record_failure("bad response")
            raise BackendError(f"{self.name} bad response: {e}")


def build_backend(name: str, config: dict) -> BaseBackend:
    """Factory: config type → backend instance."""
    t = config.get("type", "ollama")
    if t == "openai":
        return OpenAICompatibleBackend(name, config)
    return OllamaBackend(name, config)
