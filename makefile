sources = docint tests2

.PHONY: test format lint unittest coverage pre-commit clean
test: format lint unittest

format:
	isort $(sources) tests2
	black $(sources) tests2

lint:
	flake8 $(sources) tests2

unittest:
	pytest

coverage:
	pytest --cov=$(sources) --cov-branch --cov-report=term-missing tests2

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -rf .tox dist site
	rm -rf coverage.xml .coverage
