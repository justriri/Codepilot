"""
x402 payment configuration.

Every payment-related value is environment-driven — nothing here is
hardcoded. See .env.example for the full variable list and
docs/X402_PAYMENTS.md for where each value comes from (the official
OKX X Layer token list, OKX's own x402 dev docs, etc.).

Settlement goes through OKX's own authenticated facilitator
(x402.http.OKXFacilitatorClient, from the official `okxweb3-app-x402`
package) rather than a generic unauthenticated one — see
docs/X402_PAYMENTS.md for why.
"""

import os
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class X402Config:
    # Manual kill switch — independent of validation (see validation.py).
    enabled: bool

    chain_id: Optional[int]

    # OKX's own authenticated facilitator (see OKXAuthConfig/OKXFacilitatorConfig
    # in x402.http). base_url matches the SDK's own documented default.
    okx_base_url: str
    okx_api_key: Optional[str]
    okx_secret_key: Optional[str]
    okx_passphrase: Optional[str]
    okx_sync_settle: bool

    token_address: Optional[str]
    token_decimals: Optional[int]
    token_symbol: str
    # EIP-712 domain for the token's transferWithAuthorization (EIP-3009)
    # signature — required for the 'exact' scheme. Verify against the
    # token contract itself (see docs/X402_PAYMENTS.md); never guess it.
    token_eip712_name: Optional[str]
    token_eip712_version: str

    # Human-readable price, e.g. "0.10" — converted to atomic units via
    # price_to_atomic() using token_decimals, never hand-computed.
    price: str
    pay_to_address: Optional[str]

    max_timeout_seconds: int


def _str_or_none(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _int_or_none(value: Optional[str]) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def load_x402_config() -> X402Config:
    return X402Config(
        enabled=os.environ.get("X402_ENABLED", "true").strip().lower()
        not in ("0", "false", "no"),
        chain_id=_int_or_none(os.environ.get("X402_CHAIN_ID")),
        okx_base_url=os.environ.get("OKX_BASE_URL", "https://web3.okx.com").strip()
        or "https://web3.okx.com",
        okx_api_key=_str_or_none(os.environ.get("OKX_API_KEY")),
        okx_secret_key=_str_or_none(os.environ.get("OKX_SECRET_KEY")),
        okx_passphrase=_str_or_none(os.environ.get("OKX_PASSPHRASE")),
        okx_sync_settle=os.environ.get("OKX_SYNC_SETTLE", "true").strip().lower()
        not in ("0", "false", "no"),
        token_address=_str_or_none(os.environ.get("X402_TOKEN_ADDRESS")),
        token_decimals=_int_or_none(os.environ.get("X402_TOKEN_DECIMALS")),
        token_symbol=os.environ.get("X402_TOKEN_SYMBOL", "USD₮0"),
        token_eip712_name=_str_or_none(os.environ.get("X402_TOKEN_EIP712_NAME")),
        token_eip712_version=os.environ.get("X402_TOKEN_EIP712_VERSION", "2"),
        price=os.environ.get("X402_PRICE", "0.10"),
        pay_to_address=_str_or_none(os.environ.get("X402_PAY_TO_ADDRESS")),
        max_timeout_seconds=int(os.environ.get("X402_MAX_TIMEOUT_SECONDS", "300")),
    )


def price_to_atomic(price: str, decimals: int) -> str:
    """
    Converts a human-readable decimal price (e.g. "0.10") to the token's
    smallest-unit integer string (e.g. "100000" for 6 decimals) using
    exact decimal arithmetic — never float math, which would round a
    price like 0.10 to a wrong atomic amount.
    """
    try:
        amount = Decimal(price).scaleb(decimals).to_integral_value(rounding=ROUND_DOWN)
    except InvalidOperation as exc:
        raise ValueError(f"X402_PRICE is not a valid decimal number: {price!r}") from exc
    return str(int(amount))
