import base64
import logging
import yaml
import requests
import os
from krkn_lib_kubernetes import ChaosRunTelemetry, ScenarioTelemetry


class KrknTelemetry:
    def send_telemetry(
        self,
        telemetry_config: dict,
        chaos_telemetry: ChaosRunTelemetry,
    ):
        """

        :param chaos_telemetry: already populated Chaos
        :param telemetry_config: krkn telemetry conf section
        :param scenario_input_file: path to the scenario input yaml
        :return:
        """
        enabled = telemetry_config.get("enabled")
        if enabled:
            url = telemetry_config.get("api_url")
            username = telemetry_config.get("username")
            password = telemetry_config.get("password")
            exceptions = []
            is_exception = False
            if url is None:
                exceptions.append("telemetry url is None")
                is_exception = True
            if username is None:
                exceptions.append("telemetry url is None")
                is_exception = True
            if password is None:
                exceptions.append("telemetry password is none")
                is_exception = True
            if is_exception:
                raise Exception(", ".join(exceptions))

            # load config file
            headers = {
                "Content-type": "application/json",
                "Accept": "text/plain",
            }
            request = requests.post(
                url=url,
                auth=(username, password),
                data=chaos_telemetry.to_json(),
                headers=headers,
            )

            if request.status_code != 200:
                logging.warning("failed to send telemetry with error: {0}")
            else:
                logging.info("successfully sent telemetry data")

    def set_parameters_base64(
        self, scenario_telemetry: ScenarioTelemetry, file_path: str
    ):
        input_file_data = ""
        input_file_yaml = None
        if not os.path.exists(file_path):
            raise Exception(
                "telemetry : scenario file not found {0} ".format(file_path)
            )

        with open(file_path, "rb") as file_stream:
            input_file_data = file_stream.read().decode("utf-8")
            if input_file_data is None:
                raise Exception(
                    "telemetry : empty scenario file {0} ".format(file_path)
                )
        try:
            input_file_yaml = yaml.safe_load(input_file_data)
            # anonymize kubeconfig option in input
            self.deep_set_attribute(
                "kubeconfig", "anonymized", input_file_yaml
            )
            input_file_data = yaml.safe_dump(input_file_yaml)
            input_file_base64 = base64.b64encode(
                input_file_data.encode()
            ).decode()
        except Exception as e:
            raise Exception("telemetry: {0}".format(str(e)))
        scenario_telemetry.parametersBase64 = input_file_base64

    def deep_set_attribute(self, attribute: str, value: str, obj: any) -> any:
        if isinstance(obj, list):
            for element in obj:
                self.deep_set_attribute(attribute, value, element)
        if isinstance(obj, dict):
            for key in obj.keys():
                if isinstance(obj[key], dict):
                    self.deep_set_attribute(attribute, value, obj[key])
                elif isinstance(obj[key], list):
                    for element in obj[key]:
                        self.deep_set_attribute(attribute, value, element)
                if key == attribute:
                    obj[key] = value
        return obj
