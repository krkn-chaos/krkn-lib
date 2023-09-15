import logging
import sys

from base64io import Base64IO


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


def get_scenario_items(cont: dict[str, any], item: str, default: any) -> any:
    """
    Sets the value of item from scenario yaml.

    :param cont: content of scenario yaml file
    :param item: the name of the item in scenario yaml
    :param default: the default value
    :return: item value - if not specified the default value is returned
    """
    return default if cont.get(item) is None else cont.get(item)
