import base64
import os
import re
import tempfile

import yaml

import krkn_lib.utils as utils
from krkn_lib.tests import BaseTest
from krkn_lib.utils import (
    deep_set_attribute,
    filter_log_line,
    get_yaml_item_value,
    find_executable_in_path,
)


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

    def test_filter_file_log(self):
        pattern = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+")
        logs = [
            "2023-09-15T11:20:36.123425532Z before",
            "2023-09-15T11:28:00.000000000Z now",
            "2023-09-15T11:31:41.531143432Z after",
        ]
        # Friday, September 15, 2023 13:28:10 GMT+02:00 DST
        start_timestamp = 1694777280
        # Friday, September 15, 2023 13:30:00 AM
        end_timestamp = 1694777400

        self.assertIsNone(
            filter_log_line(
                logs[0],
                start_timestamp,
                end_timestamp,
                "UTC",
                "Europe/Rome",
                [pattern],
            )
        )
        self.assertIsNotNone(
            filter_log_line(
                logs[1],
                start_timestamp,
                end_timestamp,
                "UTC",
                "Europe/Rome",
                [pattern],
            )
        )
        self.assertIsNone(
            filter_log_line(
                logs[2],
                start_timestamp,
                end_timestamp,
                "UTC",
                "Europe/Rome",
                [pattern],
            )
        )

        # START TIMESTAMP ONLY
        # (RUN START TIMESTAMP) 13:28 GMT +2
        # >
        # 11:20 UTC (LOG TIME) = LOG SKIPPED
        self.assertIsNone(
            filter_log_line(
                logs[0], start_timestamp, None, "UTC", "Europe/Rome", [pattern]
            )
        )

        # without a top limit the third log is not skipped
        self.assertIsNotNone(
            filter_log_line(
                logs[2], start_timestamp, None, "UTC", "Europe/Rome", [pattern]
            )
        )

        self.assertIsNotNone(
            filter_log_line(
                logs[0], None, end_timestamp, "UTC", "Europe/Rome", [pattern]
            )
        )

        # if a pattern do not contains a group will raise an exception
        broken_pattern_no_group = re.compile(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z.+"
        )
        with self.assertRaises(Exception):
            self.assertIsNotNone(
                filter_log_line(
                    logs[2],
                    None,
                    end_timestamp,
                    "UTC",
                    "EST",
                    [broken_pattern_no_group],
                )
            )

        # if a pattern contains more than one group will raise an exception
        broken_pattern_multiple_groups = re.compile(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)(Z.+)"
        )

        with self.assertRaises(Exception):
            self.assertIsNotNone(
                filter_log_line(
                    logs[2],
                    None,
                    end_timestamp,
                    "UTC",
                    "EST",
                    [broken_pattern_multiple_groups],
                )
            )

    def test_get_yaml_item_value(self):
        cont = {"n_int": 1, "n_str": "value", "d_int": None, "d_str": None}

        n_int = get_yaml_item_value(cont, "n_int", 0)
        n_str = get_yaml_item_value(cont, "n_str", "default")
        d_int = get_yaml_item_value(cont, "d_int", 0)
        d_str = get_yaml_item_value(cont, "d_str", "default")

        self.assertEqual(n_int, 1)
        self.assertEqual(n_str, "value")
        self.assertEqual(d_int, 0)
        self.assertEqual(d_str, "default")

    def test_find_executable_in_path(self):
        path = find_executable_in_path("ls")
        self.assertIsNotNone(path)
        path = find_executable_in_path("do_not_exists")
        self.assertIsNone(path)
