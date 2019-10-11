import tempfile
import os
from distutils.dir_util import copy_tree
import fsspec
from pathlib import Path

def _files_to_copy(src_base, dst_base):
    src_base = Path(src_base)
    src_base = src_base.absolute()
    n_skip = len(str(src_base))

    for base, _, files in os.walk(src_base):
        b = Path(base)
        for f in files:
            src = b/f
            dst = str(src)[n_skip:]
            yield (src, dst_base  + dst)

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
            self.upload_now()

    def upload_now(self):
        fs = fsspec.filesystem('s3')
        #fs.put(self._location, self.s3location, recursive=True)
        for f_src, f_dst in _files_to_copy(self._location, self.s3location):
            fs.put(str(f_src), str(f_dst))
    

def main():
    """
    Very hacky test.
    :return:
    """
    location = 's3://test-results-deafrica-staging-west/fc-alchemist-tests'

    s3ul = S3Upload(location)
    location = s3ul.location
    # This is the sort of data that execute produces (/2)
    local = "/g/data/u46/users/dsg547/test_data/wofs_testing_bitmask"
    #local = "/g/data/u46/users/dsg547/data/c3-testing"
    #local = "/home/osboxes/test_data"
    copy_tree(local, location)

    s3ul.upload_if_needed()


if __name__ == '__main__':
    main()
