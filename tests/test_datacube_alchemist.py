from unittest import mock

from datacube_alchemist.worker import deterministic_uuid, get_transform_info, _import_transform


def test_deterministic_uuid():
    mocked_task = mock.MagicMock()
    transform = 'wofs.virtualproduct.WOfSClassifier'
    mocked_task.settings.specification.transform = transform
    mocked_task.dataset.id = '81ad70a7-c02b-5f48-b10e-4b5d3ab49985'
    algorithm_version = '1.4'
    other_tags = {}
    mocked_task.settings.output.metadata = {}
    mocked_task.settings.output.metadata['dataset_version'] = '2.2.1'
    result, _ = deterministic_uuid(mocked_task, algorithm_version='1.4', **other_tags)
    assert str(result) == '262c465e-1930-58ae-853b-818c9dfdc089'

    result, _ = deterministic_uuid(mocked_task, **other_tags)
    # print (result)


def test_get_transform_info():
    transforms = ['wofs.virtualproduct.WOfSClassifier', 'fc.virtualproduct.FractionalCover']
    for transform in transforms:
        try:
            _ = _import_transform(transform)
        except (KeyError, ModuleNotFoundError) as e:
            # Silently skip if transforms aren't installed
            continue
        result = get_transform_info(transform)
        # print (result)


if __name__ == '__main__':
    test_deterministic_uuid()
    test_get_transform_info()
