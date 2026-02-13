#!/usr/bin/env bash
set -e

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "Starting RedditWatch on http://localhost:8000"
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
