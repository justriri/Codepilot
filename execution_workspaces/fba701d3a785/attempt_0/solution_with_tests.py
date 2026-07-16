def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

assert calculate_average([]) == 0

assert calculate_average([5]) == 5

assert calculate_average([1, 2, 3, 4, 5]) == 3

assert calculate_average([-1, -2, -3, -4]) == -2.5

assert calculate_average([10.5, 20.5, 30.0]) == 20.333333333333332

assert calculate_average([0, 0, 0]) == 0

assert calculate_average([1e6, 2e6]) == 1500000.0

assert calculate_average([1, -1, 1, -1]) == 0
