from datacube_alchemist.worker import deterministic_uuid
from unittest import mock


def test_deterministic_uuid():
    mocked_task = mock.MagicMock()
    transform = 'wofs.virtualproduct.WOfSClassifier'
    mocked_task.settings.specification.transform = transform
    mocked_task.dataset.id = '81ad70a7-c02b-5f48-b10e-4b5d3ab49985'
    algorithm_version = '1.4'
    other_tags = {}
    mocked_task.settings.output.metadata = {}
    mocked_task.settings.output.metadata['dataset_version'] = '2.2.1'
    result, uuid_values = deterministic_uuid(mocked_task, algorithm_version='1.4', **other_tags)
    # print (result)
    # print (uuid_values)

    result, uuid_values = deterministic_uuid(mocked_task, **other_tags)
    # print (result)
    # print (uuid_values)


if __name__ == '__main__':
    test_deterministic_uuid()
