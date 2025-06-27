import cProfile
import logging
import os
import queue
import random
import string
import sys
import tempfile
import threading
import time
import unittest
from typing import Dict, List

import requests
import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes import config
from kubernetes.client.rest import ApiException
from requests import ConnectTimeout

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import SafeLogger


class BaseTest(unittest.TestCase):
    lib_k8s: KrknKubernetes
    lib_ocp: KrknOpenshift
    lib_telemetry_k8s: KrknTelemetryKubernetes
    lib_telemetry_ocp: KrknTelemetryOpenshift
    lib_elastic: KrknElastic
    pr: cProfile.Profile
    pod_delete_queue: queue.Queue

    @classmethod
    def setUpClass(cls):
        cls.lib_elastic = KrknElastic(
            SafeLogger(),
            os.getenv("ELASTIC_URL"),
            int(os.getenv("ELASTIC_PORT")),
            username=os.getenv("ELASTIC_USER"),
            password=os.getenv("ELASTIC_PASSWORD"),
        )
        cls.lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)
        cls.lib_ocp = KrknOpenshift(config.KUBE_CONFIG_DEFAULT_LOCATION)
        cls.lib_telemetry_k8s = KrknTelemetryKubernetes(
            SafeLogger(), cls.lib_k8s
        )
        cls.lib_telemetry_ocp = KrknTelemetryOpenshift(
            SafeLogger(), cls.lib_ocp
        )
        host = cls.lib_k8s.get_host()
        logging.disable(logging.CRITICAL)
        # PROFILER
        # """init each test"""
        # cls.pr = cProfile.Profile()
        # cls.pr.enable()
        # print("\n<<<---")

        # starting pod_delete_queue
        cls.pod_delete_queue = queue.Queue()
        worker = threading.Thread(target=cls.pod_delete_worker, args=[cls])

        worker.daemon = True
        worker.start()

        try:
            requests.get(host, timeout=2, verify=False)
        except ConnectTimeout:
            logging.error(
                "Unable to connect to Kubernetes API %s.\n"
                "To run the tests please setup a running k8s cluster.\n"
                "To have a local working k8s cluster "
                "visit https://minikube.sigs.k8s.io/docs/\n",
                host,
            )
            sys.exit(1)

    def pod_delete_worker(self):
        while True:
            pod_namespace = self.pod_delete_queue.get()
            if pod_namespace[0] == "exit" and pod_namespace == "exit":
                print("pod killing thread exiting....")
                return
            try:
                self.lib_k8s.delete_pod(pod_namespace[0], pod_namespace[1])
                self.lib_k8s.delete_namespace(pod_namespace[1])
                logging.info(
                    f"[POD DELETE WORKER] deleted pod: "
                    f"{pod_namespace[0]} namespace:{pod_namespace[1]}"
                )
                self.pod_delete_queue.task_done()
            except Exception as e:
                logging.error(
                    f"[POD DELETE WORKER] "
                    f"exception raised but continuing:  {e}"
                )
                continue

    @classmethod
    def tearDownClass(cls) -> None:
        # PROFILER
        # """finish any test"""
        # p = Stats(cls.pr)
        # p.strip_dirs()
        # p.sort_stats("cumtime")
        # p.print_stats()
        # print
        # "\n--->>>"
        cls.pod_delete_queue.put(["exit", "exit"])
        pass

    def wait_delete_namespace(
        self, namespace: str = "default", timeout: int = 60
    ):
        runtime = 0
        while True:
            if runtime >= timeout:
                raise Exception(
                    "timeout on waiting on namespace {0} deletion".format(
                        namespace
                    )
                )
            namespaces = self.lib_k8s.list_namespaces()

            if namespace in namespaces:
                logging.info("namespace %s is now deleted" % namespace)
                return
            time.sleep(2)
            runtime = runtime + 2

    def wait_pod(
        self, name: str, namespace: str = "default", timeout: int = 60
    ):
        runtime = 0
        while True:
            if runtime >= timeout:
                raise Exception(
                    "timeout on waiting {0} pod on namespace {1}".format(
                        name, namespace
                    )
                )
            result = self.lib_k8s.read_pod(name, namespace)
            if result.status.phase == "Running":
                logging.info("pod %s is now running" % name)
                return
            time.sleep(2)
            runtime = runtime + 2

    def deploy_namespace(self, name: str, labels: List[Dict[str, str]]):
        template = self.template_to_namespace(name, labels)
        self.apply_template(template)

    def deploy_fedtools(
        self,
        namespace: str = "default",
        random_label: str = None,
        name: str = "fedtools",
    ):
        template = self.template_to_pod(name, namespace, random_label)
        self.apply_template(template)

    def deploy_fake_kraken(
        self,
        namespace: str = "default",
        random_label: str = None,
        node_name: str = None,
    ):
        template = self.template_to_pod(
            "kraken-deployment", namespace, random_label, node_name
        )
        self.apply_template(template)

    def deploy_job(self, name: str, namespace: str = "default"):
        template = self.template_to_job(name, namespace)
        self.apply_template(template)

    def depoy_alpine(self, name: str, namespace: str = "default"):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("alpine.j2")
        content = template.render(name=name, namespace=namespace)
        self.apply_template(content)

    def deploy_nginx(
        self,
        namespace: str,
        pod_name: str = "nginx",
        service_name: str = "nginx",
    ):
        env = Environment(loader=FileSystemLoader("src/testdata/"))
        pod_template = env.get_template("nginx-test-pod.j2")
        pod_body = yaml.safe_load(
            pod_template.render(
                pod_name=pod_name,
                service_name=service_name,
                namespace=namespace,
            )
        )
        service_template = env.get_template("nginx-test-service.j2")
        service_body = yaml.safe_load(
            service_template.render(
                service_name=service_name,
                namespace=namespace,
            )
        )
        self.lib_k8s.create_pod(namespace=namespace, body=pod_body)
        self.lib_k8s.cli.create_namespaced_service(
            body=service_body, namespace=namespace
        )

    def deploy_delayed_readiness_pod(
        self, name: str, namespace: str, delay: int, label: str = "readiness"
    ):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("delayed_readiness_pod.j2")
        content = template.render(
            name=name, namespace=namespace, delay=delay, label=label
        )
        self.apply_template(content)

    def deploy_persistent_volume(
        self, name: str, storage_class: str, namespace: str
    ):
        template = self.template_to_pv(name, storage_class, namespace)
        self.apply_template(template)

    def deploy_persistent_volume_claim(
        self, name: str, storage_class: str, namespace: str
    ):
        template = self.template_to_pvc(name, storage_class, namespace)
        self.apply_template(template)

    def deploy_deployment(self, name: str, namespace: str = "default"):
        self.create_deployment(name, namespace)

    def deploy_statefulset(self, name: str, namespace: str = "default"):
        self.create_statefulset(name, namespace)

    def deploy_replicaset(self, name: str, namespace: str = "default"):
        self.create_replicaset(name, namespace)

    def deploy_service(self, name: str = "pause", namespace: str = "default"):
        self.create_service(name, namespace)

    def deploy_daemonset(self, name: str, namespace: str = "default"):
        self.create_daemonset(name, namespace)

    def delete_fake_kraken(self, namespace: str = "default"):
        self.lib_k8s.delete_pod("kraken-deployment", namespace)

    def template_to_job(self, name: str, namespace: str = "default") -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("job.j2")
        content = template.render(name=name, namespace=namespace)
        return content

    def template_to_namespace(
        self, name: str, labels: List[Dict[str, str]]
    ) -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("namespace_template.j2")
        content = template.render(name=name, labels=labels)
        return content

    def template_to_pod(
        self,
        name: str,
        namespace: str = "default",
        random_label: str = None,
        node_name: str = None,
    ) -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("fedtools-deployment.j2")
        if node_name is not None:
            content = template.render(
                name=name,
                namespace=namespace,
                random_label=random_label,
                has_node_selector=True,
                node_name=node_name,
            )
        else:
            content = template.render(
                name=name,
                has_node_selector=False,
                namespace=namespace,
                random_label=random_label,
            )
        return content

    def template_to_pv(self, name: str, storage_class: str, namespace: str):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("pv.j2")
        content = template.render(
            name=name, namespace=namespace, storage_class=storage_class
        )
        return content

    def template_to_pvc(self, name: str, storage_class: str, namespace: str):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("pvc.j2")
        content = template.render(
            name=name, namespace=namespace, storage_class=storage_class
        )
        return content

    def file_to_template(self, file: str, name: str, namespace: str):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template(file)
        content = template.render(name=name, namespace=namespace)
        return content

    def apply_template(self, template: str):
        with tempfile.NamedTemporaryFile(mode="w") as file:
            file.write(template)
            file.flush()
            retries = 3
            while retries > 0:
                template_applied = self.lib_k8s.apply_yaml(
                    file.name, namespace=""
                )
                if template_applied is not None:
                    return
                retries -= 1

    def get_random_string(self, length: int) -> str:
        letters = string.ascii_lowercase
        return "".join(random.choice(letters) for i in range(length))

    def is_openshift(self) -> bool:
        try:
            result = self.lib_k8s.get_clusterversion_string()
            if result == "":
                return False
            return True
        except Exception:
            return False

    def create_networkpolicy(self, name: str, namespace: str = "default"):
        """
        Create a network policy in a namespace

        :param name: network policy name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        content = self.file_to_template("net-policy.j2", name, namespace)

        dep = yaml.safe_load(content)
        self.lib_k8s.create_net_policy(dep, namespace)

    def create_deployment(self, name: str, namespace: str = "default"):
        """
        Create a deployment in a namespace

        :param name: deployment name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        content = self.file_to_template("deployment.j2", name, namespace)

        dep = yaml.safe_load(content)
        self.lib_k8s.create_obj(
            dep, namespace, self.lib_k8s.apps_api.create_namespaced_deployment
        )

    def create_daemonset(self, name: str, namespace: str = "default"):
        """
        Create a daemonset in a namespace

        :param name: daemonset name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        try:
            content = self.file_to_template("daemonset.j2", name, namespace)

            daemonset = yaml.safe_load(content)
            self.lib_k8s.apps_api.create_namespaced_daemon_set(
                body=daemonset, namespace=namespace
            )
        except ApiException as api:
            print(
                "Exception when calling AppsV1Api->create_daemonset: %s", api
            )
            if api.status == 409:
                print("DaemonSet already present")
        except Exception as e:
            logging.error(
                "Exception when calling "
                "BatchV1Api->create_namespaced_job: %s",
                str(e),
            )
            raise e

    def create_replicaset(self, name: str, namespace: str):
        """
        Create a replicaset in a namespace

        :param name: replicaset name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        try:
            content = self.file_to_template("replicaset.j2", name, namespace)

            replicaset = yaml.safe_load(content)
            self.lib_k8s.apps_api.create_namespaced_replica_set(
                body=replicaset, namespace=namespace
            )
        except ApiException as api:
            print(
                "Exception when calling AppsV1Api->create_replicaset: %s", api
            )
            if api.status == 409:
                print("Replicaset already present")
        except Exception as e:
            logging.error(
                "Exception when calling " "AppsV1Api->create_replicaset: %s",
                str(e),
            )
            raise e

    def create_statefulset(self, name: str, namespace: str):
        """
        Create a statefulset in a namespace

        :param name: statefulset name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        try:
            content = self.file_to_template("statefulset.j2", name, namespace)

            statefulset = yaml.safe_load(content)
            self.lib_k8s.apps_api.create_namespaced_stateful_set(
                body=statefulset, namespace=namespace
            )
        except ApiException as api:
            print(
                "Exception when calling AppsV1Api->create_statefulset: %s", api
            )
            if api.status == 409:
                print("Statefulset already present")
        except Exception as e:
            logging.error(
                "Exception when calling " "AppsV1Api->create_replicaset: %s",
                str(e),
            )
            raise e

    def create_service(self, name: str, namespace: str):
        """
        Create a service in a namespace

        :param name: service name
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        """
        try:
            content = self.file_to_template("service.j2", name, namespace)

            service_manifest = yaml.safe_load(content)
            self.lib_k8s.cli.create_namespaced_service(
                body=service_manifest, namespace=namespace
            )
        except ApiException as api:
            print("Exception when calling CoreV1Api->create_service: %s", api)
            if api.status == 409:
                print("Service already present")
        except Exception as e:
            logging.error(
                "Exception when calling " "CoreV1Api->create_service: %s",
                str(e),
            )
            raise e

    def background_delete_pod(self, pod_name: str, namespace: str):
        thread = threading.Thread(
            target=self.lib_k8s.delete_pod, args=(pod_name, namespace)
        )
        thread.daemon = True
        thread.start()

    def get_ChaosRunTelemetry_json(self, run_uuid: str) -> dict:
        example_data = {
            "scenarios": [
                {
                    "start_timestamp": 1628493021.0,
                    "end_timestamp": 1628496621.0,
                    "scenario": "example_scenario.yaml",
                    "scenario_type": "pod_disruption_scenarios",
                    "exit_status": 0,
                    "parameters_base64": "",
                    "parameters": {
                        "parameter_1": "test",
                        "parameter_2": "test",
                        "parameter_3": {"sub_parameter_1": "test"},
                    },
                    "affected_pods": {
                        "recovered": [
                            {
                                "pod_name": "pod1",
                                "namespace": "default",
                                "total_recovery_time": 10.0,
                                "pod_readiness_time": 5.0,
                                "pod_rescheduling_time": 2.0,
                            }
                        ],
                        "unrecovered": [
                            {"pod_name": "pod2", "namespace": "default"}
                        ],
                        "error": "some error",
                    },
                    "affected_nodes": [
                        {
                            "node_name": "kind-control-plane",
                            "node_id": "test",
                            "ready_time": 2.71,
                            "not_ready_time": 3.14,
                            "stopped_time": 0,
                            "running_time": 0,
                            "terminating_time": 0,
                        }
                    ],
                }
            ],
            "node_summary_infos": [
                {
                    "count": 5,
                    "architecture": "aarch64",
                    "instance_type": "m2i.xlarge",
                    "kernel_version": "5.4.0-66-generic",
                    "kubelet_version": "v2.1.2",
                    "os_version": "Linux",
                }
            ],
            "node_taints": [
                {
                    "key": "node.kubernetes.io/unreachable",
                    "value": "NoExecute",
                    "effect": "NoExecute",
                }
            ],
            "kubernetes_objects_count": {"Pod": 5, "Service": 2},
            "network_plugins": ["Calico"],
            "timestamp": "2023-05-22T14:55:02Z",
            "health_checks": [
                {
                    "url": "http://example.com",
                    "status": True,
                    "status_code": "200",
                    "start_timestamp": "2025-03-12T14:57:54.706000",
                    "end_timestamp": "2025-03-12T15:02:13.819742",
                    "duration": 259.113742,
                }
            ],
            "total_node_count": 3,
            "cloud_infrastructure": "AWS",
            "cloud_type": "EC2",
            "run_uuid": run_uuid,
            "cluster_version": "4.18.0-0.nightly-202491014",
            "major_verison": "4.18",
            "job_status": True,
        }
        return example_data
