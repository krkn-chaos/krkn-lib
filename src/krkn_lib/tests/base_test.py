import logging
import random
import string
import sys
import tempfile
import time
import unittest
from typing import List, Dict

import requests
from jinja2 import FileSystemLoader, Environment
from kubernetes import config
from requests import ConnectTimeout

from krkn_lib.kubernetes import KrknKubernetes
from krkn_lib.telemetry import KrknTelemetry
from krkn_lib.utils import SafeLogger


class BaseTest(unittest.TestCase):
    lib_k8s: KrknKubernetes
    lib_telemetry: KrknTelemetry

    @classmethod
    def setUpClass(cls):
        cls.lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)
        cls.lib_telemetry = KrknTelemetry(SafeLogger(), cls.lib_k8s)
        host = cls.lib_k8s.api_client.configuration.host
        logging.disable(logging.CRITICAL)
        try:
            requests.get(host, timeout=2, verify=False)
        except ConnectTimeout:
            logging.error(
                "Unable to connect to Kubernetes API %s.\n"
                "To run the tests please setup a running kubernetes cluster.\n"
                "To have a local working kubernetes cluster "
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
