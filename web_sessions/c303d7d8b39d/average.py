def calculate_average(numbers):
    """Return the average of a list of numbers.

    Args:
        numbers: A list of int or float values.

    Returns:
        The arithmetic mean as a float, or None if the list is empty.
    """
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    # Quick smoke test
    print(calculate_average([1, 2, 3, 4, 5]))
    print(calculate_average([]))
    print(calculate_average([1.5, 2.5, 3.5]))
