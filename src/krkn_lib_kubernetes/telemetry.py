import base64
import logging
import sys
import threading
import yaml
import requests
import os
from queue import Queue
from base64io import Base64IO
from requests.adapters import HTTPAdapter
from urllib3 import Retry

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
                logging.warning(
                    f"failed to send telemetry "
                    f"with error: {request.status_code}"
                )
            else:
                logging.info("successfully sent telemetry data")

    def get_ocp_prometheus_data(
        self,
        kubecli: KrknLibKubernetes,
        telemetry_config: dict,
        request_id: str,
    ) -> list[(int, str)]:
        """
        Downloads the OCP prometheus metrics folder
        :param kubecli: KrknLibKubernetes client object
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
        if is_exception:
            raise Exception(", ".join(exceptions))

        if not prometheus_backup:
            return file_list

        prometheus_pod_name = "prometheus-k8s-0"
        prometheus_container_name = "prometheus"
        prometheus_namespace = "openshift-monitoring"
        remote_archive_path = "/prometheus"
        prometheus_pod = kubecli.get_pod_info(
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
            file_list = kubecli.archive_and_get_path_from_pod(
                prometheus_pod_name,
                prometheus_container_name,
                prometheus_namespace,
                remote_archive_path,
                target_path,
                request_id,
                archive_path,
                max_threads=int(backup_threads),
                archive_part_size=10000,
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
            logging.error(exception_string)
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
        :return:
        """
        queue = Queue()
        prometheus_backup = telemetry_config.get("prometheus_backup")
        url = telemetry_config.get("api_url")
        username = telemetry_config.get("username")
        password = telemetry_config.get("password")
        backup_threads = telemetry_config.get("backup_threads")
        exceptions = []
        is_exception = False
        if prometheus_backup is None:
            exceptions.append("telemetry -> prometheus_backup flag is missing")
            is_exception = True
        if backup_threads is None:
            exceptions.append("telemetry -> backup_threads is missing")
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
        if is_exception:
            raise Exception(", ".join(exceptions))

        if not prometheus_backup:
            return

        try:
            total_size = 0
            for i, item in enumerate(archive_volumes):
                decoded_filename = item[1].replace(".b64", "")
                if item[1] == decoded_filename:
                    raise Exception(
                        "impossible to convert base64 file, "
                        "source and destination file are the same"
                    )
                self.decode_base64_file(item[1], decoded_filename)
                queue.put((i, decoded_filename))
                total_size += os.stat(decoded_filename).st_size / (1024 * 1024)
                os.unlink(item[1])
            uploaded_files = list[str]()
            for i in range(int(backup_threads)):
                worker = threading.Thread(
                    target=self.generate_url_and_put_to_s3_worker,
                    args=(
                        queue,
                        request_id,
                        f"{url}/presigned-url",
                        username,
                        password,
                        i,
                        uploaded_files,
                    ),
                )
                worker.daemon = True
                worker.start()
            queue.join()

        except Exception as e:
            logging.error(str(e))

    def generate_url_and_put_to_s3_worker(
        self,
        queue: Queue,
        request_id: str,
        api_url: str,
        username: str,
        password: str,
        thread_number: int,
        uploaded_file_list: list[str],
    ):
        """
        Worker function that creates an s3 link to put files and upload
        and uploads the file on the bucket.
        :param queue: queue that will be consumed. The queue
        elements must be tuples on which the first item must
        be the file sequence number and the second a local filename full-path
        that will be uploaded in the S3 bucket
        :param request_id: uuid of the session that will represent the
        S3 folder on which the prometheus files will be stored
        :param api_url: API endpoint to generate the S3 temporary link
        :param username: API username
        :param password: API password
        :param thread_number: Thread number
        :return:
        """
        while not queue.empty():
            try:
                data_tuple = queue.get()
                file_number = data_tuple[0]
                local_filename = data_tuple[1]

                s3_url = self.get_bucket_url_for_filename(
                    api_url,
                    request_id,
                    f"prometheus-{file_number:02d}.tar",
                    username,
                    password,
                )

                self.put_file_to_url(s3_url, local_filename)
                uploaded_file_list.append(local_filename)

                logging.info(
                    f"[Thread #{thread_number}]: uploaded file "
                    f"{len(uploaded_file_list)}/{queue.unfinished_tasks} "
                    f"on {request_id}/"
                )
            except Exception as e:
                logging.error(
                    f"[Thread #{thread_number}] failed to upload "
                    f"file {local_filename} with exception: {str(e)}"
                )
                raise e
            finally:
                os.unlink(local_filename)
                queue.task_done()

    def put_file_to_url(self, url: str, local_filename: str):
        """
        Puts a local file on an url
        :param url: url where the file will be put
        :param local_filename: local file full-path
        :return:
        """
        try:
            with open(local_filename, "rb") as file:
                session = requests.Session()
                retry = Retry(connect=30, backoff_factor=0.2)
                adapter = HTTPAdapter(max_retries=retry)
                session.mount("http://", adapter)
                session.mount("https://", adapter)

                upload_to_s3_response = session.put(
                    url,
                    data=file,
                )
                if upload_to_s3_response.status_code != 200:
                    raise Exception(
                        f"failed to send archive to s3 with "
                        f"status code: "
                        f"{str(upload_to_s3_response.status_code)}"
                    )
                session.close()

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
        prometheus data,
        :param api_url: telemetry base URL
        :param bucket_folder: folder on which the prometheus archives
        will be stored
        :param remote_filename: name of the file
        that will be stored in the bucket
        :param username: API username
        :param password: API password
        :return:
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

    def decode_base64_file(
        self, source_filename: str, destination_filename: str
    ):
        """
        Decodes a base64 file while it's read (no memory allocation).
        Suitable for big file conversion.
        :param source_filename: source base64 encoded file
        :param destination_filename: destination decoded file
        :return:
        """
        with open(source_filename, "rb") as encoded_source, open(
            destination_filename, "wb"
        ) as target:
            with Base64IO(encoded_source) as source:
                for line in source:
                    target.write(line)
