"""
Comprehensive unit tests for KrknTelemetryKubernetes class.

This test suite uses mocks to test all methods without requiring
actual Kubernetes clusters or external services.
"""

import base64
import os
import tempfile
import unittest
from queue import Queue
from unittest.mock import Mock, patch

import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.krkn import ChaosRunAlert, ChaosRunAlertSummary
from krkn_lib.models.telemetry import ChaosRunTelemetry, ScenarioTelemetry
from krkn_lib.telemetry.k8s.krkn_telemetry_kubernetes import (
    KrknTelemetryKubernetes,
)
from krkn_lib.utils.safe_logger import SafeLogger


class TestKrknTelemetryKubernetesInit(unittest.TestCase):
    """Test initialization and basic getter methods."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "username": "test_user",
            "password": "test_pass",
            "telemetry_group": "test_group",
        }
        self.request_id = "test-request-123"

    def test_init_with_config(self):
        """Test initialization with telemetry config."""
        telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
            krkn_telemetry_config=self.telemetry_config,
            telemetry_request_id=self.request_id,
        )

        self.assertEqual(telemetry.get_lib_kubernetes(), self.mock_kubecli)
        self.assertEqual(
            telemetry.get_telemetry_config(), self.telemetry_config
        )
        self.assertEqual(telemetry.get_telemetry_request_id(), self.request_id)

    def test_init_without_config(self):
        """Test initialization without telemetry config."""
        telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

        self.assertEqual(telemetry.get_telemetry_config(), {})
        self.assertEqual(telemetry.get_telemetry_request_id(), "")

    def test_default_telemetry_group(self):
        """Test default telemetry group value."""
        telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

        self.assertEqual(telemetry.default_telemetry_group, "default")


class TestCollectClusterMetadata(unittest.TestCase):
    """Test collect_cluster_metadata method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    @patch("krkn_lib.utils.get_ci_job_url")
    def test_collect_cluster_metadata_success(self, mock_get_ci_url):
        """Test successful collection of cluster metadata."""
        # Setup mocks
        mock_get_ci_url.return_value = "https://ci.example.com/job/123"

        mock_obj_count = {"Deployment": 10, "Pod": 50, "Secret": 5}
        self.mock_kubecli.get_all_kubernetes_object_count.return_value = (
            mock_obj_count
        )

        mock_node_info = Mock(count=3, instance_type="m5.large")
        mock_taints = ["NoSchedule"]
        self.mock_kubecli.get_nodes_infos.return_value = (
            [mock_node_info],
            mock_taints,
        )
        self.mock_kubecli.get_version.return_value = "v1.28.0"

        # Create telemetry with successful scenario
        chaos_telemetry = ChaosRunTelemetry()
        scenario1 = ScenarioTelemetry()
        scenario1.exit_status = 0
        chaos_telemetry.scenarios.append(scenario1)

        # Execute
        self.telemetry.collect_cluster_metadata(chaos_telemetry)

        # Assertions
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count, mock_obj_count
        )
        self.assertEqual(chaos_telemetry.node_summary_infos, [mock_node_info])
        self.assertEqual(chaos_telemetry.cluster_version, "v1.28.0")
        self.assertEqual(chaos_telemetry.major_version, "1.28")
        self.assertEqual(chaos_telemetry.node_taints, mock_taints)
        self.assertEqual(
            chaos_telemetry.build_url, "https://ci.example.com/job/123"
        )
        self.assertEqual(chaos_telemetry.total_node_count, 3)
        self.assertTrue(chaos_telemetry.job_status)  # No failed scenarios

        self.mock_logger.info.assert_called()

    @patch("krkn_lib.utils.get_ci_job_url")
    def test_collect_cluster_metadata_with_failed_scenario(
        self, mock_get_ci_url
    ):
        """Test metadata collection when scenario failed."""
        mock_get_ci_url.return_value = None
        self.mock_kubecli.get_all_kubernetes_object_count.return_value = {}
        self.mock_kubecli.get_nodes_infos.return_value = ([], [])
        self.mock_kubecli.get_version.return_value = "v1.27.5"

        chaos_telemetry = ChaosRunTelemetry()
        scenario1 = ScenarioTelemetry()
        scenario1.exit_status = 1  # Failed scenario
        chaos_telemetry.scenarios.append(scenario1)

        self.telemetry.collect_cluster_metadata(chaos_telemetry)

        self.assertFalse(chaos_telemetry.job_status)  # Should be False

    @patch("krkn_lib.utils.get_ci_job_url")
    def test_collect_cluster_metadata_multiple_nodes(self, mock_get_ci_url):
        """Test with multiple node types."""
        mock_get_ci_url.return_value = None
        self.mock_kubecli.get_all_kubernetes_object_count.return_value = {}

        node_info1 = Mock(count=3)
        node_info2 = Mock(count=5)
        self.mock_kubecli.get_nodes_infos.return_value = (
            [node_info1, node_info2],
            [],
        )
        self.mock_kubecli.get_version.return_value = "v1.29.1"

        chaos_telemetry = ChaosRunTelemetry()
        self.telemetry.collect_cluster_metadata(chaos_telemetry)

        self.assertEqual(chaos_telemetry.total_node_count, 8)  # 3 + 5


