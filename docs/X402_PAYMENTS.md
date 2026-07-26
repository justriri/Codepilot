# x402 Payment Layer

CodePilot is listed on the OKX AI Marketplace as a paid A2MCP service
(0.10 USD₮0 per verification request). This document covers the payment
gate that enforces that: how it's built, how to configure it, and how
to deploy and test it.

## What it does

Every `POST /api/agent-interface/*` route (`analyze`, `explain`,
`suggest-fix`, `rewrite`, `verify`, `full`, `execute`, `generate-tests`,
`run-tests` — see `server/agent_interface.py`) is gated behind an
[x402](https://github.com/coinbase/x402) `exact`-scheme payment
challenge on X Layer:

- **No/invalid payment** → the request never reaches CodePilot's
  verification pipeline. The official x402 SDK returns the spec's
  `402 Payment Required` response with the payment challenge (network,
  token, amount, recipient) instead.
- **Valid payment** (verified + settled through the configured
  facilitator) → the request flows into the existing handler exactly as
  before. Nothing in `agent/`, `server/agent_interface.py`, or the
  browser/sandbox/repair-loop pipeline was changed.

Every other route (`/api/sessions/*`, `/api/demo/verification`, the IDE
mode routes, the static frontend) is **not** gated — this only protects
the standalone Agent Interface API that's the paid marketplace surface.

## Architecture

```
payments/
  config.py       # X402Config dataclass, loaded entirely from env vars
  validation.py   # startup validation — decides whether to enable
  x402_middleware.py  # wires the official x402 SDK into the FastAPI app

test_x402_config_validation.py  # 18 unit tests, no network/SDK needed
test_x402_payment_gate.py       # 5 integration tests against the real
                                 # installed x402 SDK + a local mock
                                 # facilitator (see its module docstring)
```

All 23 tests pass as of this writing, run against the real `x402` PyPI
package (not mocked) — see "Local testing" below.

`server/app.py` calls `install_x402_middleware(app, load_x402_config())`
once at import time. That function:

1. Loads config from environment variables (`payments/config.py`).
2. Validates it (`payments/validation.py`) — chain ID set, facilitator
   URL set and well-formed, token/receiver addresses are valid EVM
   addresses, decimals/price/EIP-712 name present.
3. If anything is missing or invalid, **logs a warning and returns
   without installing the middleware** — the API comes up and serves
   `/api/agent-interface/*` without a payment gate, rather than
   crashing or behaving unpredictably. This is deliberate: a
   misconfigured payment gate blocking 100% of paid traffic is worse
   than temporarily unmetered access, and it fails loudly (the warning
   names every missing field) rather than silently.
4. Only if validation passes does it construct the `x402ResourceServer`,
   register the EVM `exact` scheme, and attach
   `PaymentMiddlewareASGI` to the app.

## Operational note: facilitator downtime

The x402 SDK's FastAPI middleware initializes its facilitator connection
lazily, on the first protected request per process (it calls the
facilitator's `GET /supported` once, then caches that it's done so).
Confirmed directly (see the `ConnectError` case while building
`test_x402_payment_gate.py`): if the facilitator is unreachable at that
moment, the SDK does **not** catch the resulting network error — the
request fails with an unhandled exception (a generic 500), not a clean
402/503, and initialization is retried on the *next* request rather than
crash-looping. This is upstream SDK behavior, not something this change
patches (that would be an unrelated-code refactor) — just be aware that
a facilitator outage surfaces as 500s on the paid API, not a graceful
degradation, until it recovers. Monitor the configured facilitator's
uptime accordingly.

## Environment variables

All required, no code changes needed to reconfigure. See `.env.example`
for the annotated version.

| Variable | Meaning | This deployment's value |
|---|---|---|
| `X402_ENABLED` | Master on/off switch. | `true` (set `false` for local dev without payments) |
| `X402_CHAIN_ID` | Settlement chain (CAIP-2 `eip155:<id>`). | `196` (X Layer) |
| `X402_FACILITATOR_URL` | Facilitator that verifies + settles payments. **No default — see below.** | *(you must set this)* |
| `X402_TOKEN_ADDRESS` | ERC-20 contract for the settlement token. | `0x779Ded0c9e1022225f8E0630b35a9b54bE713736` (USD₮0, from OKX's official [xlayer-tokenlist](https://github.com/okx/xlayer-tokenlist)) |
| `X402_TOKEN_DECIMALS` | Token decimals. | `6` |
| `X402_TOKEN_SYMBOL` | Display symbol only (not sent on-chain). | `USD₮0` |
| `X402_TOKEN_EIP712_NAME` | Token contract's EIP-712 domain name, required for the `exact` scheme's EIP-3009 signature. **No default — see below.** | *(you must set this)* |
| `X402_TOKEN_EIP712_VERSION` | EIP-712 domain version. | `2` (spec default) |
| `X402_PRICE` | Flat per-call price, human units. | `0.10` |
| `X402_PAY_TO_ADDRESS` | Where payment settles. | `0xff67a208df0dd71fea796af3a334b14fa687fc3a` (CodePilot's ASP wallet) |
| `X402_MAX_TIMEOUT_SECONDS` | How long a signed authorization stays valid. | `300` |

### Why `X402_FACILITATOR_URL` has no default

As of this writing, **x402.org's official facilitator directory does
not list X Layer or OKX** (checked at `docs.x402.org/dev-tools/facilitators`).
X Layer's official account has publicly acknowledged a third-party
permissionless facilitator (referred to online as "openx402") adding
X Layer + OKX Wallet support, but there is no stable documentation page
or citable endpoint URL for it — only a social-media mention — so it is
**not** hardcoded here. Before enabling payments in production:

1. Verify a facilitator that actually supports `eip155:196` + the
   USD₮0 contract above (test its `/verify` and `/settle` endpoints
   directly, or via a real `onchainos payment quote`/`pay` round-trip).
2. Set `X402_FACILITATOR_URL` to it.
3. Coinbase's public facilitator (`https://x402.org/facilitator`) is
   the documented default for the SDK's own examples, but is
   documented as serving Base/Base Sepolia — do not assume it settles
   X Layer without testing first.

### Why `X402_TOKEN_EIP712_NAME` has no default

The `exact` scheme signs an EIP-3009 `transferWithAuthorization`
message, which is bound to the token contract's own EIP-712 domain
`name` (and `version`). Using the wrong domain name makes every
signature invalid against the real contract — this can't be safely
guessed. Read it directly from the contract before deploying:

- On [OKLink's X Layer explorer](https://www.oklink.com/x-layer), open
  the USD₮0 contract → "Contract" → "Read Contract" → call `name()`
  (and `EIP712_DOMAIN()` / `version()` if exposed) and use the exact
  returned string.

## Local testing

```bash
pip install -r requirements.txt

# 1. Config validation (no external services required):
pytest test_x402_config_validation.py -v

# 2. Payment-gate integration test (mock facilitator, no real funds):
pytest test_x402_payment_gate.py -v

# 3. Run the server with the payment layer OFF (fastest local loop):
X402_ENABLED=false uvicorn server.app:app --reload
curl -X POST localhost:8000/api/agent-interface/analyze -d '{"code":"x=1"}'
# -> normal response, no payment gate involved.

# 4. Run it with the payment layer ON but genuinely unconfigured
#    (FACILITATOR_URL / TOKEN_EIP712_NAME blank in .env):
uvicorn server.app:app --reload
# -> startup log shows "x402 payment layer DISABLED — invalid/incomplete
#    configuration" listing exactly what's missing; the endpoint still
#    answers normally (auto-disable, not a crash).

# 5. Once FACILITATOR_URL + TOKEN_EIP712_NAME are filled in and verified:
uvicorn server.app:app --reload
curl -i -X POST localhost:8000/api/agent-interface/analyze -d '{"code":"x=1"}'
# -> HTTP 402 with an EMPTY body and a `payment-required` response
#    header: base64 JSON containing {x402Version, accepts: [{scheme,
#    network, asset, amount, payTo, extra}]}. Decode it locally with:
#    python -c "import base64,json,sys; print(json.dumps(json.loads(base64.b64decode(sys.argv[1])),indent=2))" "<header value>"
```

Confirmed directly against the installed SDK (see `test_x402_payment_gate.py`) — the challenge rides in the `payment-required` header, not the JSON body, which matches what `onchainos payment quote` (the buyer-side CLI) expects to parse.

## Railway deployment

1. Add the new environment variables from the table above to the
   Railway service (Project → Variables) — same place `DEEPSEEK_API_KEY`
   / `E2B_API_KEY` etc. already live. Leave `X402_FACILITATOR_URL` and
   `X402_TOKEN_EIP712_NAME` unset until you've verified them (per above)
   — the app will boot fine either way, just without the payment gate.
2. No changes to `procfile` are needed — it already runs
   `uvicorn server.app:app --host 0.0.0.0 --port $PORT`, and
   `requirements.txt` now includes `x402[fastapi,httpx,evm]`, so a
   normal Railway redeploy picks it up.
3. After deploying, check the Railway logs for the `payments.x402`
   logger line on startup — it tells you definitively whether the
   payment gate is enabled or disabled (and why).
4. Confirm `https://codepilot.up.railway.app/api/agent-interface/analyze`
   (the endpoint registered on OKX AI) returns `402` for an unpaid
   `POST` once the gate is enabled — see the production checklist below.

## Production testing checklist

- [ ] `pytest test_x402_config_validation.py test_x402_payment_gate.py`
      passes locally.
- [ ] Startup log on Railway shows `x402 payment layer ENABLED` (not a
      "DISABLED" warning) — confirms every env var is present and valid.
- [ ] **Unpaid request**: `curl -i -X POST
      https://codepilot.up.railway.app/api/agent-interface/analyze -d '{"code":"x=1"}'`
      returns `HTTP/1.1 402 Payment Required` with an empty body and a
      `payment-required` header — base64-decode it and confirm
      `accepts[]` contains `scheme: "exact"`, `network: "eip155:196"`,
      the USD₮0 asset address, the configured amount, and the pay-to
      address — do **not** see CodePilot's analysis output.
- [ ] **Paid request**: from a funded OKX Agentic Wallet, run
      `onchainos payment quote https://codepilot.up.railway.app/api/agent-interface/analyze --method POST`
      then confirm and `onchainos payment pay --payment-id <id> --selected-index <n> --yes`
      — expect `status: "success"` with a real `txHash`, and the
      replayed request returns CodePilot's normal `analyze` response
      body (not a 402).
- [ ] **Existing functionality unaffected**: with the same paid
      request's response, verify the JSON shape matches what
      `/api/agent-interface/analyze` returned before this change
      (`issues_found` / `severity` / `explanation` etc.) — the payment
      layer must be transparent to the business logic.
- [ ] Confirm the receiving address (`0xff67a208df0dd71fea796af3a334b14fa687fc3a`)
      shows the incoming USD₮0 transfer on
      [OKLink](https://www.oklink.com/x-layer) after settlement.
- [ ] Re-run the unpaid-request check once more after a paid one, to
      confirm the gate re-applies per-request rather than "unlocking"
      after a single payment.
