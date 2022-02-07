distclean:
	rm -rf dist/ build/ netfleece.egg-info .eggs netfleece/__pycache__ .mypy_cache

install:
	pip install .

develop:
	pip install -e .

.PHONY: pristine
pristine:
	@git diff-files --quiet --ignore-submodules -- || \
		(echo "You have unstaged changes."; exit 1)
	@git diff-index --cached --quiet HEAD --ignore-submodules -- || \
		(echo "Your index contains uncommitted changes."; exit 1)
	@[ -z "$(shell git ls-files -o)" ] || \
		(echo "You have untracked files: $(shell git ls-files -o)"; exit 1)

.PHONY: build
build: dist

dist:
	python3 -m build

.PHONY: publish
publish: distclean pristine dist
	git push -v --follow-tags --dry-run
	python3 -m twine upload dist/*
	git push --follow-tags

publish-test: distclean pristine dist
	python3 -m twine upload --repository-url 'https://test.pypi.org/legacy/' dist/*

.PHONY: check
check:
	python3 -m pylint netfleece/
	python3 -m flake8 netfleece/
	python3 -m isort -c netfleece/
	python3 -m mypy -p netfleece
