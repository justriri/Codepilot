def calculate_discount(price, discount):
    return price * (1 - discount / 100)

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

def calculate_discount(price, discount):
    return price * (1 - discount / 100)
assert calculate_discount(100, 20) == 80.0
print('test passed')

def calculate_discount(price, discount):
    return price * (1 - discount / 100)
assert calculate_discount(50, 0) == 50.0
print('test passed')

def calculate_discount(price, discount):
    return price * (1 - discount / 100)
assert calculate_discount(200, 100) == 0.0
print('test passed')

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
assert calculate_average([]) == 0
print('test passed')

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
assert calculate_average([5]) == 5.0
print('test passed')

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
assert calculate_average([1,2,3]) == 2.0
print('test passed')

def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
assert calculate_average([-1, 1]) == 0.0
print('test passed')
