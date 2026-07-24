"""
DeepSeek connection test — no sandbox required.

Tests the provider layer in isolation: constructs a DeepSeekProvider
from your .env config and calls its semantic methods
(analyze_code/explain_error/suggest_fix/rewrite_code) against a real,
intentionally buggy code snippet. This is the fast sanity check to run
BEFORE the full E2B pipeline test — if your DeepSeek API key
or connection is wrong, you'll find out in seconds here rather than
after a cloud sandbox has already been created.

Requires: DEEPSEEK_API_KEY set in .env. Does NOT require DEFAULT_MODEL
to be set to deepseek — this script always uses DeepSeek explicitly,
regardless of what your .env's active provider is, so you can sanity
check DeepSeek specifically without changing your default.

Usage:
    python test_deepseek_connection.py
"""

import sys

from agent.config import load_config
from providers.deepseek_provider import DeepSeekProvider
from providers.base_provider import ProviderError

BUGGY_CODE = """def calculate_average(numbers):
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

result = calculate_average([])
print(result)
"""


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main():
    section("STEP 1: Load config and construct DeepSeekProvider directly")
    config = load_config()

    if not config.deepseek_api_key:
        print("FAILED: DEEPSEEK_API_KEY is not set in your .env file.")
        print("Fix: add DEEPSEEK_API_KEY=sk-...your real key... to .env")
        sys.exit(1)

    provider = DeepSeekProvider(api_key=config.deepseek_api_key, model=config.deepseek_model)
    print(f"Provider: {provider.name}")
    print(f"Model: {provider.model}")
    print(f"Base URL: {provider._client.base_url}")

    section("STEP 2: analyze_code() — a real API call, no tools, single-shot")
    print("Analyzing this intentionally buggy code:")
    print(BUGGY_CODE)
    try:
        analysis = provider.analyze_code(BUGGY_CODE, language="python")
    except ProviderError as e:
        print(f"FAILED: DeepSeek returned an error: {e}")
        print("Common causes: invalid API key, insufficient balance, network/firewall blocking api.deepseek.com")
        sys.exit(1)
    except Exception as e:
        print(f"FAILED: unexpected error: {e}")
        sys.exit(1)

    print("Response:")
    print(analysis)

    if analysis.get("parse_error"):
        print()
        print("NOTE: the model responded but not in the exact JSON shape expected.")
        print("The connection itself works (see raw_response above) — this would just")
        print("need prompt tuning, not a connectivity fix.")
    else:
        print()
        print(f"issues_found: {analysis.get('issues_found')}")
        print(f"severity: {analysis.get('severity')}")

    section("STEP 3: suggest_fix() — confirm a second real call works too")
    try:
        fix = provider.suggest_fix(
            BUGGY_CODE,
            issue_description="Dividing by len(numbers) crashes with ZeroDivisionError when the list is empty.",
            language="python",
        )
        print(fix)
    except ProviderError as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    section("RESULT")
    print("DeepSeek connection is working: real API calls succeeded and returned")
    print("structured analysis of real buggy code, with no sandbox involved.")


if __name__ == "__main__":
    main()
