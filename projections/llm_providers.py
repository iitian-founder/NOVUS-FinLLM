"""
LangChain chat model factories for multiple providers.

Uses first-party integrations where LangChain provides them:
  - OpenAI: langchain_openai.ChatOpenAI
  - Google Gemini: langchain_google_genai.ChatGoogleGenerativeAI
  - Anthropic Claude: langchain_anthropic.ChatAnthropic
  - xAI Grok: langchain_xai.ChatXAI
  - DeepSeek: langchain_deepseek.ChatDeepSeek

Optional unified entrypoint: langchain.chat_models.init_chat_model for openai / anthropic / google_genai.
See https://docs.langchain.com/oss/python/langchain/models
"""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

ProviderName = Literal["openai", "gemini", "grok", "deepseek", "claude"]

# Defaults (override with env vars or pass model= explicitly)
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
_DEFAULT_GROK_MODEL = "grok-4.1-fast"
_DEFAULT_DEEPSEEK_MODEL = "deepseek-v3.2-exp"
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def get_openai_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """OpenAI chat models via langchain_openai.ChatOpenAI. Uses OPENAI_API_KEY if api_key omitted."""
    return ChatOpenAI(
        model=model or os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL),
        temperature=temperature,
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
        **kwargs,
    )


def get_gemini_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0,
    google_api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Google Gemini via langchain_google_genai.ChatGoogleGenerativeAI."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model or os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL),
        temperature=temperature,
        google_api_key=google_api_key or os.getenv("GOOGLE_API_KEY"),
        **kwargs,
    )


def get_grok_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """xAI Grok via langchain_xai.ChatXAI."""
    from langchain_xai import ChatXAI

    return ChatXAI(
        model=model or os.getenv("GROK_MODEL", _DEFAULT_GROK_MODEL),
        temperature=temperature,
        xai_api_key=api_key or os.getenv("XAI_API_KEY"),
        **kwargs,
    )


def get_deepseek_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """DeepSeek via langchain_deepseek.ChatDeepSeek."""
    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=model or os.getenv("DEEPSEEK_MODEL", _DEFAULT_DEEPSEEK_MODEL),
        temperature=temperature,
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        **kwargs,
    )


def get_claude_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Anthropic Claude via langchain_anthropic.ChatAnthropic."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model or os.getenv("ANTHROPIC_MODEL", _DEFAULT_CLAUDE_MODEL),
        temperature=temperature,
        api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        **kwargs,
    )


def get_chat_model(
    provider: ProviderName,
    *,
    model: str | None = None,
    temperature: float = 0,
    **kwargs: Any,
) -> BaseChatModel:
    """Dispatch to the right factory by provider name."""
    factories = {
        "openai": get_openai_chat_model,
        "gemini": get_gemini_chat_model,
        "grok": get_grok_chat_model,
        "deepseek": get_deepseek_chat_model,
        "claude": get_claude_chat_model,
    }
    fn = factories[provider]
    return fn(model=model, temperature=temperature, **kwargs)


def init_chat_model_unified(
    model_id: str,
    *,
    temperature: float = 0,
    **kwargs: Any,
) -> BaseChatModel:
    """
    LangChain's built-in initializer: provider embedded in model_id, e.g.
      "openai:gpt-4o-mini", "anthropic:claude-sonnet-4-6", "google_genai:gemini-2.0-flash"
    Does not cover Grok/DeepSeek; use get_grok_chat_model / get_deepseek_chat_model for those.
    """
    from langchain.chat_models import init_chat_model

    return init_chat_model(model_id, temperature=temperature, **kwargs)
