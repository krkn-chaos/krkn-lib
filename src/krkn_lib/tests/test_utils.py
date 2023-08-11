import base64
import os
import tempfile

import yaml
import krkn_lib.utils as utils
from base_test import BaseTest
from krkn_lib.utils import deep_set_attribute


class UtilFunctionTests(BaseTest):
    def test_decode_base64_file(self):
        workdir_basepath = os.getenv("TEST_WORKDIR")
        workdir = self.get_random_string(10)
        test_workdir = os.path.join(workdir_basepath, workdir)
        os.mkdir(test_workdir)
        test_string = "Tester McTesty!"
        with tempfile.NamedTemporaryFile(
            dir=test_workdir
        ) as src, tempfile.NamedTemporaryFile(
            dir=test_workdir
        ) as dst:  # NOQA
            with open(src.name, "w+") as source, open(dst.name, "w+") as dest:
                encoded_test_byte = base64.b64encode(
                    test_string.encode("utf-8")
                )
                source.write(encoded_test_byte.decode("utf-8"))
                source.flush()
                utils.decode_base64_file(source.name, dest.name)
                test_read = dest.read()
                self.assertEqual(test_string, test_read)
                self.assertEqual(test_string, test_read)

    def test_deep_set_attribute(self):
        deep_yaml = """
            test:
                - element: __MARKER__
                  property_1: test
                  property_2: test
                  obj_1:
                    element: __MARKER__
                    obj_1:
                        element: __MARKER__
                        property_1: test
                        property_2:
                            - property_3: test
                              property_4: test
                            - property_5:
                                element: __MARKER__
            """  # NOQA

        deep_obj = yaml.safe_load(deep_yaml)
        deep_set_attribute("element", "__UPDATED__", deep_obj)

        unserialized_updated_object = yaml.safe_dump(deep_obj, indent=4)
        self.assertEqual(unserialized_updated_object.count("__UPDATED__"), 4)
        self.assertEqual(unserialized_updated_object.count("__MARKER__"), 0)
