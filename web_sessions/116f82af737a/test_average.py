import unittest
from average import calculate_average


class TestCalculateAverage(unittest.TestCase):
    """Comprehensive tests for calculate_average."""

    # --- Normal input ---
    def test_normal_integer_list(self):
        """Average of a standard integer list."""
        self.assertAlmostEqual(calculate_average([1, 2, 3, 4, 5]), 3.0)

    def test_single_element(self):
        """Average of a single-element list is that element."""
        self.assertEqual(calculate_average([42]), 42.0)

    def test_two_elements(self):
        """Average of two numbers."""
        self.assertEqual(calculate_average([10, 20]), 15.0)

    def test_negative_numbers(self):
        """Average with negative numbers."""
        self.assertEqual(calculate_average([-5, -10, 0, 5, 10]), 0.0)

    def test_large_numbers(self):
        """Average with large numbers stays correct."""
        self.assertEqual(calculate_average([1_000_000, 2_000_000, 3_000_000]), 2_000_000.0)

    # --- Decimal / floating-point values ---
    def test_decimal_values(self):
        """Average of floating-point numbers."""
        self.assertAlmostEqual(calculate_average([1.5, 2.5, 3.5]), 2.5)

    def test_mixed_int_and_float(self):
        """Average of mixed int and float."""
        result = calculate_average([1, 2.5, 3])
        self.assertAlmostEqual(result, 2.1666666666666665)

    def test_precise_decimals(self):
        """Average of precise decimals."""
        result = calculate_average([0.1, 0.2, 0.3])
        self.assertAlmostEqual(result, 0.2)

    def test_very_small_numbers(self):
        """Average of very small floating-point numbers."""
        result = calculate_average([1e-10, 2e-10, 3e-10])
        self.assertAlmostEqual(result, 2e-10)

    # --- Empty input ---
    def test_empty_list_returns_none(self):
        """Empty list must return None, not raise an exception."""
        self.assertIsNone(calculate_average([]))

    def test_empty_list_no_exception(self):
        """Empty list does not throw any exception."""
        try:
            calculate_average([])
        except Exception as e:
            self.fail(f"calculate_average([]) raised {type(e).__name__}: {e}")

    # --- Edge cases ---
    def test_all_zeros(self):
        """Average of all zeros is zero."""
        self.assertEqual(calculate_average([0, 0, 0, 0]), 0.0)

    def test_list_with_one_zero(self):
        """Average of a list containing only zero."""
        self.assertEqual(calculate_average([0]), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
