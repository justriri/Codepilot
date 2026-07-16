import pytest
from app import calculate_total


class TestCalculateTotal:
    """Test suite for calculate_total function."""

    def test_integer_items(self):
        """calculate_total([10, 20, 30]) should return 60."""
        result = calculate_total([10, 20, 30])
        assert result == 60, f"Expected 60, got {result}"

    def test_decimal_items(self):
        """calculate_total([1.5, 2.5, 3.0]) should return 7.0."""
        result = calculate_total([1.5, 2.5, 3.0])
        assert result == 7.0, f"Expected 7.0, got {result}"

    def test_empty_list(self):
        """calculate_total([]) should not crash and should return 0."""
        result = calculate_total([])
        assert result == 0, f"Expected 0, got {result}"

    def test_single_item(self):
        """calculate_total with a single item should return that item."""
        result = calculate_total([42])
        assert result == 42, f"Expected 42, got {result}"

    def test_negative_numbers(self):
        """calculate_total should handle negative numbers."""
        result = calculate_total([-5, -10, 15])
        assert result == 0, f"Expected 0, got {result}"

    def test_mixed_types(self):
        """calculate_total with mixed int/float should work."""
        result = calculate_total([1, 2.5, 3])
        assert result == 6.5, f"Expected 6.5, got {result}"

    def test_large_numbers(self):
        """calculate_total with large numbers should work."""
        result = calculate_total([10**6, 10**6])
        assert result == 2_000_000, f"Expected 2,000,000, got {result}"

    def test_precision(self):
        """Decimal precision should be maintained."""
        result = calculate_total([0.1, 0.2])
        # 0.1 + 0.2 ≈ 0.30000000000000004 in IEEE 754
        assert abs(result - 0.3) < 1e-9, f"Expected ~0.3, got {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
