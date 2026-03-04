# Contributing to KodaDocs

Thank you for your interest in contributing to KodaDocs! This guide will help you get started.

## Development Setup

1. Clone the repository:

```bash
git clone https://github.com/kodadocs/kodadocs.git
cd kodadocs
```

2. Install uv (Python package manager):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install dependencies:

```bash
uv sync --dev
```

4. Install Playwright browser (for screenshot capture tests):

```bash
uv run playwright install chromium
```

5. Verify setup:

```bash
uv run pytest -v
```

## Running Tests

```bash
uv run pytest -v              # Run all tests
uv run pytest tests/test_capture.py  # Run specific test file
uv run pytest -k "test_name"  # Run tests matching pattern
```

## Linting and Formatting

KodaDocs uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
uv run ruff check .           # Lint
uv run ruff format --check .  # Check formatting
uv run ruff format .          # Auto-format
```

## Adding a New Framework Detector

KodaDocs detects web frameworks via heuristic file patterns. To add support for a new framework:

1. Edit `src/kodadocs/utils/framework.py`
2. Add a detection function that checks for framework-specific files (e.g., `package.json` scripts, config files, directory structure)
3. Register the detector in the framework detection chain
4. Add a test in `tests/test_framework.py`

## Pull Request Guidelines

- **One thing per PR** — keep changes focused and reviewable
- **Include tests** for new functionality
- **Run the full test suite** before submitting: `uv run pytest -v`
- **Run lint** before submitting: `uv run ruff check .`
- **Write clear commit messages** describing what changed and why

## Reporting Issues

- **Bug reports**: Include steps to reproduce, expected behavior, actual behavior, and your Python/OS version
- **Feature requests**: Describe the use case and why it would benefit KodaDocs users

## Code of Conduct

Be kind, be constructive, be respectful. We are all here to build something useful.

## License

By contributing to KodaDocs, you agree that your contributions will be licensed under the MIT License.
