distclean:
	rm -rf dist/ build/ netfleece.egg-info .eggs netfleece/__pycache__

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

dist build:
	python3 setup.py sdist bdist_wheel

publish: distclean pristine dist build
	git push -v --follow-tags --dry-run
	python3 -m twine upload dist/*
	git push --follow-tags

publish-test: distclean pristine dist build
	python3 -m twine upload --repository-url 'https://test.pypi.org/legacy/' dist/*
