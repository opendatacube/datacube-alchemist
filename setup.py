#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import io
from setuptools import setup, find_packages

tests_require = [
    "flake8",
    "pytest",
    "pytest-cov"
]

setup(
    name='datacube-alchemist',
    description='Batch process Open Data Cube Datasets',
    keywords='datacube-alchemist',
    url='https://github.com/opendatacube/datacube-alchemist',
    license='Apache License 2.0',
    long_description=io.open(
        'README.rst', 'r', encoding='utf-8').read(),
    platforms='any',
    zip_safe=False,
    # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 1 - Planning',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Operating System :: OS Independent',
    ],
    packages=find_packages(exclude=('tests',)),
    include_package_data=True,
    install_requires=[
        "attrs>=18.1",
        "cattrs",
        "structlog",
        "cloudpickle",
        "boto3",
        "dask>=2",
        "distributed",
        "fsspec>=0.3.3",
        "s3fs",
        "jsonschema>=3",
        "h5py",
        "numexpr",
        "scipy",
        "ephem",
        "requests"
    ],
    tests_require=tests_require,
    extras_require={
        "test": tests_require
    },
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    entry_points={
        'console_scripts': [
            'datacube-alchemist = datacube_alchemist.cli:cli_with_envvar_handling',
        ]
    },
)
