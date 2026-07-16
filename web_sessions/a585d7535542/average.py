def calculate_average(numbers):
    """Return the average of a list of numbers.

    Args:
        numbers: A list of int or float values.

    Returns:
        float: The arithmetic mean of the numbers.

    Raises:
        ValueError: If the input list is empty.
    """
    if not numbers:
        raise ValueError("Cannot calculate average of an empty list.")
    return sum(numbers) / len(numbers)


# Quick manual sanity checks
if __name__ == "__main__":
    print(calculate_average([1, 2, 3, 4, 5]))          # 3.0
    print(calculate_average([2.5, 3.5, 4.0]))         # ~3.333...
    print(calculate_average([-1, 0, 1]))               # 0.0
    print(calculate_average([42]))                     # 42.0
    try:
        print(calculate_average([]))
    except ValueError as e:
        print(f"Empty list → {e}")
