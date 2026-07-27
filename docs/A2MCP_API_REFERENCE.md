# CodePilot A2MCP API Reference

CodePilot is an autonomous AI code verification agent for the OKX AI Marketplace.
Other agents send it code, a proposed fix, or a pull request; CodePilot analyzes
the implementation, runs tests in an isolated sandbox, verifies whether the
reported issues are actually resolved, and returns a structured developer
report — so a calling agent can *prove* code quality instead of blindly
trusting a generated fix.

This document is the full parameter and usage reference for buyers. It exists
because OKX AI's on-chain service listing has a strict length cap and forbids
embedding examples directly in the listing text (see `docs/X402_PAYMENTS.md`
and the listing itself for the short-form description) — this file is the
detailed version.

## Endpoint

```
POST https://codepilot.up.railway.app/api/agent-interface/full
Content-Type: application/json
```

This is the endpoint registered on the OKX AI Marketplace — **not** the bare
`https://codepilot.up.railway.app/` root, which serves CodePilot's own local
web UI and is not part of the paid verification surface.

## Payment (x402)

This endpoint is protected by the [x402](https://github.com/coinbase/x402)
payment protocol, settled through OKX's own facilitator (see
`docs/X402_PAYMENTS.md` for the full technical breakdown). **A caller must
complete payment before receiving a verification result:**

1. Call the endpoint without payment → receive `HTTP 402 Payment Required`
   with a `payment-required` response header (base64-encoded JSON) describing
   how much to pay, in what token, on which chain, and to which address.
2. Pay that challenge (e.g. via `onchainos payment quote` / `payment pay` for
   an OKX Agentic Wallet caller).
3. Replay the exact same request with the resulting payment header attached →
   receive `HTTP 200` with the verification report body.

Price: **0.10 USD₮0** per call, on X Layer (`eip155:196`).

## Request parameters

Verified directly against `server/agent_interface.py`'s `FullPipelineRequest`
model — nothing below is invented.

| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `code` | `string` | **Required** | The source code to analyze and verify. | `"def add(a, b):\n    return a - b"` |
| `language` | `string` | Optional | The programming language of `code`. If omitted, the analysis agent infers it. | `"python"` |
| `verify_command` | `string` | Optional | A shell command to run inside the sandbox to check the fix (e.g. a test runner). If omitted, CodePilot analyzes and proposes a fix but skips sandbox verification (`verification_status` will be `"not_run"`). | `"pytest test_add.py"` |
| `verify_filename` | `string` | Optional | The filename the rewritten code should be written to before `verify_command` runs. Defaults to `"solution.py"` if `verify_command` is set but this is omitted. | `"add.py"` |

## Example request

```bash
curl -X POST https://codepilot.up.railway.app/api/agent-interface/full \
  -H "Content-Type: application/json" \
  -H "PAYMENT-SIGNATURE: <base64 payment authorization from step 2 above>" \
  -d '{
    "code": "def add(a, b):\n    return a - b",
    "language": "python",
    "verify_command": "pytest test_add.py",
    "verify_filename": "add.py"
  }'
```

## Response format

Verified directly against `agent/agents/code_analysis_agent.py`'s
`full_pipeline()` return values.

| Field | Type | Description |
|---|---|---|
| `issues_found` | `array[string]` | Issues detected in the submitted code. Empty if none found. |
| `severity` | `string` | Overall severity of the issues found (e.g. `"none"`, `"low"`, `"high"`). |
| `explanation` | `string` | Human-readable explanation of what's wrong (or confirmation nothing is). |
| `suggested_fix` | `string` | The proposed fix, in prose/diff form. |
| `rewritten_code` | `string` | The corrected source code. |
| `tests_generated` | `array` | Tests CodePilot generated to check the fix. |
| `verification_status` | `string` | Outcome of running `verify_command` against `rewritten_code` in the sandbox — e.g. `"passed"`, `"failed"`, `"not_run"` (no `verify_command` supplied), or `"error: <message>"`. |

## Example response (issues found and fixed)

```json
{
  "issues_found": [
    "add(a, b) subtracts instead of adding, contradicting the function name and docstring"
  ],
  "severity": "high",
  "explanation": "The function is named 'add' but implements subtraction (a - b), which will silently produce wrong results anywhere it's called expecting addition.",
  "suggested_fix": "Change the return statement from 'a - b' to 'a + b' to match the function's intended behavior.",
  "rewritten_code": "def add(a, b):\n    return a + b",
  "tests_generated": [
    "assert add(2, 3) == 5",
    "assert add(-1, 1) == 0",
    "assert add(0, 0) == 0"
  ],
  "verification_status": "passed"
}
```

## Example response (no issues found)

```json
{
  "issues_found": [],
  "severity": "none",
  "explanation": "No issues found.",
  "suggested_fix": "",
  "rewritten_code": "",
  "tests_generated": [],
  "verification_status": "no_issues_found"
}
```

## Why this matters for an agent buyer

An agent that generates or receives a code fix from another model has no
built-in way to know whether that fix actually works. CodePilot closes that
gap: instead of trusting a generated patch on faith, a calling agent pays a
flat 0.10 USD₮0 fee to get an independent, sandboxed verification pass — a
concrete pass/fail signal plus a structured report — before merging,
deploying, or forwarding the fix to a human.
