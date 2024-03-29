sources = docint tests

.PHONY: test format lint unittest coverage pre-commit clean
test: format lint unittest

format:
	poetry run ruff format $(sources)

lint:
	poetry run ruff $(sources)

unittest:
	poetry run pytest

coverage:
	poetry run pytest --cov=$(sources) --cov-branch --cov-report=term-missing tests

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -rf .tox dist site
	rm -rf coverage.xml .coverage
