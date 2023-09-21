import datetime
import logging
import os
import sys
import re
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
        start_check = True
        end_check = True
        local_tz = pytz.timezone(local_timezone)
        remote_tz = pytz.timezone(remote_timezone)

        localized_log_date = None
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
                localized_log_date = parser.parse(
                    pattern.search(log_line).groups()[0]
                ).replace(tzinfo=remote_tz)
                break

        if start_timestamp is not None:
            start_date = datetime.datetime.fromtimestamp(start_timestamp)
            localized_start_date = local_tz.localize(start_date)
            start_check = localized_log_date >= localized_start_date
        if end_timestamp is not None:
            end_date = datetime.datetime.fromtimestamp(end_timestamp)
            localized_end_date = local_tz.localize(end_date)
            end_check = localized_log_date <= localized_end_date
        if start_check and end_check:
            return log_line
        else:
            return None
    except ParserError:
        logging.warning(f"failed to parse date from line: {log_line}")
        return None
    except TypeError:
        # if the line do not contains a valid date
        # the comparison fails and raises Type Error
        # the line is skipped.
        pass
    except Exception as e:
        logging.error(str(e))
        raise e


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
