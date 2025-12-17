import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from kubernetes.client.rest import ApiException
from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes


class TestKrknKubernetesVirt(unittest.TestCase):

    def setUp(self):
        """Set up mock objects for each test"""
        # Create a mock for custom_object_client
        self.mock_custom_client = MagicMock()

        # Import and create instance with all mocks in place
        with (
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api"),
            patch("kubernetes.client.CustomObjectsApi"),
            patch("kubernetes.client.AppsV1Api"),
            patch("kubernetes.client.BatchV1Api"),
            patch("kubernetes.client.ApiClient"),
            patch("kubernetes.client.VersionApi"),
            patch("kubernetes.client.NetworkingV1Api"),
        ):
            # Create KrknKubernetes instance with mocked dependencies
            self.lib_k8s = KrknKubernetes(kubeconfig_path="dummy")

        # Patch the custom_object_client property to return our mock
        self.custom_client_patcher = patch.object(
            type(self.lib_k8s),
            "custom_object_client",
            new_callable=PropertyMock,
            return_value=self.mock_custom_client,
        )
        self.custom_client_patcher.start()

        # Mock list_namespaces_by_regex method
        self.list_namespaces_patcher = patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=[],
        )
        self.list_namespaces_patcher.start()

    def tearDown(self):
        """Clean up patches after each test"""
        self.custom_client_patcher.stop()
        self.list_namespaces_patcher.stop()

    def test_get_vm_success(self):
        """Test get_vm returns VM when it exists"""
        vm_name = "test-vm"
        namespace = "test-ns"
        expected_vm = {
            "metadata": {"name": vm_name, "namespace": namespace},
            "spec": {"running": True},
        }
        # Configure the mock to return expected_vm
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.return_value = expected_vm

        result = self.lib_k8s.get_vm(vm_name, namespace)

        mock_get.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        self.assertEqual(result, expected_vm)

    def test_get_vm_not_found(self):
        """Test get_vm returns None when VM doesn't exist"""
        vm_name = "non-existent-vm"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        result = self.lib_k8s.get_vm(vm_name, namespace)
        self.assertIsNone(result)

    def test_get_vm_api_error(self):
        """Test get_vm raises exception on API error"""
        vm_name = "test-vm"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.get_vm(vm_name, namespace)

    def test_get_vmi_success(self):
        """Test get_vmi returns VMI when it exists"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        expected_vmi = {
            "metadata": {"name": vmi_name, "namespace": namespace},
            "status": {"phase": "Running"},
        }

        # Configure the mock to return expected_vmi
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.return_value = expected_vmi

        result = self.lib_k8s.get_vmi(vmi_name, namespace)

        mock_get.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachineinstances",
            name=vmi_name,
        )
        self.assertEqual(result, expected_vmi)

    def test_get_vmi_not_found(self):
        """Test get_vmi returns None when VMI doesn't exist"""
        vmi_name = "non-existent-vmi"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        result = self.lib_k8s.get_vmi(vmi_name, namespace)
        self.assertIsNone(result)

    def test_get_vmi_api_error(self):
        """Test get_vmi raises exception on API error"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.get_vmi(vmi_name, namespace)

    def test_get_vmis_success(self):
        """Test get_vmis returns matching VMIs"""
        regex_name = "^test-vmi-.*"
        namespace = "test-ns"
        vmi1 = {
            "metadata": {"name": "test-vmi-1"},
            "status": {"phase": "Running"},
        }
        vmi2 = {
            "metadata": {"name": "test-vmi-2"},
            "status": {"phase": "Running"},
        }
        vmi3 = {
            "metadata": {"name": "other-vmi"},
            "status": {"phase": "Running"},
        }
        vmis_response = {"items": [vmi1, vmi2, vmi3]}

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=[namespace],
        ):
            # Configure the mock to return vmis
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.return_value = vmis_response

            # get_vmis returns a list
            result = self.lib_k8s.get_vmis(regex_name, namespace)

            # Check that only matching VMIs were returned
            self.assertEqual(len(result), 2)
            self.assertIn(vmi1, result)
            self.assertIn(vmi2, result)
            self.assertNotIn(vmi3, result)

    def test_get_vmis_not_found(self):
        """Test get_vmis handles 404 gracefully"""
        regex_name = "^test-vmi-.*"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=[namespace],
        ):
            # Configure the mock to raise 404
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.side_effect = api_exception

            result = self.lib_k8s.get_vmis(regex_name, namespace)
            # Returns [] when 404
            self.assertEqual(result, [])

    def test_get_vmis_multiple_namespaces(self):
        """Test get_vmis searches across multiple namespaces"""
        regex_name = "^test-vmi-.*"
        namespace_pattern = "test-ns-.*"
        namespaces = ["test-ns-1", "test-ns-2"]
        vmi1 = {"metadata": {"name": "test-vmi-1"}}
        vmi2 = {"metadata": {"name": "test-vmi-2"}}
        vmis_response_1 = {"items": [vmi1]}
        vmis_response_2 = {"items": [vmi2]}

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=namespaces,
        ):
            # Configure mock for different responses
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.side_effect = [
                vmis_response_1,
                vmis_response_2,
            ]

            # get_vmis returns a list
            result = self.lib_k8s.get_vmis(regex_name, namespace_pattern)

            self.assertEqual(len(result), 2)
            self.assertIn(vmi1, result)
            self.assertIn(vmi2, result)

    def test_get_vms_success(self):
        """Test get_vms returns matching VMs"""
        regex_name = "^test-vm-.*"
        namespace = "test-ns"
        vm1 = {
            "metadata": {"name": "test-vm-1"},
            "spec": {"running": True},
        }
        vm2 = {
            "metadata": {"name": "test-vm-2"},
            "spec": {"running": False},
        }
        vm3 = {
            "metadata": {"name": "other-vm"},
            "spec": {"running": True},
        }
        vms_response = {"items": [vm1, vm2, vm3]}

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=[namespace],
        ):
            # Configure the mock to return vms
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.return_value = vms_response

            result = self.lib_k8s.get_vms(regex_name, namespace)

            self.assertEqual(len(result), 2)
            self.assertIn(vm1, result)
            self.assertIn(vm2, result)
            self.assertNotIn(vm3, result)

    def test_get_vms_not_found(self):
        """Test get_vms returns empty list when no VMs found"""
        regex_name = "^test-vm-.*"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=[namespace],
        ):
            # Configure the mock to raise 404
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.side_effect = api_exception

            result = self.lib_k8s.get_vms(regex_name, namespace)
            self.assertEqual(result, [])

    def test_get_vms_multiple_namespaces(self):
        """Test get_vms searches across multiple namespaces"""
        regex_name = "^test-vm-.*"
        namespace_pattern = "test-ns-.*"
        namespaces = ["test-ns-1", "test-ns-2"]
        vm1 = {"metadata": {"name": "test-vm-1"}}
        vm2 = {"metadata": {"name": "test-vm-2"}}
        vms_response_1 = {"items": [vm1]}
        vms_response_2 = {"items": [vm2]}

        # Mock list_namespaces_by_regex
        with patch.object(
            self.lib_k8s,
            "list_namespaces_by_regex",
            return_value=namespaces,
        ):
            # Configure mock for different responses
            mock_list = (
                self.mock_custom_client.list_namespaced_custom_object
            )
            mock_list.side_effect = [
                vms_response_1,
                vms_response_2,
            ]

            result = self.lib_k8s.get_vms(regex_name, namespace_pattern)

            self.assertEqual(len(result), 2)
            self.assertIn(vm1, result)
            self.assertIn(vm2, result)

    def test_delete_vm_success(self):
        """Test delete_vm successfully deletes a VM"""
        vm_name = "test-vm"
        namespace = "test-ns"
        expected_response = {
            "metadata": {"name": vm_name},
            "status": {"phase": "Terminating"},
        }

        # Configure the mock to return expected response
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.return_value = expected_response

        result = self.lib_k8s.delete_vm(vm_name, namespace)

        mock_delete.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        self.assertEqual(result, expected_response)

    def test_delete_vm_not_found(self):
        """Test delete_vm returns None when VM doesn't exist"""
        vm_name = "non-existent-vm"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.side_effect = api_exception

        result = self.lib_k8s.delete_vm(vm_name, namespace)
        self.assertIsNone(result)

    def test_delete_vm_api_error(self):
        """Test delete_vm raises exception on API error"""
        vm_name = "test-vm"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.delete_vm(vm_name, namespace)

    def test_delete_vmi_success(self):
        """Test delete_vmi successfully deletes a VMI"""
        vmi_name = "test-vmi"
        namespace = "test-ns"

        # Mock logging
        with patch("krkn_lib.k8s.krkn_kubernetes.logging") as mock_logging:
            # Configure the mock to return None (success)
            mock_delete = (
                self.mock_custom_client.delete_namespaced_custom_object
            )
            mock_delete.return_value = None

            result = self.lib_k8s.delete_vmi(vmi_name, namespace)

            mock_delete.assert_called_once_with(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachineinstances",
                name=vmi_name,
            )
            # delete_vmi doesn't explicitly return on success (returns None)
            self.assertIsNone(result)
            # Verify logging was called
            mock_logging.info.assert_called_once()

    def test_delete_vmi_not_found(self):
        """Test delete_vmi returns 1 when VMI doesn't exist"""
        vmi_name = "non-existent-vmi"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Mock logging
        with patch("krkn_lib.k8s.krkn_kubernetes.logging"):
            # Configure the mock to raise 404
            mock_delete = (
                self.mock_custom_client.delete_namespaced_custom_object
            )
            mock_delete.side_effect = api_exception

            result = self.lib_k8s.delete_vmi(vmi_name, namespace)
            # Returns 1 on 404
            self.assertEqual(result, 1)

    def test_delete_vmi_api_error(self):
        """Test delete_vmi returns 1 on API error"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Mock logging
        with patch("krkn_lib.k8s.krkn_kubernetes.logging"):
            # Configure the mock to raise 500
            mock_delete = (
                self.mock_custom_client.delete_namespaced_custom_object
            )
            mock_delete.side_effect = api_exception

            result = self.lib_k8s.delete_vmi(vmi_name, namespace)
            # Returns 1 on error
            self.assertEqual(result, 1)

    def test_get_snapshot_success(self):
        """Test get_snapshot returns snapshot when it exists"""
        snapshot_name = "test-snapshot"
        namespace = "test-ns"
        expected_snapshot = {
            "metadata": {
                "name": snapshot_name,
                "namespace": namespace,
            },
            "spec": {"source": {"name": "test-vm"}},
            "status": {"readyToUse": True},
        }

        # Configure the mock to return expected_snapshot
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.return_value = expected_snapshot

        result = self.lib_k8s.get_snapshot(snapshot_name, namespace)

        mock_get.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="VirtualMachineSnapshot",
            name=snapshot_name,
        )
        self.assertEqual(result, expected_snapshot)

    def test_get_snapshot_not_found(self):
        """Test get_snapshot returns None when not found"""
        snapshot_name = "non-existent-snapshot"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        result = self.lib_k8s.get_snapshot(snapshot_name, namespace)
        self.assertIsNone(result)

    def test_get_snapshot_api_error(self):
        """Test get_snapshot raises exception on API error"""
        snapshot_name = "test-snapshot"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_get = self.mock_custom_client.get_namespaced_custom_object
        mock_get.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.get_snapshot(snapshot_name, namespace)

    def test_delete_snapshot_success(self):
        """Test delete_snapshot successfully deletes a snapshot"""
        snapshot_name = "test-snapshot"
        namespace = "test-ns"

        # Mock the logger and snapshot_name attributes
        self.lib_k8s.logger = MagicMock()
        self.lib_k8s.snapshot_name = snapshot_name

        # Configure the mock to return None (success)
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.return_value = None

        # Should not raise any exception
        self.lib_k8s.delete_snapshot(snapshot_name, namespace)

        mock_delete.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="VirtualMachineSnapshot",
            name=snapshot_name,
        )
        # Verify logger was called (uses self.snapshot_name, not parameter)
        self.lib_k8s.logger.info.assert_any_call(
            f"Deleting snapshot '{snapshot_name}'..."
        )
        self.lib_k8s.logger.info.assert_any_call(
            f"Snapshot '{snapshot_name}' deleted successfully."
        )

    def test_delete_snapshot_not_found(self):
        """Test delete_snapshot handles deletion gracefully"""
        snapshot_name = "non-existent-snapshot"
        namespace = "test-ns"
        api_exception = ApiException(status=404)

        # Mock the logger and snapshot_name attributes
        self.lib_k8s.logger = MagicMock()
        self.lib_k8s.snapshot_name = snapshot_name

        # Configure the mock to raise 404
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.side_effect = api_exception

        # Should not raise exception, but log warning
        self.lib_k8s.delete_snapshot(snapshot_name, namespace)

        # Verify warning was logged
        self.lib_k8s.logger.warning.assert_called_once()
        warning_call_args = self.lib_k8s.logger.warning.call_args[0][0]
        self.assertIn("Failed to delete snapshot", warning_call_args)

    def test_delete_snapshot_api_error(self):
        """Test delete_snapshot handles API errors gracefully"""
        snapshot_name = "test-snapshot"
        namespace = "test-ns"
        api_exception = ApiException(status=500)

        # Mock the logger and snapshot_name attributes
        self.lib_k8s.logger = MagicMock()
        self.lib_k8s.snapshot_name = snapshot_name

        # Configure the mock to raise 500
        mock_delete = (
            self.mock_custom_client.delete_namespaced_custom_object
        )
        mock_delete.side_effect = api_exception

        # Should not raise exception, but log warning
        self.lib_k8s.delete_snapshot(snapshot_name, namespace)

        # Verify warning was logged
        self.lib_k8s.logger.warning.assert_called_once()
        warning_call_args = self.lib_k8s.logger.warning.call_args[0][0]
        self.assertIn("Failed to delete snapshot", warning_call_args)

    def test_create_vmi_success(self):
        """Test create_vmi successfully creates a VMI"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        vm_name = "test-vm"
        vmi_body = {
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachineInstance",
            "metadata": {"name": vmi_name, "namespace": namespace},
            "spec": {"domain": {"devices": {}}},
        }
        expected_vmi = {
            "metadata": {"name": vmi_name, "namespace": namespace},
            "status": {"phase": "Pending"},
        }

        # Configure the mock to return expected_vmi
        mock_create = (
            self.mock_custom_client.create_namespaced_custom_object
        )
        mock_create.return_value = expected_vmi

        result = self.lib_k8s.create_vmi(
            vmi_name, namespace, vm_name, vmi_body
        )

        mock_create.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachineinstances",
            name=vmi_name,
            body=vmi_body,
        )
        self.assertEqual(result, expected_vmi)

    def test_create_vmi_not_found(self):
        """Test create_vmi returns None when resource not found"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        vm_name = "non-existent-vm"
        vmi_body = {"metadata": {"name": vmi_name}}
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_create = (
            self.mock_custom_client.create_namespaced_custom_object
        )
        mock_create.side_effect = api_exception

        result = self.lib_k8s.create_vmi(
            vmi_name, namespace, vm_name, vmi_body
        )
        self.assertIsNone(result)

    def test_create_vmi_api_error(self):
        """Test create_vmi raises exception on API error"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        vm_name = "test-vm"
        vmi_body = {"metadata": {"name": vmi_name}}
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_create = (
            self.mock_custom_client.create_namespaced_custom_object
        )
        mock_create.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.create_vmi(
                vmi_name, namespace, vm_name, vmi_body
            )

    def test_patch_vm_success(self):
        """Test patch_vm successfully patches a VM"""
        vm_name = "test-vm"
        namespace = "test-ns"
        vm_body = {
            "spec": {
                "running": True,
                "template": {"metadata": {"labels": {"app": "test"}}},
            }
        }
        expected_vm = {
            "metadata": {"name": vm_name, "namespace": namespace},
            "spec": {"running": True},
        }

        # Configure the mock to return expected_vm
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.return_value = expected_vm

        result = self.lib_k8s.patch_vm(vm_name, namespace, vm_body)

        mock_patch.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
            body=vm_body,
        )
        self.assertEqual(result, expected_vm)

    def test_patch_vm_not_found(self):
        """Test patch_vm returns None when VM doesn't exist"""
        vm_name = "non-existent-vm"
        namespace = "test-ns"
        vm_body = {"spec": {"running": False}}
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.side_effect = api_exception

        result = self.lib_k8s.patch_vm(vm_name, namespace, vm_body)
        self.assertIsNone(result)

    def test_patch_vm_api_error(self):
        """Test patch_vm raises exception on API error"""
        vm_name = "test-vm"
        namespace = "test-ns"
        vm_body = {"spec": {"running": True}}
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.patch_vm(vm_name, namespace, vm_body)

    def test_patch_vmi_success(self):
        """Test patch_vmi successfully patches a VMI"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        vmi_body = {
            "metadata": {
                "labels": {"environment": "production"},
            }
        }
        expected_vmi = {
            "metadata": {
                "name": vmi_name,
                "namespace": namespace,
                "labels": {"environment": "production"},
            },
            "status": {"phase": "Running"},
        }

        # Configure the mock to return expected_vmi
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.return_value = expected_vmi

        result = self.lib_k8s.patch_vmi(vmi_name, namespace, vmi_body)

        mock_patch.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            namespace=namespace,
            plural="virtualmachineinstances",
            name=vmi_name,
            body=vmi_body,
        )
        self.assertEqual(result, expected_vmi)

    def test_patch_vmi_not_found(self):
        """Test patch_vmi returns None when VMI doesn't exist"""
        vmi_name = "non-existent-vmi"
        namespace = "test-ns"
        vmi_body = {"metadata": {"labels": {"app": "test"}}}
        api_exception = ApiException(status=404)

        # Configure the mock to raise 404
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.side_effect = api_exception

        result = self.lib_k8s.patch_vmi(vmi_name, namespace, vmi_body)
        self.assertIsNone(result)

    def test_patch_vmi_api_error(self):
        """Test patch_vmi raises exception on API error"""
        vmi_name = "test-vmi"
        namespace = "test-ns"
        vmi_body = {"metadata": {"labels": {"app": "test"}}}
        api_exception = ApiException(status=500)

        # Configure the mock to raise 500
        mock_patch = (
            self.mock_custom_client.patch_namespaced_custom_object
        )
        mock_patch.side_effect = api_exception

        with self.assertRaises(ApiException):
            self.lib_k8s.patch_vmi(vmi_name, namespace, vmi_body)
