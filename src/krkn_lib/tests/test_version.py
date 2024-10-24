from krkn_lib.tests import BaseTest
from krkn_lib.version import __version__


class VersionTest(BaseTest):
    def test_version(self):
        version = __version__
        self.assertNotEqual(version, "0.0.0")
