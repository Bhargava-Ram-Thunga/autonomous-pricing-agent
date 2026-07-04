"""Gemini via Google's OpenAI-compatible endpoint.
Uses ChatOpenAI to bypass google-genai SDK's AFC issue.
"""
import os


def build():
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    key   = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model=model,
        api_key=key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        temperature=0.1,
    )
    print(f"[gemini] model: {model} (OpenAI-compat endpoint)")
    return llm