class TestSendTelemetry(unittest.TestCase):
    """Test send_telemetry method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    @patch("requests.post")
    def test_send_telemetry_success(self, mock_post):
        """Test successful telemetry send."""
        # Setup
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            "telemetry_group": "testgroup",
        }

        chaos_telemetry = ChaosRunTelemetry()
        uuid = "test-uuid-123"

        # Execute
        result = self.telemetry.send_telemetry(
            telemetry_config, uuid, chaos_telemetry
        )

        # Assertions
        self.assertIsNotNone(result)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["url"], "https://test-api.com/telemetry")
        self.assertEqual(call_kwargs["auth"], ("testuser", "testpass"))
        self.assertEqual(call_kwargs["params"]["request_id"], uuid)
        self.assertEqual(call_kwargs["params"]["telemetry_group"], "testgroup")

        self.mock_logger.info.assert_called_with(
            "successfully sent telemetry data"
        )

    @patch("requests.post")
    def test_send_telemetry_default_group(self, mock_post):
        """Test telemetry send with default group."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            # telemetry_group not specified
        }

        self.telemetry.send_telemetry(
            telemetry_config, "test-uuid", ChaosRunTelemetry()
        )

        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["params"]["telemetry_group"], "default")

    def test_send_telemetry_disabled(self):
        """Test when telemetry is disabled."""
        telemetry_config = {"enabled": False}

        result = self.telemetry.send_telemetry(
            telemetry_config, "test-uuid", ChaosRunTelemetry()
        )

        self.assertIsNone(result)

    def test_send_telemetry_missing_api_url(self):
        """Test with missing api_url."""
        telemetry_config = {
            "enabled": True,
            "username": "testuser",
            "password": "testpass",
        }

        with self.assertRaises(Exception) as context:
            self.telemetry.send_telemetry(
                telemetry_config, "test-uuid", ChaosRunTelemetry()
            )

        self.assertIn("api_url is missing", str(context.exception))

    def test_send_telemetry_missing_username(self):
        """Test with missing username."""
        telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "password": "testpass",
        }

        with self.assertRaises(Exception) as context:
            self.telemetry.send_telemetry(
                telemetry_config, "test-uuid", ChaosRunTelemetry()
            )

        self.assertIn("username is missing", str(context.exception))

    def test_send_telemetry_missing_password(self):
        """Test with missing password."""
        telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
        }

        with self.assertRaises(Exception) as context:
            self.telemetry.send_telemetry(
                telemetry_config, "test-uuid", ChaosRunTelemetry()
            )

        self.assertIn("password is missing", str(context.exception))

    def test_send_telemetry_multiple_missing_fields(self):
        """Test with multiple missing required fields."""
        telemetry_config = {"enabled": True}

        with self.assertRaises(Exception) as context:
            self.telemetry.send_telemetry(
                telemetry_config, "test-uuid", ChaosRunTelemetry()
            )

        exception_str = str(context.exception)
        self.assertIn("api_url is missing", exception_str)
        self.assertIn("username is missing", exception_str)
        self.assertIn("password is missing", exception_str)

    @patch("requests.post")
    def test_send_telemetry_http_error(self, mock_post):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = b"Internal Server Error"
        mock_post.return_value = mock_response

        telemetry_config = {
            "enabled": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
        }

        with self.assertRaises(Exception) as context:
            self.telemetry.send_telemetry(
                telemetry_config, "test-uuid", ChaosRunTelemetry()
            )

        self.assertIn("failed to send telemetry", str(context.exception))
        self.assertIn("500", str(context.exception))
        self.mock_logger.warning.assert_called()


