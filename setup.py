#!/usr/bin/env python
# -*- coding: utf-8 -*-


import setuptools


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

requirements = [
]

setuptools.setup(
    name = 'pipettor',
    version = '0.8.0',
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
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    python_requires='>=3.7',
)
