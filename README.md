# Datacube Alchemist - ODC Dataset to Dataset Converter


![Scan](https://github.com/opendatacube/datacube-alchemist/workflows/Scan/badge.svg)
![Test](https://github.com/opendatacube/datacube-alchemist/workflows/Test/badge.svg)
![Push](https://github.com/opendatacube/datacube-alchemist/workflows/Push/badge.svg)
[![codecov](https://codecov.io/gh/opendatacube/datacube-alchemist/branch/main/graph/badge.svg?token=8dsJGc99qY)](https://codecov.io/gh/opendatacube/datacube-alchemist)

## Purpose

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

## Installation

You can build the docker image locally with Docker or Docker Compose. The commands are
`docker build --tag opendatacube/datacube-alchemist .` or `docker-compose build`.

There's a Python setup file, so you can do `pip3 install .` in the root folder. You will
need to ensure that the Open Data Cube and all its dependencies happily install though.

## Usage

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

## Production Usage

Datacube Alchemist is used in production by the [Digital Earth Australia](https://dea.ga.gov.au/) and [Digital Earth
Africa](https://www.digitalearthafrica.org/) programs

### Queues

Notes on queues. To run jobs from an SQS queue, good practice is to create a deadletter queue
as well as a main queue. Jobs (messages) get picked up off the main queue, and if they're successful,
then they're deleted. If they aren't successful, they're not deleted, and they go back on the
main queue after a defined amount of time. If this happens more than the defined number of times
then the message is moved to the deadletter queue. In this way, you can track work completion.

## Commands

Note that the `--config-file` can be a local path or a URI.

### datacube-alchemist run-one

<!-- [[[cog
# Regenerate this embedded CLI documentation by running `python -m cogapp -r README.md`
import cog
from datacube_alchemist import cli
from click.testing import CliRunner
runner = CliRunner()
def print_help(command):
  result = runner.invoke(cli.cli, [command, "--help"])
  help = result.output.replace("Usage: cli", "Usage: datacube-alchemist")
  cog.out(
      "```\n{}\n```".format(help)
  )
print_help("run-one")
]]] -->
```
Usage: datacube-alchemist run-one [OPTIONS]

  Run with the config file for one input_dataset (by UUID)

Options:
  -c, --config-file TEXT  The path (URI or file) to a config file to use for the
                          job  [required]
  -u, --uuid TEXT         UUID of the scene to be processed  [required]
  --dryrun, --no-dryrun   Don't actually do real work
  --help                  Show this message and exit.

```
<!-- [[[end]]] -->

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

<!-- [[[cog
print_help("run-many")
]]] -->
```
Usage: datacube-alchemist run-many [OPTIONS] [EXPRESSIONS]...

  Run Alchemist with the config file on all the Datasets matching an ODC query
  expression

  EXPRESSIONS

  Select datasets using [EXPRESSIONS] to filter by date, product type, spatial
  extents or other searchable fields.

      FIELD = VALUE
      FIELD in DATE-RANGE
      FIELD in [START, END]
      TIME < DATE
      TIME > DATE

  START and END can be either numbers or dates
  Dates follow YYYY, YYYY-MM, or YYYY-MM-DD format

  FIELD: x, y, lat, lon, time, product, ...

  eg. 'time in [1996-01-01, 1996-12-31]'
      'time in 1996'
      'time > 2020-01'
      'lon in [130, 140]' 'lat in [-40, -30]'
      product=ls5_nbar_albers

Options:
  -c, --config-file TEXT  The path (URI or file) to a config file to use for the
                          job  [required]
  -l, --limit INTEGER     For testing, limit the number of tasks to create or
                          process.
  --dryrun, --no-dryrun   Don't actually do real work
  --help                  Show this message and exit.

```
<!-- [[[end]]] -->

**Example**

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


<!-- [[[cog
print_help("run-from-queue")
]]] -->
```
Usage: datacube-alchemist run-from-queue [OPTIONS]

  Process messages from the given queue

Options:
  -c, --config-file TEXT       The path (URI or file) to a config file to use
                               for the job  [required]
  -q, --queue TEXT             Name of an AWS SQS Message Queue  [required]
  -l, --limit INTEGER          For testing, limit the number of tasks to create
                               or process.
  -s, --queue-timeout INTEGER  The SQS message Visibility Timeout in seconds,
                               default is 600, or 10 minutes.
  --dryrun, --no-dryrun        Don't actually do real work
  --sns-arn TEXT               Publish resulting STAC document to an SNS
  --help                       Show this message and exit.

```
<!-- [[[end]]] -->

**Example**

``` bash
datacube-alchemist run-from-queue \
  --config-file ./examples/c3_config_wo.yaml \
  --queue example-queue-name \
  --limit=1 \
  --queue-timeout=600 \
  --dryrun
```

### datacube-alchemist add-to-queue

Search for Datasets and enqueue Tasks into an AWS SQS Queue for later processing.


The `--limit` is the total number of datasets to limit to, whereas the `--product-limit` is
the number of datasets per product, in the case that you have multiple input products.

<!-- [[[cog
print_help("add-to-queue")
]]] -->
```
Usage: datacube-alchemist add-to-queue [OPTIONS] [EXPRESSIONS]...

  Search for Datasets and enqueue Tasks into an AWS SQS Queue for later
  processing.

  EXPRESSIONS

  Select datasets using [EXPRESSIONS] to filter by date, product type, spatial
  extents or other searchable fields.

      FIELD = VALUE
      FIELD in DATE-RANGE
      FIELD in [START, END]
      TIME < DATE
      TIME > DATE

  START and END can be either numbers or dates
  Dates follow YYYY, YYYY-MM, or YYYY-MM-DD format

  FIELD: x, y, lat, lon, time, product, ...

  eg. 'time in [1996-01-01, 1996-12-31]'
      'time in 1996'
      'time > 2020-01'
      'lon in [130, 140]' 'lat in [-40, -30]'
      product=ls5_nbar_albers

Options:
  -c, --config-file TEXT       The path (URI or file) to a config file to use
                               for the job  [required]
  -q, --queue TEXT             Name of an AWS SQS Message Queue  [required]
  -l, --limit INTEGER          For testing, limit the number of tasks to create
                               or process.
  -p, --product-limit INTEGER  For testing, limit the number of datasets per
                               product.
  --dryrun, --no-dryrun        Don't actually do real work
  --help                       Show this message and exit.

```
<!-- [[[end]]] -->

**Example**

``` bash
datacube-alchemist add-to-queue \
  --config-file ./examples/c3_config_wo.yaml \
  --queue example-queue-name \
  --limit=300 \
  --product-limit=100
```

### datacube-alchemist redrive-to-queue

Redrives messages from an SQS queue.

All the messages in the specified queue are re-transmitted to either their original queue
or the specified TO-QUEUE.

Be careful when manually specifying TO-QUEUE, as it's easy to mistakenly push tasks to the
wrong queue, eg. One that will process them with an incorrect configuration file.

<!-- [[[cog
print_help("redrive-to-queue")
]]] -->
```
Usage: datacube-alchemist redrive-to-queue [OPTIONS]

  Redrives all the messages from the given sqs queue to their source, or the
  target queue

Options:
  -q, --queue TEXT       Name of an AWS SQS Message Queue  [required]
  -l, --limit INTEGER    For testing, limit the number of tasks to create or
                         process.
  -t, --to-queue TEXT    Url of SQS Queue to move to
  --dryrun, --no-dryrun  Don't actually do real work
  --help                 Show this message and exit.

```
<!-- [[[end]]] -->

**Example**

``` bash
datacube-alchemist redrive-to-queue \
  --queue example-from-queue \
  --to-queue example-to-queue
```

### datacube-alchemist add-missing-to-queue

Search for datasets that don't have a target product dataset and add them to the queue

If a predicate is supplied, datasets which do not match are filtered out.

The predicate is a Python expression that should return True or False, which has a single
dataset available as the variable `d`.

Example predicates:
 - `d.metadata.gqa_iterative_mean_xy <= 1`
 - `d.metadata.gqa_iterative_mean_xy and ('2022-06-30' <= str(d.center_time.date()) <= '2023-07-01')`
 - `d.metadata.dataset_maturity == "final"`

<!-- [[[cog
print_help("add-missing-to-queue")
]]] -->
```
Usage: datacube-alchemist add-missing-to-queue [OPTIONS]

  Search for datasets that don't have a target product dataset and add them to
  the queue

  If a predicate is supplied, datasets which do not match are filtered out.

  Example predicate:  - 'd.metadata.gqa_iterative_mean_xy <= 1'

Options:
  --predicate TEXT        Python predicate to filter datasets. Dataset is
                          available as "d"
  -c, --config-file TEXT  The path (URI or file) to a config file to use for the
                          job  [required]
  -q, --queue TEXT        Name of an AWS SQS Message Queue  [required]
  --dryrun, --no-dryrun   Don't actually do real work
  --help                  Show this message and exit.

```
<!-- [[[end]]] -->

## Configuration File

A YAML file with 3 sections:

- [`specification`](#specification-of-inputs) - Define the inputs and algorithm
- [`output`](#specification-of-inputs) - Output location and format options
- [`processing`](#) - Optimise CPU/Memory requirements

Datacube Alchemist requires a configuration file in YAML format, to setup the Algorithm or Transformation,
the input Dataset/s, as well as details of the outputs including metadata, destination and preview image generation.

The configuration file has 3 sections. `specification` sets up the input ODC product, data bands and
configured algorithm  to run . `output` sets where the output files will be written, how the preview image will be
created, and what extra metadata to include. `processing` can help configure the tasks memory and CPU requirements..

### Specification (of inputs)

Defines the input data and the algorithm to process it.

**product** or **products**
Names of the

**measurements:** [list] of measurement names to load from the input products

**measurement_renames:** [map] rename measurements from the input data before passing to the transform

**transform:** [string] fully qualified name of a Python class implementing the transform

**transform_url:** [string] Reference URL for the Transform, to record in the output metadata

**override_product_family:**  Override part of the metadata (should be in <output>)

**basis:** ????

**transform_args:** [map] Named arguments to pass to the Transformer class


### Full example specification

```yaml
specification:
  products:
    - ga_ls5t_ard_3
    - ga_ls7e_ard_3
    - ga_ls8c_ard_3
  measurements: ['nbart_blue', 'nbart_green', 'nbart_red', 'nbart_nir', 'nbart_swir_1', 'nbart_swir_2', 'oa_fmask']
  measurement_renames:
    oa_fmask: fmask

  aws_unsigned: False
  transform: wofs.virtualproduct.WOfSClassifier
  transform_url: 'https://github.com/GeoscienceAustralia/wofs/'
  override_product_family: ard
  basis: nbart_green

  transform_args:
    dsm_path:  's3://dea-non-public-data/dsm/dsm1sv1_0_Clean.tiff'
```

### Transform Class Implementation

## License

Apache License 2.0

## Copyright

© 2021, Open Data Cube Community
