.PHONY: install lint format check test clean

install:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

check:
	ruff check .
	ruff format --check .
	pytest

test:
	pytest

clean:
	rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
