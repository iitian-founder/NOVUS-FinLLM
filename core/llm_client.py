"""
novus_v3/core/llm_client.py — Unified LLM Client with Tool Calling

Replaces your current call_deepseek() which only supports:
    response_text = call_deepseek(system_prompt, user_content)

This supports:
    1. Simple calls (backward compatible)
    2. Tool/function calling (DeepSeek + OpenAI compatible)
    3. Multi-turn conversations
    4. Reasoning trace extraction (<think> tags)
    5. Automatic retry with exponential backoff
"""

import json
import time
import re
import os
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMResponse:
    """Structured response from any LLM call."""
    content: str = ""
    thinking: Optional[str] = None        # DeepSeek R1 <think> trace
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = "stop"           # "stop" | "tool_calls" | "length"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def is_final(self) -> bool:
        """True if the model produced a final answer (no more tool calls needed)."""
        return not self.has_tool_calls


class LLMClient:
    """
    Unified client for DeepSeek R1 / V3 with function calling.
    
    Uses the OpenAI-compatible API that DeepSeek provides.
    Drop-in replacement for your current call_deepseek().
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "deepseek-chat",
        max_retries: int = 3,
        timeout: int = 120,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
            except ImportError:
                raise ImportError("pip install openai — required for DeepSeek API access")
        return self._client

    # ── Simple call (backward compatible with your current call_deepseek) ──

    def call_simple(self, system_prompt: str, user_content: str) -> str:
        """Drop-in replacement for call_deepseek(system_prompt, user_content)."""
        response = self.call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        return response.content

    # ── Full call with tool support ──

    def call(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Full LLM call with tool/function calling support.
        
        Args:
            messages: Conversation history [{role, content}, ...]
            tools: Tool definitions for function calling
            temperature: 0.0-1.0 (use 0.1 for analytical tasks)
            max_tokens: Max output tokens
            
        Returns:
            LLMResponse with content, tool_calls, thinking trace, etc.
        """
        client = self._get_client()

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start = time.time()
                raw = client.chat.completions.create(**kwargs)
                latency = int((time.time() - start) * 1000)

                msg = raw.choices[0].message
                content = msg.content or ""
                finish = raw.choices[0].finish_reason or "stop"

                # Extract <think> reasoning trace
                thinking = None
                think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
                if think_match:
                    thinking = think_match.group(1).strip()
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                # Extract tool calls
                tool_calls = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                        tool_calls.append({
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": args,
                        })

                usage = raw.usage
                return LLMResponse(
                    content=content,
                    thinking=thinking,
                    tool_calls=tool_calls,
                    finish_reason="tool_calls" if tool_calls else finish,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    latency_ms=latency,
                )

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    print(f"[LLM] Attempt {attempt} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)

        return LLMResponse(
            content=f"[LLM ERROR after {self.max_retries} retries] {last_error}",
            finish_reason="error",
        )


# ── Module-level singleton ────────────────────────────────────────────────

_default_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
