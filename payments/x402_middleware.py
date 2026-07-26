"""
x402 payment middleware wiring for the CodePilot verification API.

Gates every POST under /api/agent-interface/* (the paid A2MCP
verification surface registered on OKX AI) behind an x402 'exact'
payment challenge on X Layer, settled through OKX's own authenticated
facilitator (x402.http.OKXFacilitatorClient, from the official
`okxweb3-app-x402` package — see docs/X402_PAYMENTS.md for why this
replaced the generic unauthenticated HTTPFacilitatorClient). Nothing
here is hardcoded — every network/token/price/credential value comes
from payments/config.py.

This module only adds the payment gate. The verification pipeline
itself (agent/, server/agent_interface.py) is completely unchanged:
once a request clears the x402 challenge, it flows into the existing
handlers exactly as before.
"""

import logging

from fastapi import FastAPI

from .config import X402Config, price_to_atomic
from .validation import resolve_x402_enabled

logger = logging.getLogger("payments.x402")

PROTECTED_ROUTE_PATTERN = "POST /api/agent-interface/*"


def install_x402_middleware(app: FastAPI, config: X402Config) -> bool:
    """
    Attaches the x402 payment gate to `app` if, and only if,
    resolve_x402_enabled() confirms a complete configuration. Returns
    whether the middleware was actually installed, so callers/tests can
    assert on it without re-deriving the same logic.
    """
    enabled, _errors = resolve_x402_enabled(config)
    if not enabled:
        return False

    # Imported lazily so importing this module never requires the x402
    # package unless the payment layer is actually being installed
    # (e.g. local dev with X402_ENABLED=false doesn't need it present).
    from x402 import x402ResourceServer
    from x402.http import OKXAuthConfig, OKXFacilitatorClient, OKXFacilitatorConfig
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    network = f"eip155:{config.chain_id}"

    facilitator = OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(
                api_key=config.okx_api_key,
                secret_key=config.okx_secret_key,
                passphrase=config.okx_passphrase,
            ),
            base_url=config.okx_base_url,
            sync_settle=config.okx_sync_settle,
        )
    )
    server = x402ResourceServer(facilitator)
    server.register(network, ExactEvmServerScheme())

    routes = {
        PROTECTED_ROUTE_PATTERN: {
            "accepts": {
                "scheme": "exact",
                "network": network,
                "payTo": config.pay_to_address,
                "price": {
                    "amount": price_to_atomic(config.price, config.token_decimals),
                    "asset": config.token_address,
                    "extra": {
                        "name": config.token_eip712_name,
                        "version": config.token_eip712_version,
                    },
                },
                "maxTimeoutSeconds": config.max_timeout_seconds,
            },
            "description": "CodePilot code verification request",
        },
    }

    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)

    logger.info(
        "x402 payment layer ENABLED — %s %s per call on %s (asset %s), paid to %s, "
        "settled via OKX facilitator at %s",
        config.price,
        config.token_symbol,
        network,
        config.token_address,
        config.pay_to_address,
        config.okx_base_url,
    )
    return True
