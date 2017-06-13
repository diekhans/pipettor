#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

requirements = [
    "six"
]

test_requirements = [
    "six"
]

setup(
    name = 'pipettor',
    version = '0.1.3',
    description = "pipettor - robust, easy to use Unix process pipelines",
    long_description = readme + '\n\n' + history,
    author = "Mark Diekhans",
    author_email = 'markd@soe.ucsc.edu',
    url = 'https://github.com/diekhans/pipettor',
    packages = [
        'pipettor',
    ],
    package_dir = {'': 'src'},
    include_package_data = True,
    install_requires = requirements,
    license = "MIT",
    zip_safe = True,
    keywords = ['process', 'pipe'],
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    test_suite = 'tests',
    tests_require = test_requirements
)