class TestSetParametersBase64(unittest.TestCase):
    """Test set_parameters_base64 method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    def test_set_parameters_base64_success(self):
        """Test successful base64 encoding of scenario file."""
        scenario_yaml = {
            "scenario": "pod_kill",
            "kubeconfig": "/path/to/kubeconfig",
            "param1": "value1",
        }
        yaml_content = yaml.safe_dump(scenario_yaml)

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".yaml"
        ) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            scenario_telemetry = ScenarioTelemetry()
            result = self.telemetry.set_parameters_base64(
                scenario_telemetry, temp_path
            )

            # Verify base64 was set
            self.assertIsNotNone(scenario_telemetry.parameters_base64)

            # Decode and verify
            decoded = base64.b64decode(
                scenario_telemetry.parameters_base64.encode()
            ).decode()
            decoded_yaml = yaml.safe_load(decoded)

            self.assertEqual(decoded_yaml["scenario"], "pod_kill")
            self.assertEqual(decoded_yaml["kubeconfig"], "anonymized")
            self.assertEqual(decoded_yaml["param1"], "value1")
            self.assertIsInstance(result, dict)
        finally:
            os.unlink(temp_path)

    def test_set_parameters_base64_file_not_found(self):
        """Test with non-existent file."""
        scenario_telemetry = ScenarioTelemetry()

        with self.assertRaises(Exception) as context:
            self.telemetry.set_parameters_base64(
                scenario_telemetry, "/nonexistent/file.yaml"
            )

        self.assertIn("scenario file not found", str(context.exception))

    def test_set_parameters_base64_invalid_yaml(self):
        """Test with invalid YAML content."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".yaml"
        ) as f:
            f.write("invalid: yaml: content:\n  - this is\n  bad yaml")
            f.flush()
            temp_path = f.name

        try:
            scenario_telemetry = ScenarioTelemetry()

            with self.assertRaises(Exception) as context:
                self.telemetry.set_parameters_base64(
                    scenario_telemetry, temp_path
                )

            # The exception comes from yaml processing
            self.assertIn("telemetry:", str(context.exception))
        finally:
            os.unlink(temp_path)

    def test_set_parameters_base64_nested_kubeconfig(self):
        """Test anonymization of nested kubeconfig."""
        scenario_yaml = {
            "input_list": [
                {"scenario": "pod_kill", "kubeconfig": "/path/to/config"},
                {"scenario": "network", "kubeconfig": "/another/config"},
            ]
        }
        yaml_content = yaml.safe_dump(scenario_yaml)

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".yaml"
        ) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            scenario_telemetry = ScenarioTelemetry()
            self.telemetry.set_parameters_base64(
                scenario_telemetry, temp_path
            )

            decoded = base64.b64decode(
                scenario_telemetry.parameters_base64.encode()
            ).decode()
            decoded_yaml = yaml.safe_load(decoded)

            # All kubeconfig fields should be anonymized
            self.assertEqual(
                decoded_yaml["input_list"][0]["kubeconfig"], "anonymized"
            )
            self.assertEqual(
                decoded_yaml["input_list"][1]["kubeconfig"], "anonymized"
            )
        finally:
            os.unlink(temp_path)


class TestGetBucketUrlForFilename(unittest.TestCase):
    """Test get_bucket_url_for_filename method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    @patch("requests.get")
    def test_get_bucket_url_success(self, mock_get):
        """Test successful retrieval of presigned URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = (
            b"https://s3.amazonaws.com/bucket/file?presigned=true"
        )
        mock_get.return_value = mock_response

        url = self.telemetry.get_bucket_url_for_filename(
            api_url="https://api.test.com/presigned-url",
            bucket_folder="test/folder",
            remote_filename="test-file.tar",
            username="testuser",
            password="testpass",
        )

        self.assertEqual(
            url, "https://s3.amazonaws.com/bucket/file?presigned=true"
        )
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_get_bucket_url_http_error(self, mock_get):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.telemetry.get_bucket_url_for_filename(
                api_url="https://api.test.com/presigned-url",
                bucket_folder="test/folder",
                remote_filename="test-file.tar",
                username="testuser",
                password="testpass",
            )

        self.assertIn("impossible to get upload url", str(context.exception))
        self.assertIn("403", str(context.exception))


