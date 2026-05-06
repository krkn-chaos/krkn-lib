import concurrent.futures
import datetime
import logging
import os
import threading
import time
from queue import Queue
from typing import Optional

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
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        prometheus_url: Optional[str] = None,
        prometheus_bearer_token: Optional[str] = None,
    ) -> list[(int, str)]:
        """
        Downloads the Openshift prometheus metrics.
        Attempts API-based collection first (if parameters provided),
        then falls back to filesystem backup.

        :param telemetry_config: krkn telemetry conf section
            will be stored
        :param request_id: uuid of the session that will represent the
            temporary archive files
        :param start_timestamp: (Optional) Start time for API-based collection
            (Unix timestamp in seconds)
        :param end_timestamp: (Optional) End time for API-based collection
            (Unix timestamp in seconds)
        :param prometheus_url: (Optional) Prometheus API URL for API-based
            collection
        :param prometheus_bearer_token: (Optional) Bearer token for
            Prometheus API authentication
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
            "/prometheus",
            start_timestamp,
            end_timestamp,
            prometheus_url,
            prometheus_bearer_token,
        )

    def collect_cluster_metadata(self, chaos_telemetry: ChaosRunTelemetry):
        t0 = time.monotonic()
        super().collect_cluster_metadata(chaos_telemetry)
        self.safe_logger.info(
            f"collect_cluster_metadata: base metadata collected in "
            f"{time.monotonic() - t0:.2f}s"
        )

        TIMEOUT = 30  # seconds wall-clock for all OCP calls combined

        def timed(name, fn):
            t = time.monotonic()
            try:
                result = fn()
                self.safe_logger.info(
                    f"collect_cluster_metadata: {name} in "
                    f"{time.monotonic() - t:.2f}s"
                )
                return result
            except Exception as e:
                self.safe_logger.warning(
                    f"collect_cluster_metadata: {name} failed after "
                    f"{time.monotonic() - t:.2f}s: {e}"
                )
                raise

        ocp = self.__ocpcli
        calls = {
            "get_cloud_infrastructure": ocp.get_cloud_infrastructure,
            "get_cluster_type": ocp.get_cluster_type,
            "get_clusterversion_string": ocp.get_clusterversion_string,
            "get_cluster_network_plugins": ocp.get_cluster_network_plugins,
            "get_vm_number": self.get_vm_number,
            "get_build_count": self.get_build_count,
            "get_route_count": self.get_route_count,
        }

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=len(calls)
        )
        futures = {
            name: executor.submit(timed, name, fn)
            for name, fn in calls.items()
        }
        done, _ = concurrent.futures.wait(futures.values(), timeout=TIMEOUT)
        executor.shutdown(wait=False)

        for name, future in futures.items():
            if future not in done:
                self.safe_logger.warning(
                    f"collect_cluster_metadata: {name} timed out after "
                    f"{TIMEOUT}s, skipping"
                )

        def get_result(name):
            f = futures[name]
            if f not in done:
                return None
            try:
                return f.result()
            except Exception:
                return None

        chaos_telemetry.cloud_infrastructure = get_result(
            "get_cloud_infrastructure"
        )
        chaos_telemetry.cloud_type = get_result("get_cluster_type")
        cluster_version = get_result("get_clusterversion_string")
        if cluster_version:
            chaos_telemetry.cluster_version = cluster_version
            chaos_telemetry.major_version = cluster_version[:4]
        chaos_telemetry.network_plugins = (
            get_result("get_cluster_network_plugins") or []
        )
        vm_number = get_result("get_vm_number") or 0
        if vm_number > 0:
            chaos_telemetry.kubernetes_objects_count[
                "VirtualMachineInstance"
            ] = vm_number
        build_count = get_result("get_build_count") or 0
        chaos_telemetry.kubernetes_objects_count["Build"] = build_count
        route_count = get_result("get_route_count") or 0
        chaos_telemetry.kubernetes_objects_count["Route"] = route_count

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

    def _count_custom_objects(
        self, group: str, version: str, plural: str
    ) -> int:
        count = 0
        continue_token = None
        client = self.__ocpcli.custom_object_client
        while True:
            kwargs = {"limit": 500}
            if continue_token:
                kwargs["_continue"] = continue_token
            result = client.list_cluster_custom_object(
                group=group,
                version=version,
                plural=plural,
                **kwargs,
            )
            count += len(result["items"])
            continue_token = result.get("metadata", {}).get("continue")
            if not continue_token:
                break
        return count

    def get_vm_number(self) -> int:
        try:
            return self._count_custom_objects(
                "kubevirt.io", "v1", "virtualmachineinstances"
            )
        except Exception as e:
            logging.info(f"failed to get virtualmachines: {e}")
            return 0

    def get_build_count(self) -> int:
        try:
            return self._count_custom_objects(
                "build.openshift.io", "v1", "builds"
            )
        except Exception as e:
            logging.info(f"failed to get builds: {e}")
            return 0

    def get_route_count(self) -> int:
        try:
            return self._count_custom_objects(
                "route.openshift.io", "v1", "routes"
            )
        except Exception as e:
            logging.info(f"failed to get routes: {e}")
            return 0
