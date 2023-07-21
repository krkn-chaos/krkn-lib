import base64
import logging
import sys
from typing import Optional

import yaml
import requests
import os
from krkn_lib_kubernetes import (
    ChaosRunTelemetry,
    ScenarioTelemetry,
    KrknLibKubernetes,
)


class KrknTelemetry:
    def send_telemetry(
        self,
        telemetry_config: dict,
        uuid: str,
        chaos_telemetry: ChaosRunTelemetry,
        kubecli: KrknLibKubernetes,
    ):
        """
        :param telemetry_config: krkn telemetry conf section
        :param uuid: uuid used as folder in S3 bucket
        :param chaos_telemetry: already populated ChaosRunTelemetry object
        :param kubecli: KrknLibKubernetes client object
        :return:
        """
        enabled = telemetry_config.get("enabled")
        if enabled:
            logging.info("collecting telemetry data, please wait....")
            chaos_telemetry.cloud_infrastructure = (
                kubecli.get_cluster_infrastructure()
            )
            chaos_telemetry.network_plugins = (
                kubecli.get_cluster_network_plugins()
            )
            chaos_telemetry.kubernetes_objects_count = (
                kubecli.get_all_kubernetes_object_count(
                    [
                        "Deployment",
                        "Pod",
                        "Secret",
                        "ConfigMap",
                        "Build",
                        "Route",
                    ]
                )
            )
            chaos_telemetry.node_infos = kubecli.get_nodes_infos()
            chaos_telemetry.node_count = len(chaos_telemetry.node_infos)

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
            json_data = chaos_telemetry.to_json()
            request = requests.post(
                url=url,
                auth=(username, password),
                data=json_data,
                params={"request_id": uuid},
                headers=headers,
            )

            if request.status_code != 200:
                logging.warning("failed to send telemetry with error: {0}")
            else:
                logging.info("successfully sent telemetry data")

    def get_ocp_prometheus_data(
        self,
        kubecli: KrknLibKubernetes,
        telemetry_config: dict,
        local_archive_path: str = "/tmp",
    ) -> Optional[str]:
        """
        Downloads the OCP prometheus metrics folder
        :param kubecli: KrknLibKubernetes client object
        :param telemetry_config: krkn telemetry conf section
        :param local_archive_path: local path where the archive
        will be stored
        :return:
        """
        prometheus_pod_name = "prometheus-k8s-0"
        prometheus_container_name = "prometheus"
        prometheus_namespace = "openshift-monitoring"
        remote_archive_path = "/prometheus"
        prometheus_pod = kubecli.get_pod_info(
            prometheus_pod_name, prometheus_namespace
        )
        if not prometheus_pod:
            return None
        try:
            archive_name = kubecli.download_folder_from_pod_as_archive(
                prometheus_pod_name,
                prometheus_container_name,
                prometheus_namespace,
                remote_archive_path,
                remote_archive_path,
            )
            return archive_name
        except Exception as e:
            logging.error(
                f"failed to download prometheus backup"
                f" on pod: {prometheus_pod_name},"
                f" container: {prometheus_container_name},"
                f" namespace: {prometheus_namespace}:"
                f" {str(e)}"
            )

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

    # move it to utils package
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

    def log_exception(self, scenario: str = None):
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
