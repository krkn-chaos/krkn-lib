"""
Tests for KubernetesObjectHelpers
"""

import unittest
from unittest.mock import MagicMock
from kubernetes.client.rest import ApiException
from krkn_lib.k8s.kubernetes_object_helpers import KubernetesObjectHelpers


class TestKubernetesObjectHelpers(unittest.TestCase):
    """Tests for KubernetesObjectHelpers class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_krkn = MagicMock()
        self.helpers = KubernetesObjectHelpers(self.mock_krkn)

    def test_get_object_by_name_pod(self):
        """Test getting a Pod using get_object_by_name"""
        mock_pod = {"metadata": {"name": "test-pod", "namespace": "default"}}
        self.mock_krkn.cli.read_namespaced_pod.return_value = mock_pod
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pod

        result = self.helpers.get_object_by_name("Pod", "test-pod", "default")

        self.assertEqual(result, mock_pod)
        self.mock_krkn.cli.read_namespaced_pod.assert_called_once_with("test-pod", "default")

    def test_get_object_by_name_deployment(self):
        """Test getting a Deployment using get_object_by_name"""
        mock_deployment = {"metadata": {"name": "test-deploy"}}
        self.mock_krkn.apps_api.read_namespaced_deployment.return_value = mock_deployment
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_deployment

        result = self.helpers.get_object_by_name("Deployment", "test-deploy", "default")

        self.assertEqual(result, mock_deployment)
        self.mock_krkn.apps_api.read_namespaced_deployment.assert_called_once_with("test-deploy", "default")

    def test_get_object_by_name_statefulset(self):
        """Test getting a StatefulSet using get_object_by_name"""
        mock_sts = {"metadata": {"name": "test-sts"}}
        self.mock_krkn.apps_api.read_namespaced_stateful_set.return_value = mock_sts
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_sts

        result = self.helpers.get_object_by_name("StatefulSet", "test-sts", "default")

        self.assertEqual(result, mock_sts)
        self.mock_krkn.apps_api.read_namespaced_stateful_set.assert_called_once_with("test-sts", "default")

    def test_get_object_by_name_daemonset(self):
        """Test getting a DaemonSet using get_object_by_name"""
        mock_ds = {"metadata": {"name": "test-ds"}}
        self.mock_krkn.apps_api.read_namespaced_daemon_set.return_value = mock_ds
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_ds

        result = self.helpers.get_object_by_name("DaemonSet", "test-ds", "default")

        self.assertEqual(result, mock_ds)
        self.mock_krkn.apps_api.read_namespaced_daemon_set.assert_called_once_with("test-ds", "default")

    def test_get_object_by_name_replicaset(self):
        """Test getting a ReplicaSet using get_object_by_name"""
        mock_rs = {"metadata": {"name": "test-rs"}}
        self.mock_krkn.apps_api.read_namespaced_replica_set.return_value = mock_rs
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_rs

        result = self.helpers.get_object_by_name("ReplicaSet", "test-rs", "default")

        self.assertEqual(result, mock_rs)
        self.mock_krkn.apps_api.read_namespaced_replica_set.assert_called_once_with("test-rs", "default")

    def test_get_object_by_name_service(self):
        """Test getting a Service using get_object_by_name"""
        mock_svc = {"metadata": {"name": "test-svc"}}
        self.mock_krkn.cli.read_namespaced_service.return_value = mock_svc
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_svc

        result = self.helpers.get_object_by_name("Service", "test-svc", "default")

        self.assertEqual(result, mock_svc)
        self.mock_krkn.cli.read_namespaced_service.assert_called_once_with("test-svc", "default")

    def test_get_object_by_name_persistentvolumeclaim(self):
        """Test getting a PersistentVolumeClaim using get_object_by_name"""
        mock_pvc = {"metadata": {"name": "test-pvc"}}
        self.mock_krkn.cli.read_namespaced_persistent_volume_claim.return_value = mock_pvc
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pvc

        result = self.helpers.get_object_by_name("PersistentVolumeClaim", "test-pvc", "default")

        self.assertEqual(result, mock_pvc)
        self.mock_krkn.cli.read_namespaced_persistent_volume_claim.assert_called_once_with("test-pvc", "default")

    def test_get_object_by_name_job(self):
        """Test getting a Job using get_object_by_name"""
        mock_job = {"metadata": {"name": "test-job"}}
        self.mock_krkn.batch_cli.read_namespaced_job.return_value = mock_job
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_job

        result = self.helpers.get_object_by_name("Job", "test-job", "default")

        self.assertEqual(result, mock_job)
        self.mock_krkn.batch_cli.read_namespaced_job.assert_called_once_with("test-job", "default")

    def test_get_object_by_name_cronjob(self):
        """Test getting a CronJob using get_object_by_name"""
        mock_cj = {"metadata": {"name": "test-cj"}}
        self.mock_krkn.batch_cli.read_namespaced_cron_job.return_value = mock_cj
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_cj

        result = self.helpers.get_object_by_name("CronJob", "test-cj", "default")

        self.assertEqual(result, mock_cj)
        self.mock_krkn.batch_cli.read_namespaced_cron_job.assert_called_once_with("test-cj", "default")

    def test_get_object_by_name_node(self):
        """Test getting a Node using get_object_by_name"""
        mock_node = {"metadata": {"name": "worker-1"}}
        self.mock_krkn.cli.read_node.return_value = mock_node
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_node

        result = self.helpers.get_object_by_name("Node", "worker-1")

        self.assertEqual(result, mock_node)
        self.mock_krkn.cli.read_node.assert_called_once_with("worker-1")

    def test_get_object_by_name_persistentvolume(self):
        """Test getting a PersistentVolume using get_object_by_name"""
        mock_pv = {"metadata": {"name": "test-pv"}}
        self.mock_krkn.cli.read_persistent_volume.return_value = mock_pv
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pv

        result = self.helpers.get_object_by_name("PersistentVolume", "test-pv")

        self.assertEqual(result, mock_pv)
        self.mock_krkn.cli.read_persistent_volume.assert_called_once_with("test-pv")

    def test_get_object_by_name_case_insensitive(self):
        """Test that resource kind is case-insensitive"""
        mock_pod = {"metadata": {"name": "test-pod"}}
        self.mock_krkn.cli.read_namespaced_pod.return_value = mock_pod
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pod

        result = self.helpers.get_object_by_name("pod", "test-pod", "default")

        self.assertEqual(result, mock_pod)

    def test_get_object_by_name_missing_namespace_raises(self):
        """Test that missing namespace for namespaced resource raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.helpers.get_object_by_name("Pod", "test-pod")

        self.assertIn("Namespace is required", str(context.exception))

    def test_get_object_by_name_unsupported_kind(self):
        """Test that unsupported resource kind returns None"""
        result = self.helpers.get_object_by_name("UnsupportedKind", "test", "default")
        self.assertIsNone(result)

    def test_get_object_by_name_api_exception(self):
        """Test that ApiException is re-raised"""
        self.mock_krkn.cli.read_namespaced_pod.side_effect = ApiException(404, "Not Found")

        with self.assertRaises(ApiException):
            self.helpers.get_object_by_name("Pod", "test-pod", "default")

    def test_get_object_by_name_cluster_scoped_ignores_namespace(self):
        """Test that cluster-scoped resources don't use namespace"""
        mock_node = {"metadata": {"name": "worker-1"}}
        self.mock_krkn.cli.read_node.return_value = mock_node
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_node

        result = self.helpers.get_object_by_name("Node", "worker-1", namespace="ignored")

        self.assertEqual(result, mock_node)
        self.mock_krkn.cli.read_node.assert_called_once_with("worker-1")

    def test_list_objects_by_kind_pods(self):
        """Test listing pods with pagination support"""
        mock_pod_1 = {"metadata": {"name": "pod-1", "namespace": "default"}}
        mock_pod_2 = {"metadata": {"name": "pod-2", "namespace": "default"}}

        mock_response = MagicMock()
        mock_response.items = [mock_pod_1, mock_pod_2]

        self.mock_krkn.list_continue_helper.return_value = [mock_response]
        self.mock_krkn.api_client.sanitize_for_serialization.side_effect = [mock_pod_1, mock_pod_2]
        self.mock_krkn.request_chunk_size = 500

        result = self.helpers.list_objects_by_kind("Pod", "default")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], mock_pod_1)
        self.assertEqual(result[1], mock_pod_2)

    def test_list_objects_by_kind_with_pagination(self):
        """Test listing with continue token for pagination"""
        mock_pod_1 = {"metadata": {"name": "pod-1"}}
        mock_pod_2 = {"metadata": {"name": "pod-2"}}
        mock_pod_3 = {"metadata": {"name": "pod-3"}}

        # First page response
        mock_response_1 = MagicMock()
        mock_response_1.items = [mock_pod_1, mock_pod_2]

        # Second page response
        mock_response_2 = MagicMock()
        mock_response_2.items = [mock_pod_3]

        # list_continue_helper returns list of response objects
        self.mock_krkn.list_continue_helper.return_value = [mock_response_1, mock_response_2]
        self.mock_krkn.api_client.sanitize_for_serialization.side_effect = [mock_pod_1, mock_pod_2, mock_pod_3]
        self.mock_krkn.request_chunk_size = 2

        result = self.helpers.list_objects_by_kind("Pod", "default", limit=2)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], mock_pod_1)
        self.assertEqual(result[1], mock_pod_2)
        self.assertEqual(result[2], mock_pod_3)

    def test_list_objects_by_kind_with_label_selector(self):
        """Test listing with label selector"""
        mock_pod = {"metadata": {"name": "pod-1", "labels": {"app": "test"}}}

        mock_response = MagicMock()
        mock_response.items = [mock_pod]

        self.mock_krkn.list_continue_helper.return_value = [mock_response]
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pod
        self.mock_krkn.request_chunk_size = 500

        result = self.helpers.list_objects_by_kind("Pod", "default", label_selector="app=test")

        self.assertEqual(len(result), 1)
        # Verify list_continue_helper was called with correct params
        call_args = self.mock_krkn.list_continue_helper.call_args
        self.assertEqual(call_args[0][1], "default")  # First positional arg after method
        self.assertEqual(call_args[1]['label_selector'], "app=test")

    def test_list_objects_by_kind_nodes(self):
        """Test listing cluster-scoped nodes"""
        mock_node_1 = {"metadata": {"name": "worker-1"}}
        mock_node_2 = {"metadata": {"name": "worker-2"}}

        mock_response = MagicMock()
        mock_response.items = [mock_node_1, mock_node_2]

        self.mock_krkn.list_continue_helper.return_value = [mock_response]
        self.mock_krkn.api_client.sanitize_for_serialization.side_effect = [mock_node_1, mock_node_2]

        result = self.helpers.list_objects_by_kind("Node")

        self.assertEqual(len(result), 2)
        self.mock_krkn.list_continue_helper.assert_called_once()

    def test_list_objects_by_kind_missing_namespace(self):
        """Test that listing namespaced resources requires namespace"""
        with self.assertRaises(ValueError) as context:
            self.helpers.list_objects_by_kind("Pod")

        self.assertIn("Namespace is required", str(context.exception))

    def test_list_objects_by_kind_unsupported(self):
        """Test listing unsupported resource kind returns empty list"""
        result = self.helpers.list_objects_by_kind("UnsupportedKind", "default")
        self.assertEqual(result, [])

    def test_watch_crd_objects_with_handler(self):
        """Test watching CRD objects with event handler"""
        mock_event_1 = {
            'type': 'ADDED',
            'object': MagicMock(metadata=MagicMock(name='widget-1'))
        }
        mock_event_2 = {
            'type': 'MODIFIED',
            'object': MagicMock(metadata=MagicMock(name='widget-1'))
        }

        mock_api_resource = MagicMock()
        mock_dyn_client = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_api_resource

        self.mock_krkn.dyn_client = mock_dyn_client
        self.mock_krkn.api_client.sanitize_for_serialization.side_effect = [
            {'metadata': {'name': 'widget-1'}, 'spec': {}},
            {'metadata': {'name': 'widget-1'}, 'spec': {'updated': True}}
        ]

        events_received = []

        def event_handler(event_type, obj):
            events_received.append((event_type, obj['metadata']['name']))

        # Mock the watch stream
        with unittest.mock.patch('krkn_lib.k8s.kubernetes_object_helpers.k8s_watch.Watch') as mock_watch_class:
            mock_watch_instance = MagicMock()
            mock_watch_class.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [mock_event_1, mock_event_2]

            result = self.helpers.watch_crd_objects(
                "example.com", "v1", "widgets",
                namespace="default",
                event_handler=event_handler
            )

            # When handler is provided, result should be None
            self.assertIsNone(result)
            # Verify events were processed
            self.assertEqual(len(events_received), 2)
            self.assertEqual(events_received[0], ('ADDED', 'widget-1'))
            self.assertEqual(events_received[1], ('MODIFIED', 'widget-1'))

    def test_watch_crd_objects_without_handler(self):
        """Test watching CRD objects without handler returns list of events"""
        mock_event_1 = {
            'type': 'ADDED',
            'object': MagicMock(metadata=MagicMock(name='widget-1'))
        }
        mock_event_2 = {
            'type': 'DELETED',
            'object': MagicMock(metadata=MagicMock(name='widget-1'))
        }

        mock_api_resource = MagicMock()
        mock_dyn_client = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_api_resource

        self.mock_krkn.dyn_client = mock_dyn_client
        self.mock_krkn.api_client.sanitize_for_serialization.side_effect = [
            {'metadata': {'name': 'widget-1'}, 'spec': {}},
            {'metadata': {'name': 'widget-1'}, 'spec': {}}
        ]

        # Mock the watch stream
        with unittest.mock.patch('krkn_lib.k8s.kubernetes_object_helpers.k8s_watch.Watch') as mock_watch_class:
            mock_watch_instance = MagicMock()
            mock_watch_class.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [mock_event_1, mock_event_2]

            result = self.helpers.watch_crd_objects(
                "example.com", "v1", "widgets",
                namespace="default"
            )

            # When no handler, should return list of events
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['type'], 'ADDED')
            self.assertEqual(result[1]['type'], 'DELETED')

    def test_watch_crd_objects_with_selectors(self):
        """Test watching CRD objects with label and field selectors"""
        mock_api_resource = MagicMock()
        mock_dyn_client = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_api_resource

        self.mock_krkn.dyn_client = mock_dyn_client

        with unittest.mock.patch('krkn_lib.k8s.kubernetes_object_helpers.k8s_watch.Watch') as mock_watch_class:
            mock_watch_instance = MagicMock()
            mock_watch_class.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = []

            self.helpers.watch_crd_objects(
                "example.com", "v1", "widgets",
                namespace="default",
                label_selector="app=test",
                field_selector="status.phase=Active",
                timeout_seconds=30
            )

            # Verify stream was called with correct selectors
            call_kwargs = mock_watch_instance.stream.call_args[1]
            self.assertEqual(call_kwargs['label_selector'], "app=test")
            self.assertEqual(call_kwargs['field_selector'], "status.phase=Active")
            self.assertEqual(call_kwargs['timeout_seconds'], 30)

    def test_watch_crd_objects_missing_dyn_client(self):
        """Test watch returns None when dynamic client not available"""
        # Mock the krkn instance without dyn_client
        mock_krkn_no_dyn = MagicMock(spec=['api_client'])
        helpers = KubernetesObjectHelpers(mock_krkn_no_dyn)

        result = helpers.watch_crd_objects(
            "example.com", "v1", "widgets",
            namespace="default"
        )

        # Should return None and log error
        self.assertIsNone(result)

    def test_watch_crd_objects_handler_exception(self):
        """Test watch handles exceptions in event handler gracefully"""
        mock_event = {
            'type': 'ADDED',
            'object': MagicMock(metadata=MagicMock(name='widget-1'))
        }

        mock_api_resource = MagicMock()
        mock_dyn_client = MagicMock()
        mock_dyn_client.resources.get.return_value = mock_api_resource

        self.mock_krkn.dyn_client = mock_dyn_client
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = {'metadata': {'name': 'widget-1'}}

        def failing_handler(event_type, obj):
            raise ValueError("Handler error")

        with unittest.mock.patch('krkn_lib.k8s.kubernetes_object_helpers.k8s_watch.Watch') as mock_watch_class:
            mock_watch_instance = MagicMock()
            mock_watch_class.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [mock_event]

            # Should not raise, but log the error
            result = self.helpers.watch_crd_objects(
                "example.com", "v1", "widgets",
                namespace="default",
                event_handler=failing_handler
            )

            # Handler exception shouldn't stop the watch
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
