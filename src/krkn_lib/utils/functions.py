import datetime
import logging
import os
import random
import re
import socket
import string
import sys
import xml.etree.cElementTree as ET
from queue import Queue
from typing import Optional

import pytz
from base64io import Base64IO
from dateutil import parser
from dateutil.parser import ParserError


def decode_base64_file(source_filename: str, destination_filename: str):
    """
    Decodes a base64 file while it's read (no memory allocation).
    Suitable for big file conversion.

    :param source_filename: source base64 encoded file
    :param destination_filename: destination decoded file
    """
    with open(source_filename, "rb") as encoded_source, open(
        destination_filename, "wb"
    ) as target:
        with Base64IO(encoded_source) as source:
            for line in source:
                target.write(line)


def log_exception(scenario: str = None):
    """
    Logs an exception printing the file and the line
    number from where the method is called

    :param scenario: if set will include the scenario name in the log
    """
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if scenario is None:
        logging.error(
            "exception: %s file: %s line: %s",
            exc_type,
            exc_tb.tb_frame.f_code.co_filename,
            exc_tb.tb_lineno,
        )
    else:
        logging.error(
            "scenario: %s failed with exception: %s file: %s line: %s",
            scenario,
            exc_type,
            exc_tb.tb_frame.f_code.co_filename,
            exc_tb.tb_lineno,
        )


def deep_set_attribute(attribute: str, value: str, obj: any) -> any:
    """
    Recursively sets the attribute value in all the occurrences of the
    object.
    An example usage is to anonymize a yaml object setting all the
    occurrences of the property `kubeconfig` with a dummy value.

    :param attribute: the attribute name in the object
    :param value: the value that will be set in the attribute if present
    :param obj: the object that will be traversed and modified
    :return: obj
    """
    if isinstance(obj, list):
        for element in obj:
            deep_set_attribute(attribute, value, element)
    if isinstance(obj, dict):
        for key in obj.keys():
            if isinstance(obj[key], dict):
                deep_set_attribute(attribute, value, obj[key])
            elif isinstance(obj[key], list):
                for element in obj[key]:
                    deep_set_attribute(attribute, value, element)
            if key == attribute:
                obj[key] = value
    return obj


def deep_get_attribute(
    attribute: str, obj: any, values: list[any] = None
) -> list[any]:
    """
    Recursively finds the attribute value in all the occurrences of the
    object and returns the value.

    :param attribute: the attribute to search in the object
    :param obj: the object that will be traversed and modified
    :param values: the list of values found each step that will
        be recursively passed to the function itself each time.
        can be left empty.
    :return: a list of values found
    """
    if values is None:
        values = []
    if isinstance(obj, list):
        for element in obj:
            deep_get_attribute(attribute, element, values)
    if isinstance(obj, dict):
        for key in obj.keys():
            if isinstance(obj[key], dict):
                deep_get_attribute(attribute, obj[key], values)
            elif isinstance(obj[key], list):
                for element in obj[key]:
                    deep_get_attribute(attribute, element, values)
            if key == attribute:
                values.append(obj[key])
    return values


def check_date_in_localized_interval(
    start_timestamp: Optional[int],
    end_timestamp: Optional[int],
    check_timestamp: int,
    check_timezone: str,
    interval_timezone: str,
) -> bool:
    """
    Checks if a timestamp is within an interval localizing with timezones

    :param start_timestamp: bottom limit of the interval, if None no bottom
        limit is set
    :param end_timestamp: top limit of the interval, if None no top limit is
        set
    :param check_timestamp: timestamp checked in the interval
    :param check_timezone: timezone string to be applied to the check timestamp
    :param interval_timezone: timezone string to be applied to the interval
        timestamps
    """

    start_check = True
    end_check = True

    interval_tz = pytz.timezone(interval_timezone)
    check_tz = pytz.timezone(check_timezone)

    localized_check_date = datetime.datetime.fromtimestamp(
        check_timestamp, tz=check_tz
    )

    if start_timestamp is not None:
        start_date = datetime.datetime.fromtimestamp(
            start_timestamp, tz=interval_tz
        )
        start_check = localized_check_date >= start_date
    if end_timestamp is not None:
        end_date = datetime.datetime.fromtimestamp(
            end_timestamp, tz=interval_tz
        )
        end_check = localized_check_date <= end_date

    return start_check and end_check


