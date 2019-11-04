=====================================================
datacube-alchemist - ODC Dataset to Dataset Converter
=====================================================

:Info: This is the README file for datacube-alchemist
.. :Author: {{ cookiecutter.full_name }} <{{ cookiecutter.email }}>
:Copyright: © 2019, Geoscience Australia.
:Version: 0.0.1

.. index: README
.. image:: https://travis-ci.org/opendatacube/datacube-alchemist.svg?branch=master
   :target: https://travis-ci.org/opendatacube/datacube-alchemist

PURPOSE
-------
Datacube Alchemst is a command line application for performing Dataset -> Dataset transformations in the context
of an Open Data Cube system.

It uses a configuration file which specifies an input _Product_, a transformation to perform, and
output parameters and destination.

Features
--------

- Writes output a Cloud Optimised GeoTIFFs
- Easily run within a Docker Container
- Parallelism using AWS SQS queues
- Write output data to S3
- Generates ``eo3`` format dataset metadata, along with processing information
- Configurable thumbnail generation
- Pass any command line options as Environment Variables

INSTALLATION
------------

.. code-block::bash

   docker pull opendatacube/datacube-alchemist

USAGE
-----

Datacube Alchemist does not handle the re-indexing of produced datasets. This must be handled separately.

NOTES
-----

COPYRIGHT
---------
Apache License 2.0
