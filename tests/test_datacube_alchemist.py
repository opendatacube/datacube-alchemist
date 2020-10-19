from datacube_alchemist.worker import Alchemist


def test_alchemist_transform_name(config_file):
    alchemist = Alchemist(config_file=config_file)

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
