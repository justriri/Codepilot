"""
Integration tests for the x402 payment gate (payments/x402_middleware.py)
against the real, installed OKX x402 SDK (`okxweb3-app-x402`).

These tests run a real local "mock OKX facilitator" HTTP server —
implementing the actual OKX endpoint shape (`/api/v6/pay/x402/supported
|verify|settle`, `{code, data, msg}` response envelope, `OK-ACCESS-*`
auth headers) rather than mocking the SDK itself — so what's being
tested is the real wire behavior CodePilot will exercise in production:
an unpaid request must get a real 402 challenge, a request carrying a
payment the facilitator accepts must reach the protected handler
unchanged, and the request must actually be signed the way OKX's own
API expects.

They run against a small synthetic FastAPI app with a dummy protected
route (not the real server/app.py) so they're isolated from unrelated
dependencies the real app needs (a configured AI provider key, E2B,
Playwright, etc.) — this file tests the payment gate in payments/, not
CodePilot's verification pipeline, which is untouched by this change.

Real settlement against OKX's actual production facilitator (with real
OKX_API_KEY/SECRET/PASSPHRASE and real funds) is exercised manually per
docs/X402_PAYMENTS.md's production checklist — that's not something a
unit test suite should depend on.
"""

import base64
import hashlib
import hmac
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from payments.config import X402Config
from payments.x402_middleware import install_x402_middleware

TOKEN_ADDRESS = "0x779Ded0c9e1022225f8E0630b35a9b54bE713736"
PAY_TO_ADDRESS = "0xff67a208df0dd71fea796af3a334b14fa687fc3a"
NETWORK = "eip155:196"
OKX_BASE_PATH = "/api/v6/pay/x402"

API_KEY = "test-api-key"
SECRET_KEY = "test-secret-key"
PASSPHRASE = "test-passphrase"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockOKXFacilitator:
    """
    A minimal stand-in for OKX's real facilitator API
    (/api/v6/pay/x402/*): declares support for our exact scheme/network,
    accepts any payment as valid, and reports settlement as successful
    with a fake transaction hash — wrapped in OKX's real {code, data,
    msg} envelope, and checking that requests actually carry a
    correctly-computed OK-ACCESS-SIGN (catches a wiring mistake that
    silently drops auth).
    """

    def __init__(self):
        self.verify_calls = []
        self.settle_calls = []
        self.auth_failures = []

        app = FastAPI()

        @app.get(f"{OKX_BASE_PATH}/supported")
        def supported(request: Request):
            self._check_auth(request, "")
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "kinds": [
                        {"x402Version": 2, "scheme": "exact", "network": NETWORK},
                    ]
                },
            }

        @app.post(f"{OKX_BASE_PATH}/verify")
        async def verify(request: Request):
            raw = await request.body()
            self._check_auth(request, raw.decode())
            self.verify_calls.append(json.loads(raw))
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "isValid": True,
                    "payer": "0x000000000000000000000000000000000000aa",
                },
            }

        @app.post(f"{OKX_BASE_PATH}/settle")
        async def settle(request: Request):
            raw = await request.body()
            self._check_auth(request, raw.decode())
            self.settle_calls.append(json.loads(raw))
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "success": True,
                    "transaction": "0x" + "ab" * 32,
                    "network": NETWORK,
                    "amount": "100000",
                },
            }

        self.app = app
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def _check_auth(self, request: Request, body: str) -> None:
        """
        Recomputes the OK-ACCESS-SIGN the real OKX API would require
        (HMAC-SHA256 over timestamp+method+path+body, per okx_auth.py)
        and records a failure if it doesn't match — proves the
        middleware is actually authenticating, not just reachable.
        """
        key = request.headers.get("OK-ACCESS-KEY")
        sign = request.headers.get("OK-ACCESS-SIGN")
        timestamp = request.headers.get("OK-ACCESS-TIMESTAMP")
        passphrase = request.headers.get("OK-ACCESS-PASSPHRASE")

        path = request.url.path
        prehash = (timestamp or "") + request.method + path + body
        expected = base64.b64encode(
            hmac.new(SECRET_KEY.encode(), prehash.encode(), hashlib.sha256).digest()
        ).decode()

        if key != API_KEY or passphrase != PASSPHRASE or sign != expected:
            self.auth_failures.append(
                {"path": path, "key": key, "passphrase": passphrase, "sign_ok": sign == expected}
            )

    def start(self):
        self.thread.start()
        deadline = time.time() + 5
        while not self.server.started and time.time() < deadline:
            time.sleep(0.05)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture(scope="module")
def mock_facilitator():
    facilitator = MockOKXFacilitator()
    facilitator.start()
    yield facilitator
    facilitator.stop()


def _complete_config(okx_base_url: str, **overrides) -> X402Config:
    base = dict(
        enabled=True,
        chain_id=196,
        okx_base_url=okx_base_url,
        okx_api_key=API_KEY,
        okx_secret_key=SECRET_KEY,
        okx_passphrase=PASSPHRASE,
        okx_sync_settle=True,
        token_address=TOKEN_ADDRESS,
        token_decimals=6,
        token_symbol="USD₮0",
        token_eip712_name="USD₮0",
        token_eip712_version="2",
        price="0.10",
        pay_to_address=PAY_TO_ADDRESS,
        max_timeout_seconds=300,
    )
    base.update(overrides)
    return X402Config(**base)