def filter_log_line(
    log_line: str,
    start_timestamp: Optional[int],
    end_timestamp: Optional[int],
    remote_timezone: str,
    local_timezone: str,
    log_filter_patterns: [re.Pattern[str]],
) -> Optional[str]:
    """
    Filters a log line extracting time informations using a set of compiled
    regular expressions containing excatly one group.

    :param start_timestamp: timestamp representing the minimum date after that
        the log becomes relevant, if None no bottom limit applied
    :param end_timestamp: timestamp representing the maximum date before that
        the log is still relevant, if None no top limit applied
    :param remote_timezone: timezone of the system from where the log has been
        extracted
    :param local_timezone: timezone of the client that is parsing the log

    :param log_filter_patterns: a list of regex that will match
        and extract the time info that will be
        parsed by dateutil.parser (it supports several formats
        by default but not every date format).
        Each pattern *must contain* only 1 group that represent
        the time string that must be extracted
        and parsed

    :return: the log line if matches the criteria above otherwise None
    """
    try:
        if len(log_filter_patterns) == 0:
            logging.error(
                "no log filter patterns has been defined in config file,"
                "unable to filter logfile. Skipping"
            )
            return None
        log_date = None
        for pattern in log_filter_patterns:
            if pattern.groups != 1:
                logging.error(
                    f"{pattern} it's not a valid pattern, "
                    f"it must contain only one group that "
                    f"represents the date to be parsed, skipping"
                )
                raise Exception(
                    f"{pattern} it's not a valid pattern, it must "
                    f"contain only one group that represents "
                    f"the date to be parsed, skipping"
                )
            if pattern.match(log_line):
                log_date = parser.parse(pattern.search(log_line).groups()[0])
                break

        is_in_interval = False
        if log_date is not None and isinstance(log_date, datetime.datetime):
            is_in_interval = check_date_in_localized_interval(
                start_timestamp,
                end_timestamp,
                int(log_date.timestamp()),
                remote_timezone,
                local_timezone,
            )

        if is_in_interval:
            return log_line

        return None
    except ParserError:
        logging.warning(f"failed to parse date from line: {log_line}")
        return None
    except TypeError:
        # if the line do not contains a valid date
        # the comparison fails and raises Type Error
        # the line is skipped.
        return None
    except Exception as e:
        logging.error(str(e))
        raise e


def filter_dictionary(
    dictionary: dict[str, any],
    datetime_key: str,
    start_timestamp: Optional[int],
    end_timestamp: Optional[int],
    dictionary_timezone: str,
    interval_timezone: str,
) -> Optional[dict[str, any]]:
    """
    Filters a dictionary by datetime string attribute

    :param dictionary: the dictionary that needs to be filtered
    :param datetime_key: the key of the dictionary representing
        the time of the dictionary
    :param start_timestamp: timestamp representing the minimum date after that
        the dictionary becomes relevant, if None no bottom limit applied
    :param end_timestamp: timestamp representing the maximum date before that
        the dictionary is still relevant, if None no top limit applied
    :param dictionary_timezone: timezone of the date contained
        in the dictionary
    :param interval_timezone: timezone of the interval within
        the dictionary will be checked
    """
    date_time = dictionary.get(datetime_key)
    if not date_time:
        return None

    try:
        log_date = parser.parse(date_time)
        if check_date_in_localized_interval(
            start_timestamp,
            end_timestamp,
            int(log_date.timestamp()),
            dictionary_timezone,
            interval_timezone,
        ):
            return dictionary
        return None
    except ParserError:
        logging.error(f"impossible to parse date: {str(date_time)}")
        return None
    except TypeError:
        logging.error(f"{str(date_time)} does not represent a valid datetime")
        return None


