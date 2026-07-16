def calculate_average(numbers):
    if not numbers:
        return 0
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

print(calculate_average([]))

# --- Generated tests ---

def test_empty_list():
    assert calculate_average([]) == 0
    print('test_empty_list passed')
test_empty_list()

def test_single_element():
    assert calculate_average([5]) == 5
    print('test_single_element passed')
test_single_element()

def test_positive_integers():
    assert calculate_average([1, 2, 3, 4, 5]) == 3.0
    print('test_positive_integers passed')
test_positive_integers()

def test_negative_integers():
    assert calculate_average([-1, -2, -3, -4, -5]) == -3.0
    print('test_negative_integers passed')
test_negative_integers()

def test_mixed_signs():
    assert calculate_average([-10, 0, 10]) == 0.0
    print('test_mixed_signs passed')
test_mixed_signs()

def test_floats():
    assert calculate_average([1.5, 2.5, 3.5]) == 2.5
    print('test_floats passed')
test_floats()

def test_all_zeros():
    assert calculate_average([0, 0, 0]) == 0.0
    print('test_all_zeros passed')
test_all_zeros()

def test_large_numbers():
    assert calculate_average([10**6, 10**6, 10**6]) == 10**6
    print('test_large_numbers passed')
test_large_numbers()

def test_mixed_types():
    assert calculate_average([1, 2.5, 3]) == 2.1666666666666665
    print('test_mixed_types passed')
test_mixed_types()
