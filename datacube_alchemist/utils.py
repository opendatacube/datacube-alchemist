import pathlib
import re
from functools import lru_cache

import requests
import structlog
import yaml
from yaml.scanner import ScannerError

_LOG = structlog.get_logger()


@lru_cache(maxsize=1024 * 2014 * 8)
def fetch_file(file_url):
    """
    Receves a http/https url and returns the content of the file.
    Cached for subsequent invocations
    """
    response = requests.get(file_url)
    return response.text


def get_config(config_file, properties):
    """
    Plain simple implementaion of config lookup for general purpose.
    Receives a YAML file as config_file and returns the value of the nested lookup.
    params:
    config_file: filepath or http path of the yaml file
    properties: list of keys or string,
        - if string returns the value of the key
        - if list/tuple returns the value of the nested.
        - String contains dot '.' will be treated as nested lookup
        - Raises KeyError if there is no relevant key found.
    """
    if re.match(r"(http|https)://", config_file):
        file_content = fetch_file(config_file)
    else:
        p = pathlib.Path(config_file)
        if not p.is_file():
            raise RuntimeError("config_file must be either a vaid http|https url or a valid filepath")
        file_content = open(config_file, "r").read()

    try:
        structure = yaml.safe_load(file_content)
        _LOG.info(f"Loaded configuration {structure}")
    except ScannerError:
        _LOG.exception(f"Config lookup failed for {properties} with {config_file}, Unable to proceed")
        raise RuntimeError(f"Config lookup failed for {properties} with {config_file}, Unable to proceed")

    if type(properties) == str:
        properties = properties.split(".")
        properties = map(
            lambda x: int(x) if x.isdigit() else x, properties
        )  # If there are convertible ints, convert them.

    for p in properties:
        structure = structure[p]  # Let it fail with KeyError if the lookup fails
    return structure
