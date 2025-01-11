sources = docint tests

.PHONY: test format lint unittest coverage pre-commit clean
test: format lint unittest

format:
	uv run ruff format $(sources)

lint:
	uv run ruff $(sources)

unittest:
	uv run pytest

coverage:
	uv run pytest --cov=$(sources) --cov-branch --cov-report=term-missing tests

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -rf .tox dist site
	rm -rf coverage.xml .coverage
