from datacube_alchemist._dask import setup_dask_client
from datacube_alchemist.worker import Alchemist, execute_with_dask
import pytest

def test_help_message(run_alchemist):
    result = run_alchemist('--help')
    print(result)

    result = run_alchemist('run-one', '--help')
    print(result)

    result = run_alchemist('run-many', '--help')
    print(result)

    result = run_alchemist('addtoqueue', '--help')
    print(result)

    result = run_alchemist('pullfromqueue', '--help')
    print(result)

    result = run_alchemist('processqueue', '--help')
    print(result)

@pytest.mark.skip(reason="Example doesn't exist yet")
def test_api():
    alchemist = Alchemist(config_file='test_config_file.yaml',
                          dc_env='test_environment')

    tasks = alchemist.generate_tasks([], limit=3)

    client = setup_dask_client(alchemist.config)
    execute_with_dask(client, tasks)
