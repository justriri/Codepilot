"""
Startup validation for the x402 payment layer.

Runs once at process startup (see server/app.py). Deliberately never
raises: an invalid or incomplete configuration disables the payment
layer with a clear log warning instead of crashing the whole service
or, worse, coming up in a half-configured state that fails
unpredictably on the first real request.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import List, Tuple

from .config import X402Config

logger = logging.getLogger("payments.x402")

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def validate_x402_config(config: X402Config) -> List[str]:
    """
    Returns a list of human-readable problems with the config. An empty
    list means every required value is present and well-formed.
    """
    errors: List[str] = []

    if not config.facilitator_url:
        errors.append(
            "X402_FACILITATOR_URL is not set. No official x402 facilitator "
            "for X Layer is documented as of this writing — this must be "
            "supplied explicitly once you've verified one (see "
            "docs/X402_PAYMENTS.md); it intentionally has no default."
        )
    elif not (
        config.facilitator_url.startswith("http://")
        or config.facilitator_url.startswith("https://")
    ):
        errors.append(
            f"X402_FACILITATOR_URL is not a valid http(s) URL: {config.facilitator_url!r}"
        )

    if not config.chain_id:
        errors.append("X402_CHAIN_ID is not set.")

    if not config.token_address:
        errors.append("X402_TOKEN_ADDRESS is not set.")
    elif not _EVM_ADDRESS_RE.match(config.token_address):
        errors.append(
            f"X402_TOKEN_ADDRESS is not a valid EVM address: {config.token_address!r}"
        )

    if not config.pay_to_address:
        errors.append("X402_PAY_TO_ADDRESS is not set.")
    elif not _EVM_ADDRESS_RE.match(config.pay_to_address):
        errors.append(
            f"X402_PAY_TO_ADDRESS is not a valid EVM address: {config.pay_to_address!r}"
        )

    if not config.token_decimals or config.token_decimals <= 0:
        errors.append("X402_TOKEN_DECIMALS is not set (or not a positive integer).")

    if not config.token_eip712_name:
        errors.append(
            "X402_TOKEN_EIP712_NAME is not set. This is the token contract's "
            "EIP-712 domain name, required for the 'exact' scheme's "
            "EIP-3009 signature — read it from the contract itself "
            "(see docs/X402_PAYMENTS.md), do not guess it."
        )

    try:
        Decimal(config.price)
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"X402_PRICE is not a valid decimal number: {config.price!r}")

    return errors


def resolve_x402_enabled(config: X402Config) -> Tuple[bool, List[str]]:
    """
    Combines the manual X402_ENABLED feature flag with config validation.

    Returns (effectively_enabled, errors). Logs a clear warning and
    disables automatically on any validation failure.
    """
    if not config.enabled:
        logger.info("x402 payment layer disabled via X402_ENABLED=false.")
        return False, []

    errors = validate_x402_config(config)
    if errors:
        logger.warning(
            "x402 payment layer DISABLED at startup — invalid/incomplete "
            "configuration:\n  - %s\n"
            "The verification API will serve requests WITHOUT a payment "
            "gate until this is fixed. See docs/X402_PAYMENTS.md.",
            "\n  - ".join(errors),
        )
        return False, errors

    return True, []
