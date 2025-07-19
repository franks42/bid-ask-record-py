#!/bin/bash

# Exit on any error
set -e

echo "=== Running code quality checks ==="

# Run black for code formatting
echo "[1/4] Running black..."
uv run black --check --diff --color .

# Run isort for import sorting
echo "[2/4] Running isort..."
uv run isort --check-only --profile black .

# Run pylint for code quality
echo "[3/4] Running pylint..."
uv run pylint bidaskrecord/ tests/ scripts/

# Run mypy for type checking
echo "[4/4] Running mypy..."
uv run mypy --strict --ignore-missing-imports bidaskrecord/ scripts/

echo "=== All checks passed! ==="

# If we get here, all checks passed
exit 0
