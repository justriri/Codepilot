def calculate_average(numbers):
    """
    Calculate the average of a list of numbers.

    Args:
        numbers: A list of numeric values (int or float).

    Returns:
        The arithmetic mean as a float, or None if the list is empty.
    """
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    # Quick demonstration
    print(calculate_average([1, 2, 3, 4, 5]))
    print(calculate_average([1.5, 2.5, 3.5]))
    print(calculate_average([]))