def _decode_challenge(resp) -> dict:
    """
    The SDK delivers the x402 v2 challenge via the PAYMENT-REQUIRED
    header (base64 JSON) rather than the response body — confirmed by
    inspecting a real 402 response from install_x402_middleware().
    """
    header_value = resp.headers["payment-required"]
    return json.loads(base64.b64decode(header_value))


def _build_app(config: X402Config) -> FastAPI:
    app = FastAPI()

    @app.post("/api/agent-interface/analyze")
    def analyze():
        return {"issues_found": [], "severity": "none", "explanation": "looks fine"}

    install_x402_middleware(app, config)
    return app


# --- Disabled / invalid config: middleware is a true no-op -----------


def test_disabled_config_leaves_route_unprotected():
    config = _complete_config(okx_base_url="http://127.0.0.1:1", enabled=False, okx_api_key=None)
    app = _build_app(config)
    client = TestClient(app)

    resp = client.post("/api/agent-interface/analyze", json={"code": "x=1"})

    assert resp.status_code == 200
    assert resp.json() == {"issues_found": [], "severity": "none", "explanation": "looks fine"}


def test_incomplete_config_auto_disables_and_leaves_route_unprotected():
    # OKX_API_KEY missing -> validation fails -> middleware not installed,
    # even though enabled=True.
    config = _complete_config(okx_base_url="http://127.0.0.1:1", enabled=True, okx_api_key=None)
    app = _build_app(config)
    client = TestClient(app)

    resp = client.post("/api/agent-interface/analyze", json={"code": "x=1"})

    assert resp.status_code == 200
    assert resp.json()["explanation"] == "looks fine"


# --- Enabled + valid config: real payment gate behavior ---------------


def test_unpaid_request_gets_x402_challenge(mock_facilitator):
    config = _complete_config(okx_base_url=mock_facilitator.url)
    app = _build_app(config)
    client = TestClient(app)

    resp = client.post("/api/agent-interface/analyze", json={"code": "x=1"})

    assert resp.status_code == 402
    challenge = _decode_challenge(resp)
    accepts = challenge["accepts"]
    assert len(accepts) == 1
    option = accepts[0]
    assert option["scheme"] == "exact"
    assert option["network"] == NETWORK
    assert option["asset"] == TOKEN_ADDRESS
    assert option["amount"] == "100000"  # 0.10 USD₮0 at 6 decimals
    assert option["payTo"] == PAY_TO_ADDRESS
    assert mock_facilitator.auth_failures == []


def test_paid_request_reaches_protected_route(mock_facilitator):
    config = _complete_config(okx_base_url=mock_facilitator.url)
    app = _build_app(config)
    client = TestClient(app)

    # Get the real challenge so `accepted` mirrors exactly what the
    # server asked for (mirrors what a real x402 client does).
    challenge = _decode_challenge(
        client.post("/api/agent-interface/analyze", json={"code": "x=1"})
    )
    accepted = challenge["accepts"][0]

    payment_payload = {
        "x402Version": 2,
        "payload": {"signature": "0x" + "11" * 65, "authorization": {}},
        "accepted": accepted,
        "resource": None,
    }
    header_value = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    resp = client.post(
        "/api/agent-interface/analyze",
        json={"code": "x=1"},
        headers={"PAYMENT-SIGNATURE": header_value},
    )

    assert resp.status_code == 200
    # Existing endpoint behavior is completely unchanged by the payment layer.
    assert resp.json() == {"issues_found": [], "severity": "none", "explanation": "looks fine"}
    # The mock OKX facilitator actually saw authenticated verify + settle calls.
    assert len(mock_facilitator.verify_calls) >= 1
    assert len(mock_facilitator.settle_calls) >= 1
    assert mock_facilitator.auth_failures == []


def test_unpaid_request_after_a_paid_one_is_still_gated(mock_facilitator):
    # The gate must re-apply per request, not "unlock" after one payment.
    config = _complete_config(okx_base_url=mock_facilitator.url)
    app = _build_app(config)
    client = TestClient(app)

    challenge = _decode_challenge(
        client.post("/api/agent-interface/analyze", json={"code": "x=1"})
    )
    accepted = challenge["accepts"][0]
    payment_payload = {
        "x402Version": 2,
        "payload": {"signature": "0x" + "22" * 65, "authorization": {}},
        "accepted": accepted,
        "resource": None,
    }
    header_value = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    paid_resp = client.post(
        "/api/agent-interface/analyze",
        json={"code": "x=1"},
        headers={"PAYMENT-SIGNATURE": header_value},
    )
    assert paid_resp.status_code == 200

    unpaid_again = client.post("/api/agent-interface/analyze", json={"code": "x=1"})
    assert unpaid_again.status_code == 402
