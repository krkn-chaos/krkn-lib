#!/usr/bin/env python3

"""
Unit tests for KrknKubernetes.get_pod_pids host-netns PID filtering.

Unlike the cluster-integration tests in test_krkn_kubernetes_get.py these
run without a cluster: exec_cmd_in_pod is mocked, verifying the command
sequences and filtering semantics of the PID resolution.

Run: python -m unittest src/krkn_lib/tests/test_krkn_kubernetes_pod_pids_unit.py -v
"""

import unittest
from unittest.mock import patch

from krkn_lib.k8s import KrknKubernetes


class KrknKubernetesPodPidsUnitTests(unittest.TestCase):
    def setUp(self):
        # do not load a kubeconfig: every cluster interaction is mocked
        with patch.object(KrknKubernetes, "__init__", lambda self: None):
            self.lib_k8s = KrknKubernetes()

    def _mock_exists(self, mock_k8s):
        mock_k8s.check_if_pod_exists.return_value = True

    def test_conmon_host_netns_pids_are_filtered(self):
        """PIDs in the host netns (e.g. conmon) must be excluded."""
        with patch.object(self.lib_k8s, "check_if_pod_exists") as mock_exists, \
             patch.object(self.lib_k8s, "exec_cmd_in_pod") as mock_exec:
            self._mock_exists(mock_exists)
            # cgroup grep returns conmon + container process
            mock_exec.side_effect = ["29892\n29894", "29894"]

            pids = self.lib_k8s.get_pod_pids(
                base_pod_name="helper",
                base_pod_namespace="ns",
                base_pod_container_name="helper-ctr",
                pod_name="target",
                pod_namespace="ns",
                pod_container_id="abc123",
            )

        self.assertEqual(pids, ["29894"])
        # second exec must be the netns comparison filter
        filter_cmd = mock_exec.call_args_list[1][0][0][0]
        self.assertIn("readlink /proc/$p/ns/net", filter_cmd)
        self.assertIn("readlink /proc/1/ns/net", filter_cmd)
        self.assertIn("29892", filter_cmd)
        self.assertIn("29894", filter_cmd)

    def test_all_pids_filtered_returns_raw_list(self):
        """When no PID survives the filter (all host-netns, or readlink
        unavailable), fall back to the raw list rather than None."""
        with patch.object(self.lib_k8s, "check_if_pod_exists") as mock_exists, \
             patch.object(self.lib_k8s, "exec_cmd_in_pod") as mock_exec:
            self._mock_exists(mock_exists)
            mock_exec.side_effect = ["29892\n29894", ""]

            pids = self.lib_k8s.get_pod_pids(
                "helper", "ns", "helper-ctr", "target", "ns", "abc123"
            )

        self.assertEqual(pids, ["29892", "29894"])

    def test_no_cgroup_match_returns_none(self):
        with patch.object(self.lib_k8s, "check_if_pod_exists") as mock_exists, \
             patch.object(self.lib_k8s, "exec_cmd_in_pod") as mock_exec:
            self._mock_exists(mock_exists)
            mock_exec.return_value = None

            pids = self.lib_k8s.get_pod_pids(
                "helper", "ns", "helper-ctr", "target", "ns", "does_not_exist"
            )

        self.assertIsNone(pids)
        # filter never runs when the cgroup grep found nothing
        self.assertEqual(mock_exec.call_count, 1)

    def test_target_pod_missing_raises(self):
        with patch.object(self.lib_k8s, "check_if_pod_exists") as mock_exists, \
             patch.object(self.lib_k8s, "exec_cmd_in_pod") as mock_exec:
            mock_exists.return_value = False

            with self.assertRaises(Exception):
                self.lib_k8s.get_pod_pids(
                    "helper", "ns", "helper-ctr", "target", "ns", "abc123"
                )
            mock_exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
