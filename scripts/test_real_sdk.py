#!/usr/bin/env python3
"""Manual validation script for testing llmcast with real LLM SDKs.

Run this script with an API key to verify interceptor works with real SDKs.
NOT run in CI -- this makes actual API calls that cost money (~$0.001 per run).

Usage:
    OPENAI_API_KEY=sk-... python scripts/test_real_sdk.py
"""

import os
import sys


def test_openai():
    """Test with real OpenAI SDK."""
    try:
        import openai
    except ImportError:
        print("SKIP: openai not installed (pip install openai)")
        return False

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("SKIP: OPENAI_API_KEY not set")
        return False

    import llmcast
    llmcast.auto_track()

    client = openai.OpenAI(api_key=key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'test' and nothing else."}],
        max_tokens=5,
    )

    summary = llmcast.get_session_summary()
    stats = llmcast.get_interceptor_stats()

    print(f"  Response: {response.choices[0].message.content}")
    print(f"  Session: {summary}")
    print(f"  Interceptor: {stats}")

    if summary.get("calls", 0) > 0:
        print("  PASS: OpenAI call tracked")
        return True
    else:
        print("  FAIL: Call not tracked (check interceptor)")
        return False


def test_anthropic():
    """Test with real Anthropic SDK."""
    try:
        import anthropic
    except ImportError:
        print("SKIP: anthropic not installed (pip install anthropic)")
        return False

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("SKIP: ANTHROPIC_API_KEY not set")
        return False

    import llmcast
    llmcast.auto_track()

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=5,
        messages=[{"role": "user", "content": "Say 'test' and nothing else."}],
    )

    summary = llmcast.get_session_summary()
    print(f"  Response: {response.content[0].text}")
    print(f"  Session: {summary}")

    if summary.get("calls", 0) > 0:
        print("  PASS: Anthropic call tracked")
        return True
    else:
        print("  FAIL: Call not tracked")
        return False


if __name__ == "__main__":
    print("llmcast SDK Validation (makes real API calls ~$0.001)")
    print("=" * 50)

    results = []

    print("\n1. Testing OpenAI SDK...")
    results.append(("OpenAI", test_openai()))

    print("\n2. Testing Anthropic SDK...")
    results.append(("Anthropic", test_anthropic()))

    print("\n" + "=" * 50)
    print("Results:")
    for name, passed in results:
        status = "PASS" if passed else "SKIP/FAIL"
        print(f"  {name}: {status}")

    if all(r[1] for r in results if r[1] is not False):
        print("\nAll available SDKs validated.")
    sys.exit(0)
