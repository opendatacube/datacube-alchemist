import os
import tempfile
import boto3
from distutils.dir_util import copy_tree
from pathlib import Path
import mimetypes
from urlparse import urlparse


mimetypes.add_type('application/x-yaml', '.yml')
mimetypes.add_type('application/x-yaml', '.yaml')

def _files_to_copy(src_base, dst_base):
    src_base = Path(src_base)
    src_base = src_base.absolute()
    n_skip = len(str(src_base))

    for base, _, files in os.walk(src_base):
        b = Path(base)
        for f in files:
            src = b / f
            dst = str(src)[n_skip:]
            yield (src, dst_base + dst)


class S3Upload(object):
    def __init__(self, location):
        if location[0:2] == 's3':
            self.upload = True
            self.tmp_results = tempfile.mkdtemp()
            self._location = self.tmp_results
            self.s3location = location
        else:
            self._location = location
            self.upload = False

    @property
    def location(self):
        return self._location

    def upload_if_needed(self):
        """
        If the data needs to be moved from a tmp location to s3 do the move.
        """
        if self.upload is True:
            self.upload_now_change_control()

    def upload_now_change_control(self):
        s3_resource = boto3.resource('s3')
        for f_src, f_dst in _files_to_copy(self._location, self.s3location):
            o = urlparse(str(f_dst), allow_fragments=False)
            bucket = o.netloc
            key = o.path.lstrip('/')
            mimetype, _ = mimetypes.guess_type(str(f_src), strict=False)
            args = {'ExtraArgs': {'ContentType': mimetype}}
            with open(f_src, 'rb') as data:
                s3_resource.meta.client.upload_fileobj(
                    Fileobj=data,
                    Bucket=bucket,
                    Key=key,
                    **args
                )
                s3_resource.ObjectAcl(bucket, key).put(ACL='bucket-owner-full-control')

def main():
    """
    Very hacky test.
    :return:
    """
    location = 's3://dea-public-data-dev/alchemist/tests'

    s3ul = S3Upload(location)
    location = s3ul.location
    local = "/home/osboxes/dump2"
    copy_tree(local, location)

    s3ul.upload_if_needed()


if __name__ == '__main__':
    main()
