# llm_clients.py — LLM API clients for Novus FinLLM
"""
Centralized LLM client configuration and call wrappers.
Supports DeepSeek (via OpenAI-compatible API) and Google Gemini.
"""

import os
import time
import json as _json
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")

# Configure the DeepSeek API client
_ENABLE_DEEPSEEK_DEBUG_LOGS = os.getenv("ENABLE_DEEPSEEK_DEBUG_LOGS", "false").lower() in ("1", "true", "yes", "on")
client = OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com")
deepseek_model_name = 'deepseek-chat'

# Configure the Gemini API client
_ENABLE_GEMINI_DEBUG_LOGS = os.getenv("ENABLE_GEMINI_DEBUG_LOGS", "false").lower() in ("1", "true", "yes", "on")
if gemini_api_key and gemini_api_key != "replace_me":
    genai.configure(api_key=gemini_api_key)
    gemini_client = True
else:
    gemini_client = None


def call_gemini(prompt, text_to_analyze, send_financials=False, financial_data=None, extra_context=None):
    """Calls the Gemini API with a specific prompt and text, optionally including financial data."""
    if gemini_client is None:
        return "Error: Gemini API key is not configured."

    # --- Refined Prompt Construction ---
    if send_financials and financial_data:
        description = "transcripts and historical financial statements"
        content_to_send = f"{text_to_analyze}\n\n---\n\n{financial_data}"
    else:
        description = "transcripts"
        content_to_send = text_to_analyze

    if extra_context:
        content_to_send = f"{content_to_send}\n\n---\n\nPrior context from previous step:\n{extra_context}"

    full_prompt = f"System:\n{prompt}\n\nUser Data:\n{content_to_send}"

    try:
        if _ENABLE_GEMINI_DEBUG_LOGS:
            try:
                _debug_path = os.path.join(os.path.dirname(__file__), "gemini_input_debug.txt")
                with open(_debug_path, "a", encoding="utf-8") as _f:
                    _f.write("\n\n=== GEMINI_CALL INPUT @ " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
                    _f.write("-- send_financials: " + str(bool(send_financials)) + "\n")
                    _f.write("-- extra_context: " + ("yes" if bool(extra_context) else "no") + "\n")
                    _f.write("-- prompt:\n" + (prompt if isinstance(prompt, str) else _json.dumps(prompt, ensure_ascii=False)) + "\n")
                    _f.write("-- content_to_analyze (possibly markdown):\n" + (text_to_analyze if isinstance(text_to_analyze, str) else _json.dumps(text_to_analyze, ensure_ascii=False)) + "\n")
                    if send_financials and financial_data is not None:
                        _f.write("-- financial_data (truncated to 10k chars):\n")
                        _fd = financial_data if isinstance(financial_data, str) else _json.dumps(financial_data, ensure_ascii=False)
                        _f.write(str(_fd)[:10000] + ("...\n" if len(str(_fd)) > 10000 else "\n"))
            except Exception as _e0:
                print(f"[debug] Failed to log Gemini input: {_e0}")

        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=prompt
        )
        response = model.generate_content(
            contents=f"Here are the {description} to analyze:\n\n---\n\n{content_to_send}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=8192
            )
        )

        if _ENABLE_GEMINI_DEBUG_LOGS:
            try:
                _debug_path = os.path.join(os.path.dirname(__file__), "gemini_output_debug.txt")
                with open(_debug_path, "a", encoding="utf-8") as _f:
                    _f.write("\n\n=== GEMINI_CALL RAW OUTPUT @ " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
                    _f.write(str(response.text) + "\n")
                    _f.write("=== END RAW OUTPUT ===\n")
            except Exception as _e1:
                print(f"[debug] Failed to log Gemini output: {_e1}")

        return response.text
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        return f"Error: Could not generate content from AI. Details: {e}"


def call_deepseek(prompt, text_to_analyze, send_financials=False, financial_data=None, extra_context=None):
    """Calls the DeepSeek API with a specific prompt and text, optionally including financial data."""

    # --- Refined Prompt Construction ---
    if send_financials and financial_data:
        description = "transcripts and historical financial statements"
        content_to_send = f"{text_to_analyze}\n\n---\n\n{financial_data}"
    else:
        description = "transcripts"
        content_to_send = text_to_analyze

    if extra_context:
        content_to_send = f"{content_to_send}\n\n---\n\nPrior context from previous step:\n{extra_context}"

    user_message = f"Here are the {description} to analyze:\n\n---\n\n{content_to_send}"

    try:
        if _ENABLE_DEEPSEEK_DEBUG_LOGS:
            try:
                _debug_path = os.path.join(os.path.dirname(__file__), "deepseek_input_debug.txt")
                with open(_debug_path, "a", encoding="utf-8") as _f:
                    _f.write("\n\n=== DEEPSEEK_CALL INPUT @ " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
                    _f.write("-- send_financials: " + str(bool(send_financials)) + "\n")
                    _f.write("-- extra_context: " + ("yes" if bool(extra_context) else "no") + "\n")
                    _f.write("-- prompt:\n" + (prompt if isinstance(prompt, str) else _json.dumps(prompt, ensure_ascii=False)) + "\n")
                    _f.write("-- content_to_analyze (possibly markdown):\n" + (text_to_analyze if isinstance(text_to_analyze, str) else _json.dumps(text_to_analyze, ensure_ascii=False)) + "\n")
                    if send_financials and financial_data is not None:
                        _f.write("-- financial_data (truncated to 10k chars):\n")
                        _fd = financial_data if isinstance(financial_data, str) else _json.dumps(financial_data, ensure_ascii=False)
                        _f.write(str(_fd)[:10000] + ("...\n" if len(str(_fd)) > 10000 else "\n"))
                    _f.write("=== END INPUT ===\n")
            except Exception as _e0:
                print(f"[debug] Failed to log DeepSeek input: {_e0}")

        response = client.chat.completions.create(
            model=deepseek_model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2,
            max_tokens=8192
        )
        response_text = response.choices[0].message.content

        if _ENABLE_DEEPSEEK_DEBUG_LOGS:
            try:
                _debug_path = os.path.join(os.path.dirname(__file__), "deepseek_input_debug.txt")
                with open(_debug_path, "a", encoding="utf-8") as _f:
                    _f.write("\n=== DEEPSEEK_CALL OUTPUT @ " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
                    _f.write((response_text or "") + "\n")
                    _f.write("=== END OUTPUT ===\n")
            except Exception as _e1:
                print(f"[debug] Failed to log DeepSeek output: {_e1}")

        return response_text
    except Exception as e:
        print(f"An error occurred with the DeepSeek API: {e}")
        return f"Error: Could not generate content from AI. Details: {e}"
