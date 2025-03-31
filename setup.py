#!/usr/bin/env python
# -*- coding: utf-8 -*-


import setuptools


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

requirements = [
]

extras_require={
    "dev": [
        "bumpversion>=0.5.3",
        "wheel>=0.23.0",
        "flake8>=2.4.1",
        "tox>=2.1.1",
        "coverage>=4.0",
        "Sphinx>=1.3.1",
        "cryptography>=1.0.1",
        "PyYAML>=3.11",
        "twine>=1.11",
        "pytest>=5.3",
        "vulture>=2.1",
    ],
}

setuptools.setup(
    name = 'pipettor',
    version = '1.1.0',
    description = "pipettor - robust, easy to use Unix process pipelines",
    long_description = readme + '\n\n' + history,
    long_description_content_type="text/markdown",
    author = "Mark Diekhans",
    author_email = 'markd@ucsc.edu',
    url = 'https://github.com/diekhans/pipettor',
    packages = [
        'pipettor',
    ],
    package_dir = {'': 'lib'},
    include_package_data = True,
    install_requires = requirements,
    license = "MIT",
    zip_safe = True,
    keywords = ['Unix', 'process', 'pipe'],
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    python_requires='>=3.7',
)
