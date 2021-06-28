# Datacube Alchemist - ODC Dataset to Dataset Converter


![Scan](https://github.com/opendatacube/datacube-alchemist/workflows/Scan/badge.svg)
![Test](https://github.com/opendatacube/datacube-alchemist/workflows/Test/badge.svg)
![Push](https://github.com/opendatacube/datacube-alchemist/workflows/Push/badge.svg)
[![codecov](https://codecov.io/gh/opendatacube/datacube-alchemist/branch/main/graph/badge.svg?token=8dsJGc99qY)](https://codecov.io/gh/opendatacube/datacube-alchemist)

## PURPOSE

Datacube Alchemist is a command line application for performing Dataset to Dataset transformations in the context
of an Open Data Cube system.

It uses a configuration file which specifies an input _Product_ or _Products_, a _Transformation_ to perform, and
output parameters and destination.

Features

* Writes output to Cloud Optimised GeoTIFFs
* Easily runs within a Docker Container
* Parallelism using AWS SQS queues and Kubernetes
* Write output data to S3 or a file system
* Generates `eo3` format dataset metadata, along with processing information
* Generates STAC 1.0.0.beta2 dataset metadata
* Configurable thumbnail generation
* Pass any command line options as Environment Variables

## INSTALLATION

You can build the docker image locally with Docker or Docker Compose. The commands are
`docker build --tag opendatacube/datacube-alchemist .` or `docker-compose build`.

There's a Python setup file, so you can do `pip3 install .` in the root folder. You will
need to ensure that the Open Data Cube and all its dependencies happily install though.

## USAGE

### Development environment

To run some example processes you can use the Docker Compose file to create a local workspace.
To start the workspace and run an example, you can do the following:

* Export the environment variables `ODC_ACCESS_KEY` and `ODC_SECRET_KEY` with valid AWS credentials
* Run `make up` or `docker-compose up` to start the postgres and datacube-alchemist Docker containers
* `make initdb` to initialise the ODC database (or see the Makefile for the specific command)
* `make metadata` will add the metadata that the Landsat example product needs
* `make product` will add the Landsat product definitions
* `make index` will index a range of Landsat scenes to test processing with
* `make wofs-one` or `make fc-one` will process a single Fractional Cover or Water
Observations from Space scene and output the results to the ./examples folder in this project directory

## Commands

Note that the `--config-file` can be a local path or a URI.

### datacube-alchemist run-one

Note that `--dryrun` is optional, and will run a 1/10 scale load and will not
write output to the final destination.

``` bash
datacube-alchemist run-one \
  --config-file ./examples/c3_config_wo.yaml \
  --uuid 7b9553d4-3367-43fe-8e6f-b45999c5ada6 \
  --dryrun \

```

### datacube-alchemist run-many

Note that the final argument is a datacube _expression_ , see
[Datacube Search documentation](https://datacube-core.readthedocs.io/en/latest/ops/tools.html?highlight=expressions#datacube-dataset-search).

``` bash
datacube-alchemist run-many \
  --config-file ./examples/c3_config_wo.yaml \
  --limit=2 \
  --dryrun \
  time in 2020-01
```

### datacube-alchemist run-from-queue

Notes on queues. To run jobs from an SQS queue, good practice is to create a deadletter queue
as well as a main queue. Jobs (messages) get picked up off the main queue, and if they're successful,
then they're deleted. If they aren't successful, they're not deleted, and they go back on the
main queue after a defined amount of time. If this happens more than the defined number of times
then the message is moved to the deadletter queue. In this way, you can track work completion.

``` bash
datacube-alchemist run-from-queue \
  --config-file ./examples/c3_config_wo.yaml \
  --queue example-queue-name \
  --limit=1 \
  --queue-timeout=600 \
  --dryrun
```

### datacube-alchemist add-to-queue

The `--limit` is the total number of datasets to limit to, whereas the `--product-limit` is
the number of datasets per product, in the case that you have multiple input products.

``` bash
datacube-alchemist add-to-queue \
  --config-file ./examples/c3_config_wo.yaml \
  --queue example-queue-name \
  --limit=300 \
  --product-limit=100
```

### datacube-alchemist redrive-to-queue

This will get items from a deadletter queue and push them to an
alive queue. Be careful, because it doesn't know what queue is what.
You need to know that!

``` bash
datacube-alchemist redrive-to-queue \
  --queue example-from-queue \
  --to-queue example-to-queue
```

## License

Apache License 2.0

## Copyright

© 2021, Open Data Cube Community
