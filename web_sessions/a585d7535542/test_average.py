"""Tests for calculate_average covering normal, decimal, and empty-list cases."""

import math
import pytest
from average import calculate_average


class TestCalculateAverage:
    """Grouped tests for the calculate_average function."""

    # ---------- Normal input ----------
    def test_single_element(self):
        assert calculate_average([7]) == 7.0

    def test_positive_integers(self):
        assert calculate_average([1, 2, 3, 4, 5]) == 3.0

    def test_mixed_sign_integers(self):
        assert calculate_average([-3, -2, 0, 2, 3]) == 0.0

    def test_all_negative(self):
        assert calculate_average([-10, -20, -30]) == -20.0

    def test_large_numbers(self):
        assert calculate_average([10**6, 10**7]) == 5_500_000.0

    # ---------- Decimal / float values ----------
    def test_all_floats(self):
        result = calculate_average([2.5, 3.5, 4.0])
        assert math.isclose(result, 3.3333333333333335, rel_tol=1e-9)

    def test_mixed_int_float(self):
        result = calculate_average([1, 2.5, 3])
        assert math.isclose(result, 2.1666666666666665, rel_tol=1e-9)

    def test_small_decimals(self):
        result = calculate_average([0.1, 0.2, 0.3])
        assert math.isclose(result, 0.2, rel_tol=1e-9)

    def test_very_small_floats(self):
        result = calculate_average([1e-10, 2e-10, 3e-10])
        assert math.isclose(result, 2e-10, rel_tol=1e-9)

    # ---------- Empty input ----------
    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot calculate average of an empty list."):
            calculate_average([])

    # ---------- Edge cases ----------
    def test_zeros(self):
        assert calculate_average([0, 0, 0, 0]) == 0.0

    def test_repeated_values(self):
        assert calculate_average([5, 5, 5, 5]) == 5.0

    def test_long_list(self):
        numbers = list(range(1, 1001))
        expected = sum(numbers) / len(numbers)
        assert calculate_average(numbers) == expected

    def test_type_is_float(self):
        # The result should always be a float
        assert isinstance(calculate_average([1, 2]), float)
