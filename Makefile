# -*- mode: makefile-gmake  -*-

.PHONY: help clean clean-build clean-pyc clean-docs clean-tests \
	lint test test-all coverage \
	docs docs-open \
	install \
	dist test-pip \
	test-release test-release-pip \
	release

testenv = testenv

define envsetup
	@rm -rf ${testenv}
	mkdir -p ${testenv}
	virtualenv --quiet ${testenv}
endef
envact = cd ${testenv} && source ./bin/activate

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-docs - remove generated documentation"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "test-all - run tests on every Python version with tox"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "docs-open - gererate documents and open in web local browser"
	@echo "install - install the package to the active Python's site-packages"
	@echo "dist - package"
	@echo "test-pip - test install the package using pip"
	@echo "test-release - test upload to pypitest"
	@echo "test-release-pip - install from pypitest"
	@echo "release - package and upload a release"

clean: clean-build clean-pyc clean-test clean-docs

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	rm -fr ${testenv}/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -depth -name '__pycache__' -exec rm -fr {} +

clean-docs:
	rm -f docs/pipettor.rst
	rm -f docs/modules.rst
	$(MAKE) -C docs clean

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

lint:
	flake8 lib/pipettor tests

test:
	python setup.py test

test-all:
	tox

coverage:
	coverage run --source pipettor setup.py test
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html

docs:
	rm -f docs/pipettor.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ lib
	$(MAKE) -C docs clean
	$(MAKE) -C docs html

docs-open: docs
	open docs/_build/html/index.html

install: clean
	python setup.py install

dist: clean
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

# test install locally
test-pip: dist
	${envsetup}
	${envact} && pip install --no-cache-dir ../dist/pipettor-*.tar.gz
	${envact} && python ../tests/pipettorTests.py

# test release to pypitest
test-release: clean
	python setup.py sdist upload --repository=pypitest
	python setup.py bdist_wheel upload --repository=pypitest

# test release install from pypitest
test-release-pip:
	${envsetup}
	${envact} && pip install --no-cache-dir --index=https://testpypi.python.org/pypi pipettor
	${envact} && python ../tests/pipettorTests.py

release: clean
	python setup.py sdist upload --repository=pypi
	python setup.py bdist_wheel upload --repository=pypi

