# include with
#   root=../..
#   include ${root}/defs.mk

# override to change numner of test processes
nproc = 10


.PRECIOUS:
.SECONDARY:

SHELL = /bin/bash
export BASHOPTS = -beEu -o pipefail
MAKEFLAGS += -rR

PYTHON = python3
FLAKE8 = python3 -m flake8

PYTEST_OPTS = --tb=native -rsx
PYTEST = ${PYTHON} -W always -m pytest ${PYTEST_OPTS} --numprocesses=${nproc}
PIP = pip3
COVERAGE = ${PYTHON} -m coverage
TWINE = ${PYTHON} -m twine

# ensure all commands use local rather than install
ifneq (${TREE_PYTHON_PATHSET},yes)
    export PYTHONPATH:=${root}/lib:${PYTHONPATH}
    export TREE_PYTHON_PATHSET=yes
endif
export PYTHONWARNINGS=always

# prevent warnings about emacs terminal from pytest-xdist
export TERM=dumb