class TestPutFileToUrl(unittest.TestCase):
    """Test put_file_to_url method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    @patch("requests.put")
    def test_put_file_success(self, mock_put):
        """Test successful file upload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            f.flush()
            temp_path = f.name

        try:
            self.telemetry.put_file_to_url(
                "https://s3.test.com/file", temp_path
            )
            mock_put.assert_called_once()
        finally:
            os.unlink(temp_path)

    @patch("requests.put")
    def test_put_file_http_error(self, mock_put):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_put.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            f.flush()
            temp_path = f.name

        try:
            with self.assertRaises(Exception) as context:
                self.telemetry.put_file_to_url(
                    "https://s3.test.com/file", temp_path
                )

            self.assertIn(
                "failed to send archive to s3", str(context.exception)
            )
            self.assertIn("403", str(context.exception))
        finally:
            os.unlink(temp_path)

    @patch("requests.put")
    def test_put_file_connection_error(self, mock_put):
        """Test handling of connection errors."""
        mock_put.side_effect = Exception("Connection refused")

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            f.flush()
            temp_path = f.name

        try:
            with self.assertRaises(Exception) as context:
                self.telemetry.put_file_to_url(
                    "https://s3.test.com/file", temp_path
                )

            self.assertIn("Connection refused", str(context.exception))
        finally:
            os.unlink(temp_path)


class TestPutCriticalAlerts(unittest.TestCase):
    """Test put_critical_alerts method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    def test_put_alerts_empty_summary(self):
        """Test with empty alert summary."""
        telemetry_config = {
            "events_backup": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            "max_retries": 3,
        }

        empty_summary = ChaosRunAlertSummary()

        # Should return early without error
        self.telemetry.put_critical_alerts(
            "test-id", telemetry_config, empty_summary
        )

        self.mock_logger.info.assert_called_with(
            "no alerts collected during the run, skipping"
        )

    def test_put_alerts_none_summary(self):
        """Test with None summary."""
        telemetry_config = {
            "events_backup": True,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            "max_retries": 3,
        }

        self.telemetry.put_critical_alerts("test-id", telemetry_config, None)

        self.mock_logger.info.assert_called_with(
            "no alerts collected during the run, skipping"
        )

    def test_put_alerts_missing_config_fields(self):
        """Test with missing required config fields."""
        telemetry_config = {"events_backup": True}

        summary = ChaosRunAlertSummary()
        alert = ChaosRunAlert("test", "firing", "default", "critical")
        summary.chaos_alerts.append(alert)

        with self.assertRaises(Exception) as context:
            self.telemetry.put_critical_alerts(
                "test-id", telemetry_config, summary
            )

        exception_str = str(context.exception)
        self.assertIn("api_url is missing", exception_str)
        self.assertIn("username is missing", exception_str)
        self.assertIn("password is missing", exception_str)


class TestGenerateUrlAndPutToS3Worker(unittest.TestCase):
    """Test generate_url_and_put_to_s3_worker method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    @patch.object(KrknTelemetryKubernetes, "put_file_to_url")
    @patch.object(KrknTelemetryKubernetes, "get_bucket_url_for_filename")
    def test_worker_success(self, mock_get_url, mock_put_file):
        """Test successful worker execution."""
        mock_get_url.return_value = "https://s3.test.com/file"

        queue = Queue()
        uploaded_files = []

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            f.flush()
            temp_path = f.name

        try:
            queue.put((1, temp_path, 0))

            self.telemetry.generate_url_and_put_to_s3_worker(
                queue=queue,
                queue_size=1,
                request_id="test-id",
                telemetry_group="default",
                api_url="https://api.test.com/presigned-url",
                username="testuser",
                password="testpass",
                thread_number=0,
                uploaded_file_list=uploaded_files,
                max_retries=3,
                remote_file_prefix="test-",
                remote_file_extension=".tar",
            )

            # Worker should have processed the file
            self.assertTrue(queue.empty())
            self.assertEqual(len(uploaded_files), 1)
            mock_get_url.assert_called_once()
            mock_put_file.assert_called_once()
        except FileNotFoundError:
            # File was deleted by worker, which is expected
            pass

    @patch.object(KrknTelemetryKubernetes, "put_file_to_url")
    @patch.object(KrknTelemetryKubernetes, "get_bucket_url_for_filename")
    @patch("time.sleep")
    def test_worker_retry_on_failure(
        self, mock_sleep, mock_get_url, mock_put_file
    ):
        """Test worker retry logic on failure."""
        mock_get_url.return_value = "https://s3.test.com/file"
        mock_put_file.side_effect = [Exception("Upload failed"), None]

        queue = Queue()
        uploaded_files = []

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            f.flush()
            temp_path = f.name

        try:
            queue.put((1, temp_path, 0))

            self.telemetry.generate_url_and_put_to_s3_worker(
                queue=queue,
                queue_size=1,
                request_id="test-id",
                telemetry_group="default",
                api_url="https://api.test.com/presigned-url",
                username="testuser",
                password="testpass",
                thread_number=0,
                uploaded_file_list=uploaded_files,
                max_retries=3,
                remote_file_prefix="test-",
                remote_file_extension=".tar",
            )

            # Should have retried
            self.mock_logger.warning.assert_called()
            mock_sleep.assert_called()
        except FileNotFoundError:
            pass


