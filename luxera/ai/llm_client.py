from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class LLMClient:
    """
    Minimal HTTP client for the Anthropic Messages API.
    No external dependencies — uses only urllib from the standard library.
    API key from ANTHROPIC_API_KEY env var.
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Set environment variable or pass api_key.")

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Send a message to the Anthropic API and return the response.

        Uses tool_use if tools are provided. The response will contain
        content blocks that may include tool_use blocks.

        Returns the full API response as a dict.
        Raises ValueError on API error.
        """
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise ValueError(f"API error {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise ValueError(f"Network error: {e}") from e

    def extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract tool_use blocks from API response.
        Returns list of {"name": str, "input": dict} for each tool call.
        """
        calls: List[Dict[str, Any]] = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append({"name": str(block.get("name", "")), "input": dict(block.get("input", {}) or {})})
        return calls

    def extract_text(self, response: Dict[str, Any]) -> str:
        """Extract concatenated text blocks from response."""
        return "\n".join(
            str(block.get("text", ""))
            for block in response.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
