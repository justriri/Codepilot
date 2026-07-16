def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test empty list
assert calculate_average([]) == 0, 'Empty list should return 0'

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test single element
assert calculate_average([5]) == 5.0, 'Single element should return itself'

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test typical list
assert calculate_average([1, 2, 3]) == 2.0, 'Average of 1,2,3 is 2'

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test with negative numbers
assert calculate_average([-1, 1]) == 0.0, 'Average of -1 and 1 should be 0'

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test with floats
assert abs(calculate_average([1.5, 2.5]) - 2.0) < 1e-9, 'Average of 1.5 and 2.5 should be 2.0'

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

# Test with zero
assert calculate_average([0]) == 0.0, 'Average of [0] should be 0.0'
