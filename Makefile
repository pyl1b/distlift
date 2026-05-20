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
	python -c "import pathlib, shutil; \
		roots = ('dist', 'build', '.pytest_cache', '.ruff_cache', '.mypy_cache'); \
		[shutil.rmtree(p, ignore_errors=True) for p in roots]; \
		[shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]; \
		[shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
