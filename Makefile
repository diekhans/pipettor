.PHONY: help clean clean-build clean-pyc clean-docs clean-tests lint test test-all coverage docs servedocs release dist install testpip
define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

testenv = testenv


help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "test-all - run tests on every Python version with tox"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "dist - package"
	@echo "install - install the package to the active Python's site-packages"
	@echo "testpip - test install the package using pip"

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
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-docs:
	rm -f docs/pipettor.rst
	rm -f docs/modules.rst
	$(MAKE) -C docs clean

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

lint:
	flake8 src/pipettor tests

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
	sphinx-apidoc -o docs/ src
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

release: clean
	python setup.py sdist upload
	python setup.py bdist_wheel upload

dist: clean
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean
	python setup.py install

testpip: dist
	@rm -rf ${testenv}
	mkdir -p ${testenv}
	virtualenv ${testenv}
	(cd ${testenv} && source ./bin/activate && pip install --no-cache-dir ../../dist/pipettor-*.tar.gz)
	(cd ${testenv} && source ./bin/activate && python ../../tests/pipettorTests.py)
