#!/bin/bash
set -euo pipefail

# Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -sSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create and activate virtual environment
echo "Setting up virtual environment..."
uv venv .venv --python=3.11
source .venv/bin/activate

# Upgrade pip and install build dependencies
echo "Installing build dependencies..."
uv pip install --upgrade pip setuptools wheel

# Install the package in development mode with all extras
echo "Installing package in development mode..."
uv pip install -e ".[dev]"

# Install pre-commit hooks
echo "Setting up pre-commit hooks..."
pre-commit install

# Initialize git repository if not already done
if [ ! -d .git ]; then
    git init
    git add .
    git commit -m "Initial commit"
fi

echo "\n✅ Development environment setup complete!"
echo "Activate the virtual environment with: source .venv/bin/activate"
echo "Run pre-commit manually with: pre-commit run --all-files"
