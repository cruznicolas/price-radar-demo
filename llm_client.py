"""
llm_client.py — Thin wrapper around the Anthropic SDK for the Price Radar LLM layer.

Usage:
    from llm_client import summarize

    text = summarize(
        system="You are a market analyst.",
        user="Here are the KPIs: ...",
        cfg={"enabled": True, "model": "claude-haiku-4-5-20251001",
             "api_key_env": "ANTHROPIC_API_KEY", "timeout_seconds": 8,
             "stub_mode": False}
    )
    # Returns a string on success, or None on failure / disabled.

Architecture contract
---------------------
• This module is the ONLY file in the repo that imports `anthropic`.
• It is called exclusively by llm_briefing.py and llm_enrichment.py.
• build_dashboard.py and notifications.py NEVER import this module.
• All LLM calls produce text that is written to output/llm_cache/ by
  the caller.  This module never writes to disk.
"""

import os
from typing import Optional

_STUB_TEXT = (
    "[STUB] Market summary: The Chilean auto-insurance market remained "
    "stable over the past 7 days. No significant floor moves were detected "
    "on either monitored portal. Sura and Fid continued to show above-average "
    "price volatility. Hdi held the cheapest position on Falabella for the "
    "majority of the period."
)


def summarize(
    system: str,
    user: str,
    cfg: dict,
    *,
    stub: bool = False,
) -> Optional[str]:
    """
    Call the LLM and return the assistant reply as a plain string.

    Parameters
    ----------
    system : str
        System prompt / persona.
    user : str
        User message (the KPI context or alert context).
    cfg : dict
        The `llm` block from config.json.
        Expected keys: enabled, model, api_key_env, timeout_seconds, stub_mode.
    stub : bool
        If True, bypass the API and return a canned stub string regardless of
        cfg.stub_mode.  Passed explicitly for CLI --stub flags.

    Returns
    -------
    str | None
        The LLM response text, or None if disabled / failed / timed out.
    """
    if not cfg.get("enabled", False):
        return None

    if stub or cfg.get("stub_mode", False):
        return _STUB_TEXT

    api_key = os.environ.get(cfg.get("api_key_env", "ANTHROPIC_API_KEY"), "")
    if not api_key:
        print("  llm_client: ANTHROPIC_API_KEY not set — skipping LLM call")
        return None

    timeout = float(cfg.get("timeout_seconds", 8))
    model   = cfg.get("model", "claude-haiku-4-5-20251001")

    try:
        import anthropic  # lazy import so non-LLM scripts don't require the package
        import httpx

        client = anthropic.Anthropic(
            api_key=api_key,
            http_client=httpx.Client(timeout=timeout),
        )
        message = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        print(f"  llm_client: call failed ({type(exc).__name__}: {exc})")
        return None
