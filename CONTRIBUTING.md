# Contributing to RedditWatch

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone and setup
git clone https://github.com/Aditya1001001/RedditWatch.git
cd RedditWatch
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Run the dev server
cd backend
uvicorn app.main:app --reload --port 8000

# Run tests
python -m pytest tests/ -v
```

## Project Structure

```
backend/
  app/
    api/          # FastAPI route handlers
    collectors/   # Public Reddit conversation collection
    llm/          # LLM provider abstraction
    models/       # SQLAlchemy ORM models
    services/     # Business logic (analyzer, collector, search, tasks)
  tests/          # pytest test suite
frontend/
  index.html      # Single-page app (Alpine.js + Tailwind)
```

## Coding Standards

- **Python 3.9+** compatible
- **Type hints** on function signatures
- **async/await** for all I/O operations
- Follow existing patterns in the codebase
- Run `pytest` before submitting a PR

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add tests for new functionality
4. Ensure all tests pass: `python -m pytest tests/ -v`
5. Open a PR against `main` with a description of your changes

## What to Contribute

Check the [issues](https://github.com/Aditya1001001/RedditWatch/issues) page for open tasks. Good first issues are labeled accordingly.

Areas where help is welcome:
- **Tests** - Improving coverage beyond the current ~40%
- **Docker** - Testing and improving the Docker setup
- **LLM providers** - Adding new providers or improving prompts
- **UI improvements** - Responsive design, accessibility
- **Documentation** - Tutorials, API docs, examples
