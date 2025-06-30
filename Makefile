# -*- mode: makefile-gmake  -*-
root = .
include ${root}/defs.mk

version = $(shell ${PYTHON} -c "import pipettor; print(pipettor.__version__)")

ifeq ($(shell uname),Darwin)
  BROWSER = open
else
  BROWSER = true
endif

.PHONY: help clean clean-build clean-pyc clean-docs clean-tests \
	lint vulture test test-all coverage \
	docs docs-open \
	install \
	dist test-pip \
	test-release test-release-pip \
	release

testenv = testenv

pypi_url = https://upload.pypi.org/simple/
testpypi_url = https://test.pypi.org/simple/

define envsetup
	@rm -rf ${testenv}
	mkdir -p ${testenv}
	${PYTHON} -m virtualenv --quiet ${testenv}
endef
envact = source ${testenv}/bin/activate

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-docs - remove generated documentation"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "vulture - check for unused code"
	@echo "test - run tests quickly with the default Python"
	@echo "test-all - run tests on every Python version with tox"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "docs-open - gererate documents and open in web local browser"
	@echo "install - install the package to the active Python's site-packages"
	@echo "dist - package"
	@echo "test-pip - test install the package using pip"
	@echo "release-testpypi - test upload to testpypi"
	@echo "test-release-testpypi - install from testpypi"
	@echo "release - package and upload a release"
	@echo "test-release - test final release"

clean: clean-build clean-pyc clean-test clean-docs

clean-build:
	rm -fr build/ dist/ .eggs/ ${testenv}/ lib/pipettor.egg-info/

clean-pyc:
	rm -fr lib/pipettor/__pycache__ tests/__pycache__

clean-docs:
	rm -f docs/pipettor.rst docs/modules.rst
	$(MAKE) -C docs clean

clean-test:
	rm -fr .tox/ htmlcov/ .coverage htmlcov/ tests/output/ .pytest_cache/

lint:
	${PYTHON} -m flake8 --color=never lib/pipettor tests

vulture:
	${PYTHON} -m vulture lib/pipettor tests

test:
	${PYTEST} tests

test-all:
	tox

coverage:
	${COVERAGE} run -m pytest ${PYTEST_OPTS} tests
	${COVERAGE} report -m
	${COVERAGE} html
	${BROWSER} htmlcov/index.html

docs:
	$(MAKE) -C docs clean
	$(MAKE) -C docs html

docs-open: docs
	${BROWSER} docs/_build/html/index.html

install: clean
	${PIP} install .

dist: clean
	${PYTHON} -m build
	@ls -l dist

# test install locally
test-pip: dist
	${envsetup}
	${envact} && pip install --no-cache-dir dist/pipettor-${version}-py3-none-any.whl[dev]
	${envact} && ${PYTEST} tests

dist_wheel = dist/pipettor-${version}-py3-none-any.whl
dist_tar = dist/pipettor-${version}.tar.gz

# test release to testpypi
release-testpypi: dist
	${TWINE} upload --repository=testpypi ${dist_wheel} ${dist_tar}

# test release install from testpypi
test-release-testpypi:
	${envsetup}
	${envact} && pip install --no-cache-dir --index-url=${testpypi_url} pipettor==${version}
	${envact} && ${PYTEST} tests

release: dist
	${TWINE} upload --repository=pypi ${dist_wheel} ${dist_tar}

release-test:
	${envsetup}
	${envact} && pip install --no-cache-dir pipettor==${version}
	${envact} && ${PYTEST} tests


