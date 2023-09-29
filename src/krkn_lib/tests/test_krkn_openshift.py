from kubernetes import client

from krkn_lib.tests import BaseTest


class KrknOpenshiftTest(BaseTest):
    def test_get_cluster_version_string(self):
        # TODO
        result = self.lib_ocp.get_clusterversion_string()
        self.assertIsNotNone(result)

    def test_get_cluster_network_plugins(self):
        resp = self.lib_ocp.get_cluster_network_plugins()
        self.assertTrue(len(resp) > 0)
        self.assertEqual(resp[0], "Unknown")

    def test_get_cluster_infrastructure(self):
        resp = self.lib_ocp.get_cluster_infrastructure()
        self.assertTrue(resp)
        self.assertEqual(resp, "Unknown")
