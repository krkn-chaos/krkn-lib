import ast
import datetime
import logging
import os
import threading
from queue import Queue

from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.utils import SafeLogger


class KrknTelemetryOpenshift(KrknTelemetryKubernetes):
    __ocpcli: KrknOpenshift
    __telemetry_id: str = None

    def __init__(
        self,
        safe_logger: SafeLogger,
        lib_openshift: KrknOpenshift,
        telemetry_request_id: str = "",
        krkn_telemetry_config: dict[str, any] = None,
    ):
        super().__init__(
            safe_logger=safe_logger,
            lib_kubernetes=lib_openshift,
            krkn_telemetry_config=krkn_telemetry_config,
            telemetry_request_id=telemetry_request_id,
        )
        self.__ocpcli = lib_openshift

    def get_lib_ocp(self) -> KrknOpenshift:
        """
        Returns the instance of KrknOpenshift

        :return: a KrknOpenshift instance
        """
        return self.__ocpcli

    def get_ocp_prometheus_data(
        self,
        telemetry_config: dict,
        request_id: str,
    ) -> list[(int, str)]:
        """
        Downloads the Openshift prometheus metrics

        :param telemetry_config: krkn telemetry conf section
            will be stored
        :param request_id: uuid of the session that will represent the
            temporary archive files
        :return: the list of the archive number and filenames downloaded
        """
        prometheus_ocp_pod_name = "prometheus-k8s-0"
        prometheus_ocp_container_name = "prometheus"
        prometheus_ocp_namespace = "openshift-monitoring"

        return self.get_prometheus_pod_data(
            telemetry_config,
            request_id,
            prometheus_ocp_pod_name,
            prometheus_ocp_container_name,
            prometheus_ocp_namespace,
        )

    def collect_cluster_metadata(self, chaos_telemetry: ChaosRunTelemetry):
        super().collect_cluster_metadata(chaos_telemetry)
        chaos_telemetry.cloud_infrastructure = (
            self.__ocpcli.get_cloud_infrastructure()
        )
        chaos_telemetry.cloud_type = self.__ocpcli.get_cluster_type()
        chaos_telemetry.cluster_version = (
            self.__ocpcli.get_clusterversion_string()
        )
        chaos_telemetry.major_version = chaos_telemetry.cluster_version[:4]

        chaos_telemetry.network_plugins = (
            self.__ocpcli.get_cluster_network_plugins()
        )

        vm_number = self.get_vm_number()
        if vm_number > 0:
            chaos_telemetry.kubernetes_objects_count[
                "VirtualMachineInstance"
            ] = vm_number

    def put_ocp_logs(
        self,
        request_id: str,
        telemetry_config: dict,
        start_timestamp: int,
        end_timestamp: int,
        namespace: str = None,
    ):
        """
        Collects, filters, archive and put on the telemetry S3 Buckets
        Openshift logs. Built on top of the `oc adm must-gather` command
        and custom filtering.

        :param request_id: uuid of the session that will represent the
            S3 folder on which the filtered log files archive will be stored
        :param telemetry_config: telemetry section of kraken config.yaml
        :param start_timestamp: timestamp of the first relevant entry, if None
            will start filter starting from the earliest
        :param end_timestamp: timestamp of the last relevant entry, if None
            will end filtering until the latest
        :param namespace: if set the logs will be collected
            only for the provided namespace
        """

        queue = Queue()
        logs_backup = telemetry_config.get("logs_backup")
        url = telemetry_config.get("api_url")
        username = telemetry_config.get("username")
        password = telemetry_config.get("password")
        backup_threads = telemetry_config.get("backup_threads")
        max_retries = telemetry_config.get("max_retries")
        archive_path = telemetry_config.get("archive_path")
        logs_filter_patterns = telemetry_config.get("logs_filter_patterns")
        oc_cli_path = telemetry_config.get("oc_cli_path")
        group = telemetry_config.get("telemetry_group")
        exceptions = []
        is_exception = False
        if logs_backup is None:
            exceptions.append("telemetry -> logs_backup flag is missing")
            is_exception = True
        if backup_threads is None:
            exceptions.append("telemetry -> backup_threads is missing")
            is_exception = True

        if not isinstance(backup_threads, int):
            exceptions.append(
                "telemetry -> backup_threads must be a number not a string"
            )
            is_exception = True
        if url is None:
            exceptions.append("telemetry -> api_url is missing")
            is_exception = True
        if username is None:
            exceptions.append("telemetry -> username is missing")
            is_exception = True
        if password is None:
            exceptions.append("telemetry -> password is missing")
            is_exception = True
        if max_retries is None:
            exceptions.append("telemetry -> max_retries is missing")
            is_exception = True
        if archive_path is None:
            exceptions.append("telemetry -> archive_path is missing")
            is_exception = True
        if logs_filter_patterns is None:
            exceptions.append("telemetry -> logs_filter_pastterns is missing")
            is_exception = True
        if not group:
            group = self.default_telemetry_group

        # if oc_cli_path is set to empty will be set to
        # None to let the config flexible
        if oc_cli_path == "":
            oc_cli_path = None

        if not isinstance(logs_filter_patterns, list):
            exceptions.append(
                "telemetry -> logs_filter_pastterns must be a "
                "list of regex pattern"
            )
            is_exception = True

        if is_exception:
            raise Exception(", ".join(exceptions))

        if not logs_backup:
            self.safe_logger.info(
                "logs_backup is False: skipping OCP logs collection"
            )
            return

        try:
            timestamp = datetime.datetime.now().timestamp()
            workdir = os.path.join(archive_path, f"gathered-logs-{timestamp}")
            dst_dir = os.path.join(archive_path, f"filtered-logs-{timestamp}")
            os.mkdir(workdir)
            os.mkdir(dst_dir)
            archive_path = self.__ocpcli.collect_filter_archive_ocp_logs(
                workdir,
                dst_dir,
                self.__ocpcli.get_kubeconfig_path(),
                start_timestamp,
                end_timestamp,
                logs_filter_patterns,
                backup_threads,
                self.safe_logger,
                namespace,
                oc_cli_path,
            )
            # volume_number : 0 only one file
            # archive_path: path of the archived logs
            # retries: 0
            queue.put((0, archive_path, 0))
        except Exception as e:
            self.safe_logger.error(f"failed to collect ocp logs: {str(e)}")
            raise e
        # this parameter has doesn't have an utility in this context
        # used to match the method signature and reuse it (Poor design?)
        uploaded_files = list[str]()
        queue_size = queue.qsize()
        self.safe_logger.info("uploading ocp logs...")
        logs_filename_prefix = (
            "logs-" if namespace is None else f"logs-{namespace}-"
        )
        worker = threading.Thread(
            target=self.generate_url_and_put_to_s3_worker,
            args=(
                queue,
                queue_size,
                request_id,
                group,
                f"{url}/presigned-url",
                username,
                password,
                0,
                uploaded_files,
                max_retries,
                logs_filename_prefix,
                ".tar.gz",
            ),
        )
        worker.daemon = True
        worker.start()
        queue.join()
        self.safe_logger.info("ocp logs successfully uploaded")

    def get_vm_number(self) -> int:
        api_client = self.__ocpcli.api_client
        if api_client:
            try:
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/kubevirt.io/v1/virtualmachineinstances"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                if data[1] != 200:
                    return 0

                json_obj = ast.literal_eval(data[0])
                return len(json_obj["items"])
            except Exception:
                logging.info("failed to parse virtualmachines API")
                return 0
        return 0
