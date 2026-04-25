"""
LLM factory for the AI-Investment Swarm.

Provides a single entry point (get_llm) that constructs a configured
ChatGoogleGenerativeAI instance from project Settings.  Using a factory
rather than constructing LLM objects ad-hoc ensures that:
  - API key validation happens at agent call-time (not import-time)
  - Model selection is controlled by per-agent Settings fields
  - Tests can call get_llm() with a mock key for smoke-tests

Usage::

    from lockin.agents.llm import get_llm, MODEL_PRO, MODEL_FLASH

    llm = get_llm(model=MODEL_FLASH, temperature=0.1)
    response = llm.invoke([HumanMessage(content="hello")])
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from lockin.utils.config import get_settings

# ---------------------------------------------------------------------------
# Model name constants — use these everywhere instead of raw strings so that
# model upgrades only require changing one place.
# ---------------------------------------------------------------------------

MODEL_PRO = "gemini-2.5-pro"
MODEL_FLASH = "gemini-2.5-flash"


def get_llm(
    model: str = MODEL_FLASH,
    temperature: float = 0.1,
) -> ChatGoogleGenerativeAI:
    """Return a configured ChatGoogleGenerativeAI instance.

    Args:
        model: Gemini model identifier. Defaults to MODEL_FLASH for cost efficiency.
            Use MODEL_PRO for agents requiring higher reasoning quality.
        temperature: Sampling temperature. Low values (0.0-0.2) produce
            deterministic, analytical outputs suitable for financial reasoning.

    Returns:
        ChatGoogleGenerativeAI ready for .invoke() / .stream() calls.

    Raises:
        ValueError: If GOOGLE_API_KEY is not configured in settings.
    """
    google_api_key = get_settings().google_api_key
    if not google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY not configured. "
            "Set GOOGLE_API_KEY in .env or environment before calling get_llm()."
        )

    # Gemini 2.5 Pro free tier was restricted to 0 RPD after 2026-04-01.
    # Fall back to Flash when Pro is requested but unavailable (free tier).
    if model == MODEL_PRO:
        import os

        if os.environ.get("GEMINI_FORCE_FLASH", "").lower() in ("1", "true"):
            import logging

            logging.getLogger(__name__).info(
                "GEMINI_FORCE_FLASH=true — using %s instead of %s",
                MODEL_FLASH,
                MODEL_PRO,
            )
            model = MODEL_FLASH

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=google_api_key,
        temperature=temperature,
    )
