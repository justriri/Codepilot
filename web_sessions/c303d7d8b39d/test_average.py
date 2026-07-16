"""Tests for calculate_average covering normal, decimal, and empty input."""

import math
from average import calculate_average


def test_normal_integers():
    """Average of a standard list of integers."""
    result = calculate_average([1, 2, 3, 4, 5])
    assert result == 3.0, f"Expected 3.0, got {result}"


def test_single_element():
    """Average of a single-element list."""
    result = calculate_average([42])
    assert result == 42.0, f"Expected 42.0, got {result}"


def test_negative_numbers():
    """Average of negative integers."""
    result = calculate_average([-10, -20, -30])
    assert result == -20.0, f"Expected -20.0, got {result}"


def test_mixed_sign():
    """Average of mixed positive and negative numbers."""
    result = calculate_average([-5, 5])
    assert result == 0.0, f"Expected 0.0, got {result}"


def test_decimal_values():
    """Average of floating-point decimal values."""
    result = calculate_average([1.5, 2.5, 3.5])
    assert math.isclose(result, 2.5, rel_tol=1e-9), \
        f"Expected ~2.5, got {result}"


def test_mixed_int_float():
    """Average of mixed int and float values."""
    result = calculate_average([1, 2.5, 3])
    expected = (1 + 2.5 + 3) / 3
    assert math.isclose(result, expected, rel_tol=1e-9), \
        f"Expected ~{expected}, got {result}"


def test_empty_list():
    """Empty list should return None safely, not crash."""
    result = calculate_average([])
    assert result is None, f"Expected None for empty list, got {result}"


def test_large_numbers():
    """Average of large numbers."""
    result = calculate_average([1_000_000, 2_000_000, 3_000_000])
    assert result == 2_000_000.0, f"Expected 2000000.0, got {result}"


def test_all_zeros():
    """Average of all zeros."""
    result = calculate_average([0.0, 0, 0.0])
    assert result == 0.0, f"Expected 0.0, got {result}"


def test_repeating_decimals():
    """Average that results in a repeating decimal."""
    result = calculate_average([1, 2])
    assert result == 1.5, f"Expected 1.5, got {result}"


def run_all_tests():
    """Discover and run all test_* functions, reporting results."""
    import sys

    tests = [
        (name, fn)
        for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 50}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    import sys
    sys.exit(0 if success else 1)
