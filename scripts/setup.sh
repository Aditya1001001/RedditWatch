#!/usr/bin/env bash
set -e

echo "=== RedditWatch Setup ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r backend/requirements.txt

# Create data directory
mkdir -p data

# Copy .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To start RedditWatch:"
echo "  ./scripts/run.sh"
echo ""
echo "Optional: Install Ollama for local LLM analysis"
echo "  https://ollama.ai"
echo "  ollama pull llama3.1:8b"
