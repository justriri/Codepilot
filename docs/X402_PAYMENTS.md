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
challenge on X Layer, settled through **OKX's own authenticated
facilitator**:

- **No/invalid payment** → the request never reaches CodePilot's
  verification pipeline. The x402 SDK returns the spec's
  `402 Payment Required` response with the payment challenge (network,
  token, amount, recipient) instead.
- **Valid payment** (verified + settled through OKX's facilitator) →
  the request flows into the existing handler exactly as before.
  Nothing in `agent/`, `server/agent_interface.py`, or the
  browser/sandbox/repair-loop pipeline was changed.

Every other route (`/api/sessions/*`, `/api/demo/verification`, the IDE
mode routes, the static frontend) is **not** gated — this only protects
the standalone Agent Interface API that's the paid marketplace surface.

## Which facilitator, and why

The payment layer settles through **OKX's own facilitator**
(`x402.http.OKXFacilitatorClient`, from the official `okxweb3-app-x402`
package — <https://web3.okx.com/build/dev-docs/payments/methods-onetime>),
not a generic third-party one. This is a correction from an earlier
version of this file, which used the generic, unauthenticated
`x402.http.HTTPFacilitatorClient` because — at the time — OKX's own dev
docs (`web3.okx.com`) were unreachable from the environment doing the
research, and the community `x402.org` facilitator directory doesn't
list X Layer or OKX at all. Once `web3.okx.com` became reachable, its
own docs confirmed:

- X Layer (`eip155:196`) is OKX's **primary supported network** for
  x402, with **USD₮0 / USDG as the default `exact`-scheme stablecoins**
  — this matches the token this deployment already uses.
- OKX ships an official Python package, **`okxweb3-app-x402`**, adding
  `OKXFacilitatorClient` / `OKXFacilitatorConfig` / `OKXAuthConfig` to
  the same `x402.http` import path.
- Authentication is OKX's standard HMAC-SHA256 API scheme —
  `OK-ACCESS-KEY` / `OK-ACCESS-SIGN` / `OK-ACCESS-TIMESTAMP` /
  `OK-ACCESS-PASSPHRASE` headers, computed from `OKX_API_KEY` /
  `OKX_SECRET_KEY` / `OKX_PASSPHRASE` — the same trio pattern used
  across OKX's exchange/wallet APIs generally.
- `base_url` defaults to `https://web3.okx.com`, calling
  `/api/v6/pay/x402/{supported,verify,settle}` underneath.

### ⚠️ Package collision: install `okxweb3-app-x402` only

`okxweb3-app-x402` is a **full fork** of the `x402` package, not an
add-on — it installs its own `x402/*.py` file tree under the same
`x402` import path as the plain community `x402` PyPI package. If both
are ever installed in the same environment, whichever installs *second*
silently overwrites the other's files on disk (pip's own metadata
doesn't notice the collision), which can quietly drop
`OKXFacilitatorClient` with no error. **Never add a bare `x402` line to
requirements.txt alongside `okxweb3-app-x402`.** This was verified
directly: uninstalling both and installing only `okxweb3-app-x402`
still exposes the full SDK surface (`x402ResourceServer`,
`ExactEvmServerScheme`, `PaymentMiddlewareASGI`, plus the OKX classes) —
see `payments/x402_middleware.py`'s imports.

## Architecture

```
payments/
  config.py       # X402Config dataclass, loaded entirely from env vars
  validation.py   # startup validation — decides whether to enable
  x402_middleware.py  # wires the OKX-authenticated x402 SDK into the app

test_x402_config_validation.py  # 20 unit tests, no network/SDK needed
test_x402_payment_gate.py       # 5 integration tests against the real
                                 # installed okxweb3-app-x402 SDK + a
                                 # local mock OKX-shaped facilitator
                                 # (see its module docstring) — including
                                 # an independent recomputation of
                                 # OK-ACCESS-SIGN to prove auth actually
                                 # wires through correctly, not just that
                                 # the mock is reachable.
```

All 25 tests pass as of this writing, run against the real
`okxweb3-app-x402` PyPI package (not mocked) — see "Local testing" below.

`server/app.py` calls `install_x402_middleware(app, load_x402_config())`
once at import time. That function:

1. Loads config from environment variables (`payments/config.py`).
2. Validates it (`payments/validation.py`) — chain ID set, `OKX_BASE_URL`
   well-formed, `OKX_API_KEY`/`OKX_SECRET_KEY`/`OKX_PASSPHRASE` present,
   token/receiver addresses are valid EVM addresses, decimals/price/
   EIP-712 name present.
3. If anything is missing or invalid, **logs a warning and returns
   without installing the middleware** — the API comes up and serves
   `/api/agent-interface/*` without a payment gate, rather than
   crashing or behaving unpredictably. This is deliberate: a
   misconfigured payment gate blocking 100% of paid traffic is worse
   than temporarily unmetered access, and it fails loudly (the warning
   names every missing field) rather than silently.
4. Only if validation passes does it construct an `OKXFacilitatorClient`,
   register it with `x402ResourceServer`, register the EVM `exact`
   scheme, and attach `PaymentMiddlewareASGI` to the app.

## Operational note: facilitator downtime

The x402 SDK's FastAPI middleware initializes its facilitator connection
lazily, on the first protected request per process (it calls the
facilitator's `GET /supported` once, then caches that it's done so).
Confirmed directly against the real SDK: if the facilitator is
unreachable at that moment, the SDK does **not** catch the resulting
network error — the request fails with an unhandled exception (a
generic 500), not a clean 402/503, and initialization is retried on the
*next* request rather than crash-looping. This is upstream SDK
behavior, not something this change patches (that would be an
unrelated-code refactor) — just be aware that an OKX facilitator outage
surfaces as 500s on the paid API, not a graceful degradation, until it
recovers.

## Environment variables

All required (except where noted), no code changes needed to
reconfigure. See `.env.example` for the annotated version.

| Variable | Meaning | This deployment's value |
|---|---|---|
| `X402_ENABLED` | Master on/off switch. | `true` (set `false` for local dev without payments) |
| `X402_CHAIN_ID` | Settlement chain (CAIP-2 `eip155:<id>`). | `196` (X Layer) |
| `OKX_BASE_URL` | OKX facilitator base URL. Has a default. | `https://web3.okx.com` (SDK's own documented default) |
| `OKX_API_KEY` | OKX API key for facilitator auth. **No default — see below.** | *(you must set this)* |
| `OKX_SECRET_KEY` | OKX API secret. **No default — see below.** | *(you must set this)* |
| `OKX_PASSPHRASE` | OKX API passphrase. **No default — see below.** | *(you must set this)* |
| `OKX_SYNC_SETTLE` | Wait for on-chain confirmation (`true`) vs. respond on submit (`false`). | `true` |
| `X402_TOKEN_ADDRESS` | ERC-20 contract for the settlement token. | `0x779Ded0c9e1022225f8E0630b35a9b54bE713736` (USD₮0, from OKX's official [xlayer-tokenlist](https://github.com/okx/xlayer-tokenlist)) |
| `X402_TOKEN_DECIMALS` | Token decimals. | `6` |
| `X402_TOKEN_SYMBOL` | Display symbol only (not sent on-chain). | `USD₮0` |
| `X402_TOKEN_EIP712_NAME` | Token contract's EIP-712 domain name, required for the `exact` scheme's EIP-3009 signature. **No default — see below.** | *(you must set this)* |
| `X402_TOKEN_EIP712_VERSION` | EIP-712 domain version. | `2` (spec default) |
| `X402_PRICE` | Flat per-call price, human units. | `0.10` |
| `X402_PAY_TO_ADDRESS` | Where payment settles. | `0xff67a208df0dd71fea796af3a334b14fa687fc3a` (CodePilot's ASP wallet) |
| `X402_MAX_TIMEOUT_SECONDS` | How long a signed authorization stays valid. | `300` |

### How to get `OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE`

These are account-specific credentials — I can't generate them for you.
Go to the **OKX Web3 Developer Portal**
(<https://web3.okx.com/onchainos/dev-portal>), connect and verify the
wallet you want to manage the API key with, and generate the key/secret/
passphrase trio there. (The portal's key-generation UI itself wasn't
visible in what I could fetch of its docs — if the flow past "connect +
verify" isn't self-explanatory, that's worth a support ticket to OKX.)

### Why `X402_TOKEN_EIP712_NAME` still has no default

OKX's docs confirm USD₮0 is the right *token*, but don't publish its
EIP-712 domain name/version. I queried the deployed contract
(`0x779Ded0c9e1022225f8E0630b35a9b54bE713736`) directly on-chain via two
independent public X Layer RPCs (`rpc.xlayer.tech`, `xlayer.drpc.org`):
`name()` returns `"USD₮0"` on both (strong, cross-verified evidence),
but the contract does **not** implement EIP-5267 (`eip712Domain()`
reverts) and has no public `version()` getter, so there's no on-chain
declaration proving that string is *also* the signing domain name (vs.
just the display name) — using `name()` as the domain name is the
near-universal pattern for EIP-3009 tokens, but isn't proven here. Set
it explicitly once you've confirmed it (e.g. via a test payment) rather
than trusting a hardcoded default.

**Separately, a real compatibility risk worth flagging**: USDT0's own
official docs (`docs.usdt0.to/technical-documentation/developer/`)
show `transferWithAuthorization` taking a single packed `bytes
signature` parameter, not the split `(v, r, s)` of vanilla EIP-3009.
If accurate, this is OKX's/the facilitator's concern (settlement
happens there, not in this codebase), but it means "supports EIP-3009"
isn't sufficient assurance — a real end-to-end test payment (see the
production checklist) is the only way to be sure USD₮0 settles
correctly through OKX's facilitator.

## Local testing

```bash
pip install -r requirements.txt

# 1. Config validation (no external services required):
pytest test_x402_config_validation.py -v

# 2. Payment-gate integration test (local mock OKX-shaped facilitator,
#    no real credentials or funds — includes an OK-ACCESS-SIGN check):
pytest test_x402_payment_gate.py -v

# 3. Run the server with the payment layer OFF (fastest local loop):
X402_ENABLED=false uvicorn server.app:app --reload
curl -X POST localhost:8000/api/agent-interface/analyze -d '{"code":"x=1"}'
# -> normal response, no payment gate involved.

# 4. Run it with the payment layer ON but genuinely unconfigured
#    (OKX_API_KEY / TOKEN_EIP712_NAME blank in .env):
uvicorn server.app:app --reload
# -> startup log shows "x402 payment layer DISABLED — invalid/incomplete
#    configuration" listing exactly what's missing; the endpoint still
#    answers normally (auto-disable, not a crash).

# 5. Once OKX_API_KEY/SECRET/PASSPHRASE + TOKEN_EIP712_NAME are filled in:
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
   / `E2B_API_KEY` etc. already live:
   - `X402_ENABLED=true`
   - `X402_CHAIN_ID=196`
   - `OKX_BASE_URL=https://web3.okx.com`
   - `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE` — from the OKX
     Developer Portal (see above)
   - `OKX_SYNC_SETTLE=true`
   - `X402_TOKEN_ADDRESS=0x779Ded0c9e1022225f8E0630b35a9b54bE713736`
   - `X402_TOKEN_DECIMALS=6`
   - `X402_TOKEN_SYMBOL=USD₮0`
   - `X402_TOKEN_EIP712_NAME` — verify before setting (see above)
   - `X402_TOKEN_EIP712_VERSION=2`
   - `X402_PRICE=0.10`
   - `X402_PAY_TO_ADDRESS=0xff67a208df0dd71fea796af3a334b14fa687fc3a`
   - `X402_MAX_TIMEOUT_SECONDS=300`

   Leave `OKX_API_KEY`/`SECRET`/`PASSPHRASE` and `X402_TOKEN_EIP712_NAME`
   unset until verified — the app boots fine either way, just without
   the payment gate.
2. No changes to `procfile` are needed — it already runs
   `uvicorn server.app:app --host 0.0.0.0 --port $PORT`, and
   `requirements.txt` now includes `okxweb3-app-x402[fastapi,httpx,evm]`
   (not the plain `x402` package — see the collision warning above), so
   a normal Railway redeploy picks it up.
3. After deploying, check the Railway logs for the `payments.x402`
   logger line on startup — it tells you definitively whether the
   payment gate is enabled or disabled (and why), and which facilitator
   base URL it's using.
4. Confirm `https://codepilot.up.railway.app/api/agent-interface/analyze`
   (the endpoint registered on OKX AI) returns `402` for an unpaid
   `POST` once the gate is enabled — see the production checklist below.

## A2MCP marketplace compatibility

This deployment's `accepts[]` entry (`scheme: "exact"`, `network:
"eip155:196"`, asset `USD₮0`, `payTo` = CodePilot's registered ASP
wallet address) matches exactly what CodePilot's OKX AI listing already
declares (0.10 USDT per verification request, X Layer). Routing
settlement through OKX's own facilitator — rather than a third-party
one whose X Layer/USD₮0 support was never confirmed — is the change
most directly relevant to marketplace compatibility: it's the
facilitator OKX's own docs point sellers at for this exact network/token
combination. The one open item is the `X402_TOKEN_EIP712_NAME` value
(see above) — everything else lines up with the registered listing.

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
      body (not a 402). This is also the real-world test of the
      USDT0 signature-shape question above — if it settles, it settles.
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
