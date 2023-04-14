import sys
import unittest
import requests
import yaml
import logging
from kubernetes import config
from requests import ConnectTimeout
from .client import KrknLibKubernetes


class KrknLibKubernetesTests(unittest.TestCase):
    lib_k8s: KrknLibKubernetes
    test_pod_body = None

    @classmethod
    def setUpClass(cls):
        cls.lib_k8s = KrknLibKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)
        with open("src/testdata/example_deployment.yaml", "r") as stream:
            try:
                cls.test_pod_body = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        host = cls.lib_k8s.api_client.configuration.host
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

        cls.lib_k8s.create_pod(cls.test_pod_body, "default")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.lib_k8s.delete_pod(cls.test_pod_body["metadata"]["name"])

    def test_exec_command(self):
        try:
            # run command
            cmd = ["-br", "addr", "show"]
            result = self.lib_k8s.exec_cmd_in_pod(
                cmd,
                self.test_pod_body["metadata"]["name"],
                "default",
                base_command="ip",
            )
            self.assertRegex(result, r"\d+\.\d+\.\d+\.\d+")

            # run command in bash
            cmd = ["ls -al /"]
            result = self.lib_k8s.exec_cmd_in_pod(
                cmd, self.test_pod_body["metadata"]["name"], "default"
            )
            self.assertRegex(result, r"etc")
            self.assertRegex(result, r"root")
            self.assertRegex(result, r"bin")
        except Exception as exc:
            assert False, f"command execution raised an exception {exc}"


if __name__ == "__main__":
    unittest.main()
