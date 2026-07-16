def calculate_average(numbers):
    if len(numbers) == 0:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

assert calculate_average([]) == 0

assert calculate_average([5]) == 5

assert calculate_average([1, 2, 3]) == 2

assert calculate_average([-1, -2, -3]) == -2

assert calculate_average([-5, 5]) == 0

assert calculate_average([2.5, 7.5]) == 5.0

assert calculate_average([1e10, 2e10]) == 1.5e10

assert calculate_average([i for i in range(100)]) == 49.5