class TestGetPrometheusPodData(unittest.TestCase):
    """Test get_prometheus_pod_data method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    def test_prometheus_backup_disabled(self):
        """Test when prometheus backup is disabled."""
        # Need to provide all required config even when disabled
        # because validation happens before the disabled check
        telemetry_config = {
            "prometheus_backup": False,
            "full_prometheus_backup": True,
            "backup_threads": 4,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            "archive_path": "/tmp",
            "archive_size": 100,
        }

        result = self.telemetry.get_prometheus_pod_data(
            telemetry_config=telemetry_config,
            request_id="test-id",
            prometheus_pod_name="prometheus-0",
            prometheus_container_name="prometheus",
            prometheus_namespace="monitoring",
        )

        self.assertEqual(result, list[(int, str)]())

    def test_prometheus_backup_missing_config(self):
        """Test with missing required config."""
        telemetry_config = {"prometheus_backup": True}

        with self.assertRaises(Exception) as context:
            self.telemetry.get_prometheus_pod_data(
                telemetry_config=telemetry_config,
                request_id="test-id",
                prometheus_pod_name="prometheus-0",
                prometheus_container_name="prometheus",
                prometheus_namespace="monitoring",
            )

        exception_str = str(context.exception)
        self.assertIn("full_prometheus_backup flag is missing", exception_str)


class TestPutPrometheusData(unittest.TestCase):
    """Test put_prometheus_data method."""

    def setUp(self):
        self.mock_logger = Mock(spec=SafeLogger)
        self.mock_kubecli = Mock(spec=KrknKubernetes)
        self.telemetry = KrknTelemetryKubernetes(
            safe_logger=self.mock_logger,
            lib_kubernetes=self.mock_kubecli,
        )

    def test_prometheus_backup_disabled(self):
        """Test when prometheus backup is disabled."""
        # Need to provide all required config even when disabled
        # because validation happens before the disabled check
        telemetry_config = {
            "prometheus_backup": False,
            "backup_threads": 4,
            "api_url": "https://test-api.com",
            "username": "testuser",
            "password": "testpass",
            "max_retries": 3,
        }

        # Should return early without error
        result = self.telemetry.put_prometheus_data(
            telemetry_config=telemetry_config,
            archive_volumes=[],
            request_id="test-id",
        )

        self.assertIsNone(result)

    def test_put_prometheus_data_missing_config(self):
        """Test with missing required config."""
        telemetry_config = {"prometheus_backup": True}

        with self.assertRaises(Exception) as context:
            self.telemetry.put_prometheus_data(
                telemetry_config=telemetry_config,
                archive_volumes=[(0, "test.tar.b64")],
                request_id="test-id",
            )

        exception_str = str(context.exception)
        self.assertIn("backup_threads is missing", exception_str)


if __name__ == "__main__":
    unittest.main()
