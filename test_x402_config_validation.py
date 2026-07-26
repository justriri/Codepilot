"""
Unit tests for the x402 payment layer's config + startup validation
(payments/config.py, payments/validation.py).

These tests exercise pure logic only — no network calls, no x402
package import, no AI provider keys required — so they run anywhere
`pytest` runs, including CI with none of the optional services
configured.
"""

from payments.config import X402Config, price_to_atomic
from payments.validation import resolve_x402_enabled, validate_x402_config

VALID_ADDRESS_A = "0x779Ded0c9e1022225f8E0630b35a9b54bE713736"
VALID_ADDRESS_B = "0xff67a208df0dd71fea796af3a334b14fa687fc3a"


def _complete_config(**overrides) -> X402Config:
    base = dict(
        enabled=True,
        chain_id=196,
        facilitator_url="https://example-facilitator.test",
        token_address=VALID_ADDRESS_A,
        token_decimals=6,
        token_symbol="USD₮0",
        token_eip712_name="USD₮0",
        token_eip712_version="2",
        price="0.10",
        pay_to_address=VALID_ADDRESS_B,
        max_timeout_seconds=300,
    )
    base.update(overrides)
    return X402Config(**base)


# --- price_to_atomic -------------------------------------------------


def test_price_to_atomic_basic():
    assert price_to_atomic("0.10", 6) == "100000"


def test_price_to_atomic_whole_number():
    assert price_to_atomic("1", 6) == "1000000"


def test_price_to_atomic_no_float_rounding_error():
    # 0.1 cannot be represented exactly in binary float; Decimal must be
    # used internally or this silently drifts (e.g. to 99999 or 100001).
    assert price_to_atomic("0.10", 18) == "100000000000000000"


def test_price_to_atomic_invalid_raises():
    try:
        price_to_atomic("not-a-number", 6)
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- validate_x402_config --------------------------------------------


def test_complete_config_has_no_errors():
    assert validate_x402_config(_complete_config()) == []


def test_missing_facilitator_url_is_flagged():
    errors = validate_x402_config(_complete_config(facilitator_url=None))
    assert any("X402_FACILITATOR_URL" in e for e in errors)


def test_non_http_facilitator_url_is_flagged():
    errors = validate_x402_config(_complete_config(facilitator_url="ftp://bad"))
    assert any("X402_FACILITATOR_URL" in e for e in errors)


def test_missing_chain_id_is_flagged():
    errors = validate_x402_config(_complete_config(chain_id=None))
    assert any("X402_CHAIN_ID" in e for e in errors)


def test_invalid_token_address_is_flagged():
    errors = validate_x402_config(_complete_config(token_address="not-an-address"))
    assert any("X402_TOKEN_ADDRESS" in e for e in errors)


def test_missing_token_address_is_flagged():
    errors = validate_x402_config(_complete_config(token_address=None))
    assert any("X402_TOKEN_ADDRESS" in e for e in errors)


def test_invalid_pay_to_address_is_flagged():
    errors = validate_x402_config(_complete_config(pay_to_address="0xshort"))
    assert any("X402_PAY_TO_ADDRESS" in e for e in errors)


def test_missing_decimals_is_flagged():
    errors = validate_x402_config(_complete_config(token_decimals=None))
    assert any("X402_TOKEN_DECIMALS" in e for e in errors)


def test_missing_eip712_name_is_flagged():
    errors = validate_x402_config(_complete_config(token_eip712_name=None))
    assert any("X402_TOKEN_EIP712_NAME" in e for e in errors)


def test_invalid_price_is_flagged():
    errors = validate_x402_config(_complete_config(price="ten cents"))
    assert any("X402_PRICE" in e for e in errors)


def test_multiple_missing_fields_all_reported():
    errors = validate_x402_config(
        _complete_config(facilitator_url=None, chain_id=None, token_address=None)
    )
    assert len(errors) >= 3


# --- resolve_x402_enabled ----------------------------------------------


def test_disabled_flag_short_circuits_validation():
    # enabled=False with an otherwise-broken config should NOT report
    # errors — the feature is off, not misconfigured.
    config = _complete_config(enabled=False, facilitator_url=None)
    is_enabled, errors = resolve_x402_enabled(config)
    assert is_enabled is False
    assert errors == []


def test_incomplete_config_auto_disables():
    config = _complete_config(facilitator_url=None)
    is_enabled, errors = resolve_x402_enabled(config)
    assert is_enabled is False
    assert len(errors) == 1


def test_complete_config_resolves_enabled():
    is_enabled, errors = resolve_x402_enabled(_complete_config())
    assert is_enabled is True
    assert errors == []
