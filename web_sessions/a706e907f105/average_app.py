def calculate_average(numbers):
    """Calculate the average of a list of numbers.

    Args:
        numbers: A list of ints or floats.

    Returns:
        The arithmetic mean as a float.

    Raises:
        ValueError: If the list is empty.
    """
    if not numbers:
        raise ValueError("Cannot compute average of an empty list.")

    return sum(numbers) / len(numbers)
