import os
import tempfile
import boto3
import structlog
from distutils.dir_util import copy_tree
import shutil
import mimetypes
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse


mimetypes.add_type('application/x-yaml', '.yml')
mimetypes.add_type('application/x-yaml', '.yaml')

_LOG = structlog.get_logger()


class S3Url(object):
    """
    # https://stackoverflow.com/questions/42641315/s3-urls-get-bucket-name-and-path
    >>> s = S3Url("s3://bucket/hello/world")
    >>> s.bucket
    'bucket'
    >>> s.key
    'hello/world'
    >>> s.url
    's3://bucket/hello/world'
    """

    def __init__(self, url):
        self._parsed = urlparse(url, allow_fragments=False)

    @property
    def bucket(self):
        return self._parsed.netloc

    @property
    def key(self):
        if self._parsed.query:
            return self._parsed.path.lstrip('/') + '?' + self._parsed.query
        else:
            return self._parsed.path.lstrip('/')

    @property
    def url(self):
        return self._parsed.geturl()


def _upload(client, bucket, remote_path, local_file, mimetype=None):
    if mimetype is None:
        mimetype, _ = mimetypes.guess_type(local_file, strict=False)

    with open(local_file, 'rb') as data:
        extra_args = dict()

        if mimetype is not None:
            extra_args['ContentType'] = mimetype

        args = {'ExtraArgs': extra_args}
        _LOG.info('Uploading to: s3://' + bucket + '/' + remote_path)
        _LOG.info('local_file: ' + local_file)
        client.meta.client.upload_fileobj(
            Fileobj=data,
            Bucket=bucket,
            Key=remote_path,
            **args
        )


class S3Upload(object):
    def __init__(self, location):
        if location[0:2] == 's3':
            self.upload = True
            self.s3url = S3Url(location)
            self.tmp_results = tempfile.mkdtemp()
            self._location = self.tmp_results
        else:
            self.upload == False
            self._location = location

    @property
    def location(self):
        return self._location

    def upload_if_needed(self):
        if self.upload is True:
            self.upload_now()

    def upload_now(self):
        s3_resource = boto3.resource('s3')
        for subdir, dirs, files in os.walk(self.tmp_results):
            for afile in files:
                full_path = os.path.join(subdir, afile)
                rel_path = os.path.relpath(full_path, self.tmp_results)

                # Upload data to S3
                _upload(
                    s3_resource,
                    self.s3url.bucket,
                    os.path.join(self.s3url.key, rel_path),
                    local_file=full_path
                )
        shutil.rmtree(self.tmp_results)


def main():
    """
    Very hacky test.
    :return:
    """
    location = 's3://test-results-deafrica-staging-west/fc-alchemist-tests'

    s3ul = S3Upload(location)
    location = s3ul.location
    # This is the sort of data that execute produces (/2)
    local = "/g/data/u46/users/dsg547/data/c3-testing"
    local = "/home/osboxes/test_data"
    copy_tree(local, location)

    s3ul.upload_if_needed()


if __name__ == '__main__':
    main()
