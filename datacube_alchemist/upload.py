import tempfile
from distutils.dir_util import copy_tree
import fsspec


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
        fs.put(self._location, self.s3location, recursive=True)
    

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
    #local = "/home/osboxes/test_data"
    copy_tree(local, location)

    s3ul.upload_if_needed()


if __name__ == '__main__':
    main()
