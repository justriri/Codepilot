def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

try:
    calculate_average([])
    assert False, 'Should have raised ValueError'
except ValueError:
    pass

assert calculate_average([42]) == 42

assert calculate_average([1, 2, 3, 4, 5]) == 3

assert calculate_average([-1, -2, -3]) == -2

assert abs(calculate_average([1.5, 2.5, 3.5]) - 2.5) < 1e-9

assert abs(calculate_average([1, 2.5, 3]) - 2.1666666666666665) < 1e-9

assert calculate_average([10**9, 2*10**9, 3*10**9]) == 2*10**9
