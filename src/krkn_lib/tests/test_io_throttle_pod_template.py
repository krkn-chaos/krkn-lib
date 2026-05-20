"""Unit tests for io_throttle_pod Jinja template (no cluster required)."""

import unittest

import yaml
from jinja2 import Environment, PackageLoader


class TestIoThrottlePodTemplate(unittest.TestCase):
    def test_template_renders_valid_pod_manifest(self):
        env = Environment(
            loader=PackageLoader("krkn_lib.k8s", "templates"),
            autoescape=True,
        )
        template = env.get_template("io_throttle_pod.j2")
        body = yaml.safe_load(
            template.render(
                pod_suffix="12345",
                nodename="worker-1",
                image="quay.io/example/tools:latest",
            )
        )
        self.assertEqual(body["kind"], "Pod")
        self.assertEqual(body["metadata"]["name"], "io-throttle-12345")
        self.assertEqual(body["spec"]["nodeName"], "worker-1")
        self.assertTrue(
            body["spec"]["containers"][0]["securityContext"]["privileged"]
        )
