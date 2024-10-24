import base64
import json
import os
import re
import tempfile

import yaml

import krkn_lib.utils as utils
from krkn_lib.tests import BaseTest
from krkn_lib.utils import (
    check_date_in_localized_interval,
    deep_set_attribute,
    filter_dictionary,
    filter_log_line,
    find_executable_in_path,
    get_junit_test_case,
    get_random_string,
    get_yaml_item_value,
    is_host_reachable,
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

    def test_deep_get(self):
        deep_yaml = """
            test:
                - namespace: "default"
                  property_1: test
                  property_2: test
                  obj_1:
                    namespace: "kubernetes"
                    obj_1:
                        element: __MARKER__
                        property_1: test
                        property_2:
                            - property_3: test
                              property_4: test
                            - property_5:
                                namespace: "kube-system"
            """  # NOQA

        yaml_obj = yaml.safe_load(deep_yaml)

        results = utils.deep_get_attribute("namespace", yaml_obj)
        self.assertEqual(len(results), 3)
        self.assertTrue("default" in results)
        self.assertTrue("kubernetes" in results)
        self.assertTrue("kube-system" in results)

    def test_check_date_in_localized_interval(self):
        timezone = "UTC"

        now = 1696408614  # Wednesday, October 4, 2023 8:36:54 AM
        in_ten_minutes = 1696409214  # Wednesday, October 4, 2023 8:46:54 AM
        ten_minutes_ago = 1696408014  # Wednesday, October 4, 2023 8:26:54 AM
        yesterday = 1696322214  # Tuesday, October 3, 2023 8:36:54 AM
        tomorrow = 1696495014  # Thursday, October 5, 2023 8:36:54 AM

        self.assertTrue(
            check_date_in_localized_interval(
                ten_minutes_ago,
                in_ten_minutes,
                now,
                timezone,
                timezone,
            )
        )

        self.assertFalse(
            check_date_in_localized_interval(
                ten_minutes_ago,
                in_ten_minutes,
                yesterday,
                timezone,
                timezone,
            )
        )

        self.assertFalse(
            check_date_in_localized_interval(
                ten_minutes_ago,
                in_ten_minutes,
                tomorrow,
                timezone,
                timezone,
            )
        )

        self.assertTrue(
            check_date_in_localized_interval(
                None,
                in_ten_minutes,
                yesterday,
                timezone,
                timezone,
            )
        )

        self.assertTrue(
            check_date_in_localized_interval(
                ten_minutes_ago,
                None,
                tomorrow,
                timezone,
                timezone,
            )
        )

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

    def test_filter_dictionary(self):
        event = """
                {
            "apiVersion": "v1",
            "count": 1,
            "eventTime": null,
            "firstTimestamp": "2023-10-04T09:51:06Z",
            "involvedObject": {
                "kind": "Node",
                "name": "ip-10-0-143-127.us-west-2.compute.internal",
                "uid": "ip-10-0-143-127.us-west-2.compute.internal"
            },
            "kind": "Event",
            "lastTimestamp": "2023-10-04T09:51:06Z",
            "message": "Starting kubelet.",
            "metadata": {
                "creationTimestamp": "2023-10-04T09:51:07Z",
                "name": "ip-10-0-143-127.us-west-2.compute.internal.178adeb2335c61fe",
                "namespace": "default",
                "resourceVersion": "13109",
                "uid": "e119423c-a5af-4bdc-b8ea-042d01390387"
            },
            "reason": "Starting",
            "reportingComponent": "",
            "reportingInstance": "",
            "source": {
                "component": "kubelet",
                "host": "ip-10-0-143-127.us-west-2.compute.internal"
            },
            "type": "Normal"
        }
        """  # NOQA
        ten_minutes_ago = 1696412513  # Wednesday, October 4, 2023 9:41:53 AM
        in_ten_minutes = 1696413713  # Wednesday, October 4, 2023 10:01:53 AM

        event_dict = json.loads(event)

        result = filter_dictionary(
            event_dict,
            "firstTimestamp",
            ten_minutes_ago,
            in_ten_minutes,
            "UTC",
            "UTC",
        )
        self.assertEqual(result, event_dict)

        result = filter_dictionary(
            event_dict,
            "firstTimestamp",
            in_ten_minutes,
            None,
            "UTC",
            "UTC",
        )

        self.assertIsNone(result)

        result = filter_dictionary(
            event_dict,
            "apiVersion",
            in_ten_minutes,
            None,
            "UTC",
            "UTC",
        )
        self.assertIsNone(result)

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

    def test_get_random_string(self):
        string_one = get_random_string(10)
        string_two = get_random_string(10)
        self.assertNotEquals(string_one, string_two)

    def test_is_host_reachable(self):
        self.assertTrue(is_host_reachable("www.google.com", 443))
        self.assertFalse(
            is_host_reachable(f"{get_random_string(10)}.com", 12345)
        )

    def test_get_junit_test_case(self):
        test_suite_name = "krkn-test"
        test_case_description_success = (
            "success [test-case] krkn-lib test case"
        )
        test_case_description_failure = (
            "failure [test-case] krkn-lib test case"
        )
        test_stdout = "KRKN STDOUT"
        test_version = "OCP 4.16"
        time = 10
        success_output = (
            f'<testsuite name="{test_suite_name}" tests="1" skipped="0" failures="0" time="10">'  # NOQA
            f'<property name="TestVersion" value="{test_version}" />'
            f'<testcase name="{test_case_description_success}" time="{time}" />'  # NOQA
            f"</testsuite>"
        )

        success_output_not_test_version = (
            f'<testsuite name="{test_suite_name}" tests="1" skipped="0" failures="0" time="10">'  # NOQA
            f'<testcase name="{test_case_description_success}" time="{time}" />'  # NOQA
            f"</testsuite>"
        )

        failure_output = (
            f'<testsuite name="{test_suite_name}" tests="1" skipped="0" failures="1" time="10">'  # NOQA
            f'<property name="TestVersion" value="{test_version}" />'
            f'<testcase name="{test_case_description_failure}" time="{time}">'
            f'<failure message="">{test_stdout}</failure>'
            f"</testcase>"
            f"</testsuite>"
        )
        success_test = get_junit_test_case(
            True,
            time,
            test_suite_name,
            test_case_description_success,
            test_stdout,
            test_version,
        )
        success_test_not_test_version = get_junit_test_case(
            True,
            time,
            test_suite_name,
            test_case_description_success,
            test_stdout,
        )

        failure_test = get_junit_test_case(
            False,
            time,
            test_suite_name,
            test_case_description_failure,
            test_stdout,
            test_version,
        )

        self.assertEqual(success_output, success_test)
        self.assertEqual(
            success_output_not_test_version, success_test_not_test_version
        )
        self.assertEqual(failure_output, failure_test)
