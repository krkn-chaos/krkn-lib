import ast
import logging
import os
import shutil
import subprocess
import tarfile
import threading
from collections import namedtuple
from pathlib import Path
from queue import Queue
from typing import Optional

from tzlocal import get_localzone

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.utils import SafeLogger, filter_log_file_worker


class KrknOpenshift(KrknKubernetes):
    def __init__(
        self,
        kubeconfig_path: str = None,
    ):
        super().__init__(
            kubeconfig_path=kubeconfig_path,
        )

    def get_clusterversion_string(self) -> str:
        """
        Return clusterversion status text on OpenShift, empty string
        on other distributions

        :return: clusterversion status
        """

        return self._get_clusterversion_string()

    def get_cluster_type(self) -> str:
        """
        Get the cluster Cloud infrastructure type when available
        status:
            platformStatus:
                aws:
                region: us-west-2
                resourceTags:
                - key: prowci
                    value: ci-rosa-**
                - key: red-hat-clustertype
                    value: rosa
                - key: red-hat-managed
                    value: "true"
                type: AWS

        :return: the cluster type (ex. rosa) or `self-managed` when unavailable
        """
        api_client = self.api_client
        if api_client:
            try:
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/config.openshift.io/v1/infrastructures/cluster"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                json_obj = ast.literal_eval(data[0])
                platform = json_obj["status"]["platform"].lower()
                if (
                    "resourceTags"
                    in json_obj["status"]["platformStatus"][platform]
                ):
                    resource_tags = json_obj["status"]["platformStatus"][
                        platform
                    ]["resourceTags"]
                    for rt in resource_tags:
                        if rt["key"] == "red-hat-clustertype":
                            return rt["value"]
                return "self-managed"
            except Exception as e:
                logging.warning("V1ApiException -> %s", str(e))
                return "self-managed"

        return None

    def get_cloud_infrastructure(self) -> str:
        """
        Get the cluster Cloud infrastructure name when available

        :return: the cluster infrastructure name or `Unknown` when unavailable
        """
        api_client = self.api_client
        if api_client:
            try:
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/config.openshift.io/v1/infrastructures/cluster"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                json_obj = ast.literal_eval(data[0])
                return json_obj["status"]["platform"]
            except Exception as e:
                logging.warning("V1ApiException -> %s", str(e))
                return "Unknown"

        return None

    def get_cluster_network_plugins(self) -> list[str]:
        """
        Get the cluster Cloud network plugins list

        :return: the cluster infrastructure name or `Unknown` when unavailable
        """
        api_client = self.api_client
        network_plugins = list[str]()
        if api_client:
            try:
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/config.openshift.io/v1/networks"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                json_obj = ast.literal_eval(data[0])
                for plugin in json_obj["items"]:
                    network_plugins.append(plugin["status"]["networkType"])
            except Exception as e:
                logging.warning(
                    "Impossible to retrieve cluster Network plugins  -> %s",
                    str(e),
                )
                network_plugins.append("Unknown")
        return network_plugins

    def filter_must_gather_ocp_log_folder(
        self,
        src_dir: str,
        dst_dir: str,
        start_timestamp: Optional[int],
        end_timestamp: Optional[int],
        log_files_extension: str,
        threads: int,
        log_filter_patterns: list[str],
    ):
        """
        Filters a folder containing logs collected by the
        `oc adm must-gather` command
        (usually logs) with a given extension.
        The time info is extracted matching each line against
        the patterns passed as parameters and within the time
        range between `start_timestamp`
        and `end_timestamp`. if start and end timestamp
        are None the bottom and top time limit
        will be removed respectively. The filtering is multithreaded.
        The timezone of the client and the cluster will
        be applied to the filter and the records.
        If a file does not contain relevant rows in the
        time range won't be written in the
        dst_dir
        The output of the filter will be the original file name
        with all the folder structure (base
        folder not included) added as a prefix and
        separated by a dot, eg.
        src_dir: /tmp/folder
        dst_dir: /tmp/filtered
        log_file: /tmp/folder/namespaces/openshift-monitoring/pods/prometheus-k8s-0/logs/current.log # NOQA
        output: /tmp/filtered/namespaces.openshift-monitoring.pods.prometheus-k8s-0.logs.current.log # NOQA


        :param src_dir: the folder containing the files to be filtered
        :param dst_dir: the folder where the filtered logs will be written
        :param start_timestamp: timestamp of the first relevant entry, if None
            will start from the beginning
        :param end_timestamp: timestamp of the last relevant entry, if None
            will be collected until the latest
        :param log_files_extension: the extension of the files that will be filtered
            using wildcards (* will consider all the files, log_file_name.log will consider only this file)
        :param threads: the number of threads that will do the job
        :param log_filter_patterns: a list of regex that will match and extract the time info that will be
            parsed by dateutil.parser (it supports several formats by default but not every date format).
            Each pattern *must contain* only 1 group that represent the time string that must be extracted
            and parsed
        """

        if "~" in src_dir:
            src_dir = os.path.expanduser(src_dir)
        download_folder = [f.path for f in os.scandir(src_dir) if f.is_dir()]
        data_folder = [
            f.path for f in os.scandir(download_folder[0]) if f.is_dir()
        ]
        # default remote timestamp will be utc
        remote_timezone = "UTC"
        local_timezone = f"{get_localzone()}"

        if os.path.exists(os.path.join(data_folder[0], "timestamp")):
            with open(
                os.path.join(data_folder[0], "timestamp"), mode="r"
            ) as timestamp_file:
                line = timestamp_file.readline()
                remote_timezone = line.split()[3]
        if not os.path.exists(dst_dir):
            logging.error("Log destination dir do not exist")
            raise Exception("Log destination dir do not exist")
        queue = Queue()
        log_files = list(Path(data_folder[0]).rglob(log_files_extension))
        for file in log_files:
            queue.put(file)

        try:
            for _ in range(threads):
                worker = threading.Thread(
                    target=filter_log_file_worker,
                    args=(
                        start_timestamp,
                        end_timestamp,
                        data_folder[0],
                        dst_dir,
                        remote_timezone,
                        local_timezone,
                        log_filter_patterns,
                        queue,
                    ),
                )
                worker.daemon = True
                worker.start()
            queue.join()
        except Exception as e:
            logging.error(f"failed to filter log folder: {str(e)}")
            raise e

    def collect_filter_archive_ocp_logs(
        self,
        src_dir: str,
        dst_dir: str,
        kubeconfig_path: str,
        start_timestamp: Optional[int],
        end_timestamp: Optional[int],
        log_filter_patterns: list[str],
        threads: int,
        safe_logger: SafeLogger,
        namespace: str = None,
        oc_path: str = None,
    ) -> str:
        """
        Collects, filters and finally creates a tar.gz archive containing
        the filtered logs matching the criteria passed as parameters.
        The logs are used leveraging the oc CLI with must-gather option
        (`oc adm must-gather`)

        :param src_dir: the folder containing the files to be filtered
        :param dst_dir: the folder where the filtered logs will be written
        :param kubeconfig_path: path of the kubeconfig file used by the `oc`
            CLI to gather the log files from the cluster
        :param start_timestamp: timestamp of the first relevant entry, if None
            will start from the beginning
        :param end_timestamp: timestamp of the last relevant entry, if None
            will be collected until the latest
        :param threads: the number of threads that will do the job
        :param log_filter_patterns: a list of regex that will match and
            extract the time info that will be parsed by dateutil.parser
            (it supports several formats by default but not every date format)
        :param safe_logger: thread safe logger used to log
            the output on a file stream
        :param namespace: if set the logs will refer only to the provided
            namespace
        :param oc_path: the path of the `oc` CLI, if None will
            be searched in the PATH

        :return: the path of the archive containing the filtered logs
        """

        OC_COMMAND = "oc"

        if oc_path is None and shutil.which(OC_COMMAND) is None:
            safe_logger.error(
                f"{OC_COMMAND} command not found in $PATH,"
                f" skipping log collection"
            )
            return
        oc = shutil.which(OC_COMMAND)
        if oc_path is not None:
            if not os.path.exists(oc_path):
                safe_logger.error(
                    f"provided oc command path: {oc_path} is not valid"
                )
                raise Exception(
                    f"provided oc command path: {oc_path} is not valid"
                )
            else:
                oc = oc_path

        if "~" in kubeconfig_path:
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
        if "~" in src_dir:
            src_dir = os.path.expanduser(src_dir)
        if "~" in dst_dir:
            dst_dir = os.path.expanduser(dst_dir)

        if not os.path.exists(kubeconfig_path):
            safe_logger.error(
                f"provided kubeconfig path: {kubeconfig_path} is not valid"
            )
            raise Exception(
                f"provided kubeconfig path: {kubeconfig_path} is not valid"
            )

        if not os.path.exists(src_dir):
            safe_logger.error(f"provided workdir path: {src_dir} is not valid")
            raise Exception(f"provided workdir path: {src_dir} is not valid")

        if not os.path.exists(dst_dir):
            safe_logger.error(f"provided workdir path: {dst_dir} is not valid")
            raise Exception(f"provided workdir path: {dst_dir} is not valid")

        # COLLECT: run must-gather in workdir folder
        cur_dir = os.getcwd()
        os.chdir(src_dir)
        safe_logger.info(f"collecting openshift logs in {src_dir}...")
        try:
            if namespace:
                subprocess.Popen(
                    [
                        oc,
                        "adm",
                        "inspect",
                        f"ns/{namespace}",
                        "--kubeconfig",
                        kubeconfig_path,
                    ],
                    stdout=subprocess.DEVNULL,
                ).wait()
            else:
                subprocess.Popen(
                    [
                        oc,
                        "adm",
                        "must-gather",
                        "--kubeconfig",
                        kubeconfig_path,
                    ],
                    stdout=subprocess.DEVNULL,
                ).wait()
            os.chdir(cur_dir)
        except Exception as e:
            safe_logger.error(
                f"failed to collect data from openshift "
                f"with oc command: {str(e)}"
            )
            raise e

        # FILTER: filtering logs in
        try:
            safe_logger.info(f"filtering openshift logs in {dst_dir}...")
            self.filter_must_gather_ocp_log_folder(
                src_dir,
                dst_dir,
                start_timestamp,
                end_timestamp,
                "*.log",
                threads,
                log_filter_patterns,
            )
        except Exception as e:
            safe_logger.error(f"failed to filter logs: {str(e)}")
            raise e

        # ARCHIVE: creating tar archive of filtered files
        archive_name = os.path.join(dst_dir, "logs.tar.gz")
        try:
            with tarfile.open(archive_name, "w:gz") as tar:
                for file in os.listdir(dst_dir):
                    path = os.path.join(dst_dir, file)
                    tar.add(path, arcname=file)
        except Exception as e:
            safe_logger.error(f"failed to create logs archive: {str(e)}")

        return archive_name

    def get_prometheus_api_connection_data(
        self, namespace: str = "openshift-monitoring"
    ) -> Optional[
        namedtuple("PrometheusConnectionData", ["token", "endpoint"])  # NOQA
    ]:
        named_tuple = namedtuple(
            "PrometheusConnectionData", ["token", "endpoint"]
        )
        prometheus_namespace = "openshift-monitoring"
        prometheus_route = "prometheus-k8s"
        token = self.create_token_for_sa(
            prometheus_namespace, "prometheus-k8s"
        )
        if token is None:
            return None

        try:
            path = (
                "/apis/route.openshift.io/v1/"
                "namespaces/openshift-monitoring/routes"
            )
            path_params: dict[str, str] = {}
            query_params: list[str] = []
            header_params: dict[str, str] = {}
            auth_settings = ["BearerToken"]
            header_params["Accept"] = self.api_client.select_header_accept(
                ["application/json"]
            )

            (data) = self.api_client.call_api(
                path,
                "GET",
                path_params,
                query_params,
                header_params,
                response_type="str",
                auth_settings=auth_settings,
            )
            json_obj = ast.literal_eval(data[0])
            endpoint = None
            for item in json_obj["items"]:
                if item["metadata"]["name"] == "prometheus-k8s":
                    endpoint = f"https://{item['spec']['host']}"
                    break

            if endpoint is None:
                logging.error(
                    f"prometheus Route not found in cluster, "
                    f"namespace{prometheus_namespace}, "
                    f"Route: {prometheus_route}"
                )
                return None

            return named_tuple(token=token, endpoint=endpoint)
        except Exception:
            logging.error(
                f"failed to fetch prometheus route"
                f"namespace{prometheus_namespace}, "
                f"Route: {prometheus_route}"
            )
            return None

    def is_openshift(self) -> bool:
        """
        Checks if is an openshift cluster
        :return: true if it's openshift, false if not
        """
        value = self._get_clusterversion_string()
        return value is not None and value != ""
