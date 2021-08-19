import json
from pathlib import Path

import datacube_alchemist.cli
import pytest
from click.testing import CliRunner


@pytest.fixture
def run_alchemist():
    """
    A helpful fixture for running a a click CLI from within pytest
    """

    def _run_cli(
        *opts,
        catch_exceptions=False,
        expect_success=True,
        cli_method=datacube_alchemist.cli.cli
    ):
        exe_opts = []
        exe_opts.extend(opts)

        runner = CliRunner()
        result = runner.invoke(cli_method, exe_opts, catch_exceptions=catch_exceptions)
        if expect_success:
            assert 0 == result.exit_code, "Error for %r. output: %r" % (
                opts,
                result.output,
            )
        return result

    return _run_cli


@pytest.fixture
def stac_example():
    stac_file = (
        Path(__file__).absolute().parent / "data/fc_ls_159069_2021-07-17.stac-item.json"
    )
    with open(stac_file) as f:
        return json.loads(f.read())


@pytest.fixture
def config_file():
    return Path(__file__).absolute().parent / "c3_config_wo_noresampling.yaml"


@pytest.fixture
def config_file_resampling():
    return Path(__file__).absolute().parent / "c3_config_wo_resampling.yaml"


@pytest.fixture
def remote_config_file():
    return "https://raw.githubusercontent.com/opendatacube/datacube-alchemist/main/examples/c3_config_wo.yaml"


@pytest.fixture
def config_file_bai_s2be():
    return Path(__file__).absolute().parent / "c3_config_bai_s2be.yaml"


@pytest.fixture
def config_file_3band_s2be():
    return Path(__file__).absolute().parent / "c3_config_dnbr_3band_s2be.yaml"
