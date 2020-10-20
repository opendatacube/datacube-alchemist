from datacube_alchemist.worker import Alchemist


def test_alchemist_local_config(config_file):
    alchemist = Alchemist(config_file=config_file)

    assert alchemist.transform_name == 'wofs.virtualproduct.WOfSClassifier'


def test_alchemist_remote_config(remote_config_file):
    alchemist = Alchemist(config_file=remote_config_file)

    assert alchemist.transform_name == 'wofs.virtualproduct.WOfSClassifier'


def test_help_message(run_alchemist):
    result = run_alchemist("--help")
    print(result)

    result = run_alchemist("run-one", "--help")
    print(result)

    result = run_alchemist("run-many", "--help")
    print(result)

    result = run_alchemist("add-to-queue", "--help")
    print(result)

    result = run_alchemist("run-from-queue", "--help")
    print(result)

    result = run_alchemist("redrive-to-queue", "--help")
    print(result)

