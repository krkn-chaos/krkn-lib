import logging
import tempfile
import unittest

import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes.client import ApiException

from krkn_lib.tests import BaseTest


class KrknKubernetesTestsCreate(BaseTest):
    def test_create_pod(self):
        namespace = "test-cp-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        template_str = self.template_to_pod("fedtools", namespace=namespace)
        body = yaml.safe_load(template_str)
        self.lib_k8s.create_pod(body, namespace)
        try:
            self.wait_pod("fedtools", namespace=namespace)
        except Exception:
            logging.error("failed to create pod")
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put(["fedtools", namespace])

    def test_create_job(self):
        namespace = "test-ns-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        template = self.template_to_job(name, namespace)
        body = yaml.safe_load(template)
        self.lib_k8s.create_job(body, namespace)
        try:
            self.lib_k8s.get_job_status(name, namespace)
        except ApiException:
            logging.error(
                "job {0} in namespace {1} not found, failing.".format(
                    name, namespace
                )
            )
            self.assertTrue(False)
        self.lib_k8s.delete_namespace(namespace)

    def test_apply_yaml(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            environment = Environment(loader=FileSystemLoader("src/testdata/"))
            template = environment.get_template("namespace_template.j2")
            content = template.render(name=namespace, labels=[])
            with tempfile.NamedTemporaryFile(mode="w") as file:
                file.write(content)
                file.flush()
                self.lib_k8s.apply_yaml(file.name, "")
            status = self.lib_k8s.get_namespace_status(namespace)
            self.assertEqual(status, "Active")
        except Exception as e:
            logging.error("exception in test {0}".format(str(e)))
            self.assertTrue(False)

    def test_create_token_for_namespace(self):
        token = self.lib_k8s.create_token_for_sa("default", "default")
        self.assertIsNotNone(token)

        not_token = self.lib_k8s.create_token_for_sa(
            "do_not_exists", "do_not_exists"
        )
        self.assertIsNone(not_token)


if __name__ == "__main__":
    unittest.main()
