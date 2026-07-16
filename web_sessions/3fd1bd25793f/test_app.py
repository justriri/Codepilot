"""Tests for calculate_average."""

import pytest
from app import calculate_average


class TestCalculateAverage:
    """Test suite for the calculate_average function."""

    def test_normal_input(self):
        """Average of standard integer list."""
        assert calculate_average([1, 2, 3, 4, 5]) == 3.0

    def test_single_element(self):
        """Average of a single-element list."""
        assert calculate_average([42]) == 42.0

    def test_decimal_values(self):
        """Average of floating-point values."""
        assert calculate_average([1.5, 2.5, 3.0]) == pytest.approx(2.3333333333333335)

    def test_mixed_int_float(self):
        """Average of mixed int and float values."""
        result = calculate_average([1, 2.5, 3])
        assert result == pytest.approx(2.1666666666666665)

    def test_negative_numbers(self):
        """Average of negative numbers."""
        assert calculate_average([-5, -10, -15]) == -10.0

    def test_empty_input(self):
        """Empty list should return None safely."""
        assert calculate_average([]) is None

    def test_empty_input_does_not_raise(self):
        """Empty list should not raise any exception."""
        try:
            calculate_average([])
        except Exception as e:
            pytest.fail(f"Empty list raised an exception: {type(e).__name__}: {e}")

    def test_large_numbers(self):
        """Average of large numbers."""
        assert calculate_average([1_000_000, 2_000_000, 3_000_000]) == 2_000_000.0

    def test_zero_list(self):
        """Average of all zeros."""
        assert calculate_average([0, 0, 0]) == 0.0
