#!/usr/bin/env python
import io
from setuptools import setup, find_packages

dev_requirements = [
    "flake8",
    "pytest",
    "pytest-cov",
    "odc-index",
    "odc-apps-cloud",
    "odc-apps-dc-tools",
    "datacube-index @ git+https://github.com/opendatacube/datacube-index.git",
]

setup(
    name="datacube-alchemist",
    description="Batch process Open Data Cube datasets",
    keywords="datacube-alchemist",
    url="https://github.com/opendatacube/datacube-alchemist",
    license="Apache License 2.0",
    long_description=io.open("README.md", "r", encoding="utf-8").read(),
    platforms="any",
    zip_safe=False,
    # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        "Development Status :: 1 - Planning",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(exclude=("tests",)),
    include_package_data=True,
    install_requires=[
        "datacube",
        "eodatasets3",
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
        "requests",
    ],
    extras_require={"dev": dev_requirements},
    dependency_links=["https://packages.dea.ga.gov.au/"],
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    entry_points={
        "console_scripts": [
            "datacube-alchemist = datacube_alchemist.cli:cli_with_envvar_handling",
        ]
    },
)