def filter_log_file_worker(
    start_timestamp: Optional[int],
    end_timestamp: Optional[int],
    src_folder: str,
    dst_folder: str,
    remote_timezone: str,
    local_timezone: str,
    log_filter_patterns: list[str],
    queue: Queue,
):
    """
    Log file filter worker. Filters a file scanning
    each line (naive approach, no algorithms impletemented for
    this first version) and extracting time infos
    matching it with the provided regular expression and time range.

    :param start_timestamp: timestamp of the first relevant entry, if None
        will start filter starting from the earliest
    :param end_timestamp: timestamp of the last relevant entry, if None
        will end filtering until the latest
    :param src_folder: used to remove from the final filtered
        log name the base directory that is not relevant
    :param dst_folder: output folder where the filtered file will be placed
    :param local_timezone: timezone of the client
    :param remote_timezone: timezone of the system from
        which the logs have been extracted
    :param log_filter_patterns: a list of regex that will match and
        extract the time info that will be parsed by dateutil.parser
        (it supports several formats by default but not every date format).
        Each pattern *must contain* only 1 group that represent the time
        string that must be extracted and parsed
    :param queue: a queue containing `pathlib.Path` objects
        representing the log file to be parsed

    """

    # precompile patterns to speed up the parsing
    patterns = list(map(re.compile, log_filter_patterns))

    while not queue.empty():
        file = queue.get()
        try:
            filtered_log_file_name = str(file)
            filtered_log_file_name = filtered_log_file_name.replace(
                src_folder, ""
            )
            filtered_log_file_name = filtered_log_file_name.replace("/", ".")
            if filtered_log_file_name.startswith("."):
                filtered_log_file_name = filtered_log_file_name[1:]
            with file.open(mode="r") as read_file:
                with open(
                    os.path.join(dst_folder, filtered_log_file_name),
                    mode="x+t",
                ) as write_file:
                    line_count = 0
                    for line in read_file:
                        filtered_line = filter_log_line(
                            line,
                            start_timestamp,
                            end_timestamp,
                            remote_timezone,
                            local_timezone,
                            patterns,
                        )
                        if filtered_line is not None:
                            line_count += 1
                            write_file.write(filtered_line)
                read_file.flush()
                # if the file is empty is removed
                if line_count == 0:
                    os.unlink(os.path.join(dst_folder, filtered_log_file_name))
        except UnicodeDecodeError:
            logging.error(
                f"file {str(file)} contains invalid "
                f"unicode characters, skipping "
            )
            pass
        except Exception as e:
            logging.error(
                f"failed to parse file : {str(file)} "
                f"due to exception: {str(e)}"
            )
            raise e
        finally:
            queue.task_done()


def get_yaml_item_value(cont: dict[str, any], item: str, default: any) -> any:
    """
    Sets the value of item from yaml.

    :param cont: dict of all items from yaml file
    :param item: name of the item in scenario yaml
    :param default: default value
    :return: item value - if not specified the default value is returned
    """
    return default if cont.get(item) is None else cont.get(item)


def find_executable_in_path(executable_name: str) -> Optional[str]:
    path = os.getenv("PATH")
    for subpath in path.split(":"):
        test_path = os.path.join(subpath, executable_name)
        if os.path.exists(test_path):
            if os.access(test_path, os.X_OK):
                return test_path
    return None


def get_random_string(length: int) -> str:
    """
    Returns a random lowercase string of lenght `length`

    :param length: the lenght of the string
    :return: the random string
    """
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


def is_host_reachable(host: str, port: int, timeout: int = 2) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def get_junit_test_case(
    success: bool,
    time: int,
    test_suite_name: str,
    test_case_description: str,
    test_stdout: str = "",
    test_version: str = None,
) -> str:
    """
    Creates an XML compatible with sippy to track regressions
    on OCP tests.

    :param success: if true will print a success test case,
        otherwise a failure test case
    :param time: sets the duration in seconds of the testsuite
    :param test_suite_name: sets the name of the test suite
    :param test_case_description: sets the description of
        the testcase, it has to contain tags that map the test case
        to the monitored component on sippy like [sig-etcd]
        or others
    :param test_stdout: if a test failes the stdout of the krkn-run
        is attached to the testcase element in the XML
    :param test_version: sets an optional property to the testsuite
        containing the version on the test
    :return: the XML string to be written in the junit xml file
    """

    root = ET.Element("testsuite")
    root.attrib["name"] = test_suite_name
    root.attrib["tests"] = "1"
    root.attrib["skipped"] = "0"
    root.attrib["failures"] = "0" if success else "1"
    root.attrib["time"] = f"{time}"
    if test_version:
        ET.SubElement(root, "property", name="TestVersion", value=test_version)

    test_case = ET.SubElement(
        root, "testcase", name=test_case_description, time=f"{time}"
    )
    if not success:
        ET.SubElement(test_case, "failure", message="").text = test_stdout

    return ET.tostring(root, encoding="utf-8").decode("UTF-8")
