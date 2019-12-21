distclean:
	rm -rf dist/ build/ netfleece.egg-info

install:
	pip install .

develop:
	pip install -e .

publish:
	python3 setup.py sdist bdist_wheel
	python3 -m twine upload dist/*

publish-test:
	python3 setup.py sdist bdist_wheel
	python3 -m twine upload --repository-url 'https://test.pypi.org/legacy/' dist/*
