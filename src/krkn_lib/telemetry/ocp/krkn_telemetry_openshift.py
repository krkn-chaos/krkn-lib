import datetime
import os
import threading
from queue import Queue

from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.utils import SafeLogger


class KrknTelemetryOpenshift(KrknTelemetryKubernetes):
    ocpcli: KrknOpenshift

    def __init__(self, safe_logger: SafeLogger, lib_openshift: KrknOpenshift):
        super().__init__(safe_logger=safe_logger, lib_kubernetes=lib_openshift)
        self.ocpcli = lib_openshift

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
            self.ocpcli.get_cloud_infrastructure()
        )
        chaos_telemetry.network_plugins = (
            self.ocpcli.get_cluster_network_plugins()
        )

    def put_ocp_logs(
        self,
        request_id: str,
        telemetry_config: dict,
        start_timestamp: int,
        end_timestamp: int,
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
            archive_path = self.ocpcli.collect_filter_archive_ocp_logs(
                workdir,
                dst_dir,
                self.kubecli.get_kubeconfig_path(),
                start_timestamp,
                end_timestamp,
                logs_filter_patterns,
                backup_threads,
                self.safe_logger,
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
        worker = threading.Thread(
            target=self.generate_url_and_put_to_s3_worker,
            args=(
                queue,
                queue_size,
                request_id,
                f"{url}/presigned-url",
                username,
                password,
                0,
                uploaded_files,
                max_retries,
                "logs-",
                ".tar.gz",
            ),
        )
        worker.daemon = True
        worker.start()
        queue.join()
        self.safe_logger.info("ocp logs successfully uploaded")
