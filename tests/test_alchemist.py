from unittest import mock

import pytest
from mock import patch

from datacube_alchemist._dask import setup_dask_client
from datacube_alchemist.cli import get_config
from datacube_alchemist.worker import Alchemist, execute_with_dask

def test_help_message(run_alchemist):
    result = run_alchemist("--help")
    print(result)

    result = run_alchemist("run-one", "--help")
    print(result)

    result = run_alchemist("run-many", "--help")
    print(result)

    result = run_alchemist("addtoqueue", "--help")
    print(result)

    # Todo: Extend this test case to cover all possible commands

@pytest.mark.skip(reason="Example doesn't exist yet")
def test_api():
    alchemist = Alchemist(
        config_file="test_config_file.yaml", dc_env="test_environment"
    )

    tasks = alchemist.generate_tasks([], limit=3)

    client = setup_dask_client(alchemist.config)
    execute_with_dask(client, tasks)

def test_get_config():
    """
    Test the get_config() method with some yaml as file content and http lookup
    """
    sample_yaml_content = """
hello: world
specification:
  product: ga_ls8c_ard_3
  measurements: ['nbart_green', 'nbart_red', 'nbart_nir', 'nbart_swir_1', 'nbart_swir_2']
  transform_args:
    regression_coefficients:
      blue:
        - 1
        - 2
        - 3
        """
    with patch("requests.get") as mock_request:
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = sample_yaml_content

        # Test for http based config files
        config_file = "http://fake.url/"

        # Test a simple string key lookup
        assert get_config(config_file, "hello") == "world"

        # Test nested lookup as list
        assert get_config(config_file, ["specification", "product"]) == "ga_ls8c_ard_3"

        # Test nested lookup as tuple
        assert get_config(config_file, ("specification", "product")) == "ga_ls8c_ard_3"

        # Test a nested lookup that returns a list
        assert get_config(config_file, ["specification", "measurements"]) == [
            "nbart_green",
            "nbart_red",
            "nbart_nir",
            "nbart_swir_1",
            "nbart_swir_2",
        ]

        # Test a nested lookup with dashed style list @ yaml side
        assert get_config(
            config_file,
            ["specification", "transform_args", "regression_coefficients", "blue"],
        ) == [1, 2, 3]

        # Test a lookup for non existing key and expect KeyError
        with pytest.raises(KeyError):
            get_config(config_file, ["random", "lookup", "key"])

    # Do all the above assertions for filebased yaml
    mock_open = mock.mock_open(read_data=sample_yaml_content)
    with mock.patch("builtins.open", mock_open):
        with patch("pathlib.Path.is_file") as mock_is_file:
            mock_is_file.return_value = True
            config_file = "/fake/path/fake.yaml"

            assert get_config(config_file, "hello") == "world"
            assert (
                    get_config(config_file, ["specification", "product"]) == "ga_ls8c_ard_3"
            )
            assert (
                    get_config(config_file, ("specification", "product")) == "ga_ls8c_ard_3"
            )
            assert get_config(config_file, ["specification", "measurements"]) == [
                "nbart_green",
                "nbart_red",
                "nbart_nir",
                "nbart_swir_1",
                "nbart_swir_2",
            ]
            assert get_config(
                config_file,
                ["specification", "transform_args", "regression_coefficients", "blue"],
            ) == [1, 2, 3]
            with pytest.raises(KeyError):
                get_config(config_file, ["random", "lookup", "key"])
