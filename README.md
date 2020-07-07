# datacube-alchemist - ODC Dataset to Dataset Converter

Copyright: © 2019, Geoscience Australia.

Version: 0.0.1

![Test and build status](https://github.com/opendatacube/datacube-alchemist/workflows/Lint%20and%20Test%20Code%20and%20Push%20Docker%20image%20for%20master%20branch/badge.svg)

## PURPOSE

Datacube Alchemst is a command line application for performing Dataset -> Dataset transformations in the context
of an Open Data Cube system.

It uses a configuration file which specifies an input _Product_, a transformation to perform, and
output parameters and destination.

Features

* Writes output a Cloud Optimised GeoTIFFs
* Easily run within a Docker Container
* Parallelism using AWS SQS queues
* Write output data to S3
* Generates ``eo3`` format dataset metadata, along with processing information
* Configurable thumbnail generation
* Pass any command line options as Environment Variables

## INSTALLATION

You can build the docker image locally with Docker or Docker Compose. The commands are
`docker build --tag opendatacube/datacube-alchemist .` or `docker-compose build`.

There's a Python setup file, so you can do `pip3 install .` in the root folder. You will
need to ensure that the Open Data Cube and all its dependencies happily install though.

## USAGE
-----

To run some example processes you can use the Docker Compose file to create a local workspace.
To start the workspace and run an example, you can do the following:

* `make up` or `docker-compose up` to start the postgres and datacube-alchemist Docker containers
* `make initdb` to initialise the ODC database (or see the Makefile for the specific command)
* `make metadata` will add the `eo-plus` metadata that the Sentinel-2 example product needs
* `make product` will add the Sentinel-2 product definition
* `make add-one-scene` will index a single Sentinel-2 scene for us to process
* `make run-one-fc` or `make run-one-wofs` will process a single Fractional Cover or Water
Observations from Space scene and output the results to `/tmp/alchemist` locally

## NOTES

## LICENSE

Apache License 2.0
