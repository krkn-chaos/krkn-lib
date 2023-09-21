import base64
import os
import datetime
import threading
import time
from queue import Queue
from typing import Optional

import requests
import yaml

import krkn_lib.utils as utils
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ChaosRunTelemetry, ScenarioTelemetry
from krkn_lib.utils.safe_logger import SafeLogger


class KrknTelemetry:
    kubecli: KrknKubernetes = None
    safe_logger: SafeLogger = None

    def __init__(
        self, safe_logger: SafeLogger, lib_kubernetes: KrknKubernetes
    ):
        self.kubecli = lib_kubernetes
        self.safe_logger = safe_logger

    def collect_cluster_metadata(self, chaos_telemetry: ChaosRunTelemetry):
        """
        Collects useful cluster metadata:
        - cloud infrastructure
        - network plugins
        - number of objects deployed
        - node system infos
        to enrich the ChaosRunTelemetry object that will be sent to the
        telemetry service:

        :param chaos_telemetry: the chaos telemetry to be enriched by
            the cluster metadata
        """
        self.safe_logger.info("collecting telemetry data, please wait....")
        chaos_telemetry.cloud_infrastructure = (
            self.kubecli.get_cluster_infrastructure()
        )
        chaos_telemetry.network_plugins = (
            self.kubecli.get_cluster_network_plugins()
        )
        chaos_telemetry.kubernetes_objects_count = (
            self.kubecli.get_all_kubernetes_object_count(
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
        chaos_telemetry.node_infos = self.kubecli.get_nodes_infos()
        chaos_telemetry.node_count = len(chaos_telemetry.node_infos)

    def send_telemetry(
        self,
        telemetry_config: dict,
        uuid: str,
        chaos_telemetry: ChaosRunTelemetry,
    ) -> Optional[str]:
        """
        Sends Telemetry Data to the Telemetry Web Service

        :param telemetry_config: krkn telemetry conf section
        :param uuid: uuid used as folder in S3 bucket
        :param chaos_telemetry: already populated ChaosRunTelemetry object
        :return: the telemetry object json string
        """
        enabled = telemetry_config.get("enabled")
        if enabled:
            url = telemetry_config.get("api_url")
            username = telemetry_config.get("username")
            password = telemetry_config.get("password")
            exceptions = []
            is_exception = False
            if url is None:
                exceptions.append("telemetry -> api_url is missing")
                is_exception = True
            if username is None:
                exceptions.append("telemetry -> username is missing")
                is_exception = True
            if password is None:
                exceptions.append("telemetry -> password is missing")
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
                url=f"{url}/telemetry",
                auth=(username, password),
                data=json_data,
                params={"request_id": uuid},
                headers=headers,
            )

            if request.status_code != 200:
                error_message = (
                    f"failed to send telemetry to {url}/telemetry"
                    f"with error: {request.status_code} - "
                    f"{str(request.content)}"
                )
                self.safe_logger.warning(error_message)
                raise Exception(error_message)
            else:
                self.safe_logger.info("successfully sent telemetry data")
                return json_data

    def get_ocp_prometheus_data(
        self,
        telemetry_config: dict,
        request_id: str,
    ) -> list[(int, str)]:
        """
        Downloads the OCP prometheus metrics folder

        :param telemetry_config: krkn telemetry conf section
            will be stored
        :param request_id: uuid of the session that will represent the
            temporary archive files
        :return: the list of the archive number and filenames downloaded
        """
        file_list = list[(int, str)]()

        prometheus_backup = telemetry_config.get("prometheus_backup")
        full_prometheus_backup = telemetry_config.get("full_prometheus_backup")
        url = telemetry_config.get("api_url")
        username = telemetry_config.get("username")
        password = telemetry_config.get("password")
        backup_threads = telemetry_config.get("backup_threads")
        archive_path = telemetry_config.get("archive_path")
        archive_size = telemetry_config.get("archive_size")
        exceptions = []
        is_exception = False
        if prometheus_backup is None:
            exceptions.append("telemetry -> prometheus_backup flag is missing")
            is_exception = True
        if full_prometheus_backup is None:
            exceptions.append(
                "telemetry -> full_prometheus_backup flag is missing"
            )
            is_exception = True
        if backup_threads is None:
            exceptions.append("telemetry -> backup_threads is missing")
            is_exception = True
        if not isinstance(backup_threads, int):
            exceptions.append(
                "telemetry -> backup_threads must be a number" "not a string"
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
        if archive_path is None:
            exceptions.append("telemetry -> archive_path is missing")
            is_exception = True
        if archive_size is None:
            exceptions.append("telemetry -> archive_size is missing")
            is_exception = True
        if is_exception:
            raise Exception(", ".join(exceptions))

        if not prometheus_backup:
            return file_list

        prometheus_pod_name = "prometheus-k8s-0"
        prometheus_container_name = "prometheus"
        prometheus_namespace = "openshift-monitoring"
        remote_archive_path = "/prometheus"
        prometheus_pod = self.kubecli.get_pod_info(
            prometheus_pod_name, prometheus_namespace
        )
        if not prometheus_pod:
            raise Exception(
                f"prometheus pod: {prometheus_pod_name}, "
                f"container: {prometheus_container_name} "
                f"namespace: {prometheus_namespace}, "
                f"not found"
            )

        # if full_prometheus_backup is false backup only wals
        target_path = "/prometheus"
        if not full_prometheus_backup:
            target_path = "/prometheus/wal"

        try:
            file_list = self.kubecli.archive_and_get_path_from_pod(
                prometheus_pod_name,
                prometheus_container_name,
                prometheus_namespace,
                remote_archive_path,
                target_path,
                request_id,
                archive_path,
                max_threads=backup_threads,
                archive_part_size=archive_size,
                safe_logger=self.safe_logger,
            )
            return file_list
        except Exception as e:
            exception_string = (
                f"failed to download prometheus backup"
                f" on pod: {prometheus_pod_name},"
                f" container: {prometheus_container_name},"
                f" namespace: {prometheus_namespace}:"
                f" {str(e)}"
            )
            self.safe_logger.error(exception_string)
            raise Exception(exception_string)

    def put_ocp_prometheus_data(
        self,
        telemetry_config: dict,
        archive_volumes: list[(int, str)],
        request_id: str,
    ):
        """
        Puts a list of files on telemetry S3 bucket, mulithread.

        :param telemetry_config: telemetry section of kraken config.yaml
        :param archive_volumes: a list of tuples containing the
            archive number, and the archive full path to be uploaded
        :param request_id: uuid of the session that will represent the
            S3 folder on which the prometheus files will be stored
        """
        queue = Queue()
        prometheus_backup = telemetry_config.get("prometheus_backup")
        url = telemetry_config.get("api_url")
        username = telemetry_config.get("username")
        password = telemetry_config.get("password")
        backup_threads = telemetry_config.get("backup_threads")
        max_retries = telemetry_config.get("max_retries")
        exceptions = []
        is_exception = False
        if prometheus_backup is None:
            exceptions.append("telemetry -> prometheus_backup flag is missing")
            is_exception = True
        if backup_threads is None:
            exceptions.append("telemetry -> backup_threads is missing")
            is_exception = True
        if not isinstance(backup_threads, int):
            exceptions.append(
                "telemetry -> backup_threads must be a number" "not a string"
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
        if is_exception:
            raise Exception(", ".join(exceptions))

        if not prometheus_backup:
            return

        try:
            total_size = 0
            for item in archive_volumes:
                decoded_filename = item[1].replace(".b64", "")
                volume_number = item[0]
                if item[1] == decoded_filename:
                    raise Exception(
                        "impossible to convert base64 file, "
                        "source and destination file are the same"
                    )
                utils.decode_base64_file(item[1], decoded_filename)
                queue.put((volume_number, decoded_filename, 0))
                total_size += os.stat(decoded_filename).st_size / (1024 * 1024)
                os.unlink(item[1])
            uploaded_files = list[str]()
            queue_size = queue.qsize()
            for i in range(backup_threads):
                worker = threading.Thread(
                    target=self.generate_url_and_put_to_s3_worker,
                    args=(
                        queue,
                        queue_size,
                        request_id,
                        f"{url}/presigned-url",
                        username,
                        password,
                        i,
                        uploaded_files,
                        max_retries,
                        "prometheus-",
                        ".tar",
                    ),
                )
                worker.daemon = True
                worker.start()
            queue.join()

        except Exception as e:
            self.safe_logger.error(str(e))

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
            return

        try:
            timestamp = datetime.datetime.now().timestamp()
            workdir = os.path.join(archive_path, f"gathered-logs-{timestamp}")
            dst_dir = os.path.join(archive_path, f"filtered-logs-{timestamp}")
            os.mkdir(workdir)
            os.mkdir(dst_dir)
            archive_path = self.kubecli.collect_filter_archive_ocp_logs(
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

    def generate_url_and_put_to_s3_worker(
        self,
        queue: Queue,
        queue_size: int,
        request_id: str,
        api_url: str,
        username: str,
        password: str,
        thread_number: int,
        uploaded_file_list: list[str],
        max_retries: int,
        remote_file_prefix: str,
        remote_file_extension: str,
    ):
        """
        Worker function that creates an s3 link to put files and upload
        the file directly on the bucket.

        :param queue: queue that will be consumed. The queue
            elements must be tuples on which the first item must
            be the file sequence number, the second a local filename full-path
            that will be uploaded in the S3 bucket and the
            third will be a retry counter updated by the thread
            on upload exception and compared with max_retries.
        :param queue_size: total number of files
        :param request_id: uuid of the session that will represent the
            S3 folder on which the prometheus files will be stored
        :param api_url: API endpoint to generate the S3 temporary link
        :param username: API username
        :param password: API password
        :param thread_number: Thread number
        :param uploaded_file_list: uploaded file list shared between threads
        :param max_retries: maximum number of retries from config.yaml.
            If 0 will retry indefinitely.
        :param remote_file_prefix: the prefix that will given to the file
            in the S3 bucket along with the progressive number
            (if is a multiple file archive)
        :param remote_file_extension: the extension of the remote
            file on the S3 bucket
        :return:
        """
        THREAD_SLEEP = 5  # NOQA
        while not queue.empty():
            data_tuple = queue.get()
            file_number = data_tuple[0]
            local_filename = data_tuple[1]
            retry = data_tuple[2]
            try:
                s3_url = self.get_bucket_url_for_filename(
                    api_url,
                    request_id,
                    f"{remote_file_prefix}"
                    f"{file_number:02d}"
                    f"{remote_file_extension}",
                    username,
                    password,
                )

                self.put_file_to_url(s3_url, local_filename)
                uploaded_file_list.append(local_filename)

                self.safe_logger.info(
                    f"[Thread #{thread_number}] : "
                    f"{queue.unfinished_tasks - 1}/"
                    f"{queue_size} "
                    f"{local_filename} uploaded "
                )
                os.unlink(local_filename)
            except Exception as e:
                if max_retries == 0 or retry < max_retries:
                    self.safe_logger.warning(
                        f"[Thread #{thread_number}] "
                        f"{local_filename} "
                        f"retry number {retry}"
                    )
                    time.sleep(THREAD_SLEEP)
                    # if there's an exception on the file upload
                    # the file will be re-enqueued to be retried in 5 seconds
                    queue.put((file_number, local_filename, retry + 1))
                else:
                    self.safe_logger.error(
                        f"[Thread #{thread_number}] "
                        f"max retry number exceeded, "
                        f"failed to upload file {local_filename} "
                        f"with exception: {str(e)}"
                    )
                    raise e
            finally:
                queue.task_done()

    def put_file_to_url(self, url: str, local_filename: str):
        """
        Puts a local file on an url
        :param url: url where the file will be put
        :param local_filename: local file full-path
        """
        try:
            with open(local_filename, "rb") as file:
                upload_to_s3_response = requests.put(url, data=file, timeout=5)
                if upload_to_s3_response.status_code != 200:
                    raise Exception(
                        f"failed to send archive to s3 with "
                        f"status code: "
                        f"{str(upload_to_s3_response.status_code)}"
                    )
        except Exception as e:
            raise e

    def get_bucket_url_for_filename(
        self,
        api_url: str,
        bucket_folder: str,
        remote_filename: str,
        username: str,
        password: str,
    ) -> str:
        """
        Gets from the telemetry API a one shot S3 link to upload
        prometheus data

        :param api_url: telemetry base URL
        :param bucket_folder: folder on which the prometheus archives
            will be stored
        :param remote_filename: name of the file
            that will be stored in the bucket
        :param username: API username
        :param password: API password
        :return: the url where the file will be uploaded
        """
        url_params = {
            "request_id": bucket_folder,
            "remote_filename": remote_filename,
        }
        presigned_url_response = requests.get(
            api_url,
            auth=(username, password),
            params=url_params,
        )
        if presigned_url_response.status_code != 200:
            raise Exception(
                f"impossible to get upload url from "
                f"api with code: {presigned_url_response.status_code}"
            )
        return presigned_url_response.content.decode("utf-8")

    def set_parameters_base64(
        self, scenario_telemetry: ScenarioTelemetry, file_path: str
    ):
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
            utils.deep_set_attribute(
                "kubeconfig", "anonymized", input_file_yaml
            )
            input_file_data = yaml.safe_dump(input_file_yaml)
            input_file_base64 = base64.b64encode(
                input_file_data.encode()
            ).decode()
        except Exception as e:
            raise Exception("telemetry: {0}".format(str(e)))
        scenario_telemetry.parametersBase64 = input_file_base64
