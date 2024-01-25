import logging
import random
import string
import sys
import tempfile
import time
import unittest
from typing import Dict, List

import requests
import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes import config
from kubernetes.client.rest import ApiException
from requests import ConnectTimeout

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

    @classmethod
    def setUpClass(cls):
        cls.lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)
        cls.lib_ocp = KrknOpenshift(config.KUBE_CONFIG_DEFAULT_LOCATION)
        cls.lib_telemetry_k8s = KrknTelemetryKubernetes(
            SafeLogger(), cls.lib_k8s
        )
        cls.lib_telemetry_ocp = KrknTelemetryOpenshift(
            SafeLogger(), cls.lib_ocp
        )
        host = cls.lib_k8s.api_client.configuration.host
        logging.disable(logging.CRITICAL)
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

    @classmethod
    def tearDownClass(cls) -> None:
        pass

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
            self.lib_k8s.apply_yaml(file.name, "")

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
        self.lib_k8s.apps_api.create_namespaced_deployment(
            body=dep, namespace=namespace
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
