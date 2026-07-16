#!/usr/bin/env bash
# Run the test suite and generate a short summary.
set -e

echo "=== Python version ==="
python3 --version

echo ""
echo "=== Running pytest with verbose output ==="
python3 -m pytest test_average.py -v --tb=short 2>&1

echo ""
echo "=== All tests finished ==="
