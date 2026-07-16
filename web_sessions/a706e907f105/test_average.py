import pytest
from average_app import calculate_average


class TestCalculateAverage:
    """Tests for the calculate_average function."""

    # ---------- normal input ----------

    def test_normal_integers(self):
        """Average of a list of positive integers."""
        assert calculate_average([1, 2, 3, 4, 5]) == 3.0

    def test_single_element(self):
        """Average of a single-element list."""
        assert calculate_average([42]) == 42.0

    def test_mixed_positive_negative(self):
        """Average of mixed positive and negative integers."""
        assert calculate_average([-5, 5]) == 0.0

    def test_negative_numbers(self):
        """Average of all-negative integers."""
        assert calculate_average([-1, -2, -3]) == -2.0

    # ---------- decimal / float values ----------

    def test_float_values(self):
        """Average of a list of floats."""
        assert calculate_average([1.5, 2.5, 3.0]) == pytest.approx(7.0 / 3.0)

    def test_mixed_int_float(self):
        """Average of mixed ints and floats."""
        assert calculate_average([1, 2.5, 3]) == pytest.approx(6.5 / 3.0)

    def test_small_floats(self):
        """Average of very small floats."""
        result = calculate_average([1e-10, 2e-10, 3e-10])
        assert result == pytest.approx(2e-10)

    def test_large_numbers(self):
        """Average of large numbers (no overflow)."""
        assert calculate_average([1e9, 2e9, 3e9]) == pytest.approx(2e9)

    # ---------- empty input ----------

    def test_empty_list_raises(self):
        """Passing an empty list must raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            calculate_average([])
        assert "empty" in str(exc_info.value).lower()

    # ---------- edge cases ----------

    def test_all_zeros(self):
        """Average of zeros is zero."""
        assert calculate_average([0, 0, 0]) == 0.0

    def test_duplicate_values(self):
        """Average with duplicate values."""
        assert calculate_average([2, 2, 2, 2]) == 2.0
