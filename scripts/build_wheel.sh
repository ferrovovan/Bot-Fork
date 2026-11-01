#!/usr/bin/env bash
# ==============================================================================
# Helper script to build .whl and .tar.gz for Bot Fork locally
# ==============================================================================
set -euo pipefail

echo "==> Cleaning old build artifacts..."
rm -rf dist/ build/ *.egg-info

echo "==> Ensuring build tools are installed..."
python3 -m pip install --upgrade pip build twine

echo "==> Building wheel and sdist..."
python3 -m build

echo "==> Checking built packages with Twine..."
python3 -m twine check --strict dist/*

echo "==> Successfully built packages:"
ls -lah dist/
