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
]

test_requirements = [
]

setup(
    name = 'pipettor',
    version = '0.5.0',
    description = "pipettor - robust, easy to use Unix process pipelines",
    long_description = readme + '\n\n' + history,
    author = "Mark Diekhans",
    author_email = 'markd@soe.ucsc.edu',
    url = 'https://github.com/diekhans/pipettor',
    packages = [
        'pipettor',
    ],
    package_dir = {'': 'lib'},
    include_package_data = True,
    install_requires = requirements,
    license = "MIT",
    zip_safe = True,
    keywords = ['process', 'pipe'],
    classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
