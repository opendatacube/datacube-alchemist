from datacube_alchemist._utils import get_transform_info
from datacube_alchemist.worker import Alchemist


def test_alchemist_local_config(config_file):
    alchemist = Alchemist(config_file=config_file)

    assert alchemist.transform_name == "wofs.virtualproduct.WOfSClassifier"


def test_alchemist_remote_config(remote_config_file):
    alchemist = Alchemist(config_file=remote_config_file)

    assert alchemist.transform_name == "wofs.virtualproduct.WOfSClassifier"


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


def test_get_transform_info():
    transform_name = "datacube_alchemist.fake.Transform"
    info = get_transform_info(transform_name)

    for key in ["version", "url", "version_major_minor"]:
        assert key in info
        assert isinstance(info[key], str)
        assert len(info[key]) > 0

    assert info["url"].startswith("https")
