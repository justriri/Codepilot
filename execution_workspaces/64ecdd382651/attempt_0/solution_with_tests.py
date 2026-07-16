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

assert calculate_average([]) == 0

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert calculate_average([5]) == 5.0

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert calculate_average([1, 2, 3]) == 2.0

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert calculate_average([-1, -2, -3]) == -2.0

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert abs(calculate_average([1, -2, 3]) - 0.6666666666666666) < 1e-7

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert calculate_average([1.5, 2.5]) == 2.0

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

assert calculate_average([1e9, 2e9]) == 1.5e9
