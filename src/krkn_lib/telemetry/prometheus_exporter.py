"""
Prometheus API-based metrics exporter for time-window telemetry collection.
Provides faster alternative to filesystem-based backup by querying only
relevant time windows via Prometheus HTTP API.
"""

import json
import logging  
import os
import tarfile
import tempfile
import time
from datetime import datetime
from typing import Optional

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus  


class PrometheusExporter:
    """
    Exports Prometheus metrics via HTTP API for specific time windows.
    Significantly faster than filesystem backup for targeted time ranges.
    Uses existing KrknPrometheus class for Prometheus connectivity.
    """

    def __init__(
        self,
        prometheus_url: str,
        bearer_token: Optional[str] = None,
    ):
        """
        Initialize Prometheus API exporter.

        :param prometheus_url: Base URL of Prometheus server
            (e.g., 'https://prometheus-k8s.openshift-monitoring.svc:9091')
        :param bearer_token: Optional bearer token for authentication
        """
        self.prometheus_url = prometheus_url
        self.prom_client = KrknPrometheus(prometheus_url, bearer_token)

    def test_connection(self) -> bool:
        """
        Test connection to Prometheus API.

        :return: True if connection successful, False otherwise
        """
        try:
            # Try a simple query to test connection
            self.prom_client.process_query("up")
            return True
        except Exception as e:  
            logging.debug(f"Prometheus API connection test failed: {str(e)}")
            return False

    def export_metrics_snapshot(
        self,
        start_timestamp: int,
        end_timestamp: int,
        output_path: str,
        archive_name: str,
    ) -> Optional[str]:
        """
        Export metrics for a specific time window and create tar.gz archive.

        :param start_timestamp: Start time (Unix timestamp in seconds)
        :param end_timestamp: End time (Unix timestamp in seconds)
        :param output_path: Directory where archive will be created
        :param archive_name: Base name for the archive (without extension)
        :return: Full path to created archive, or None on failure
        """
        try:
            logging.info(
                f"Exporting Prometheus metrics from {start_timestamp} to {end_timestamp} "
                f"using API (time window: {(end_timestamp - start_timestamp) / 60:.1f} minutes)"
            )

            # Convert Unix timestamps to datetime objects
            start_time = datetime.fromtimestamp(start_timestamp)
            end_time = datetime.fromtimestamp(end_timestamp)

            # Calculate appropriate step size (1 point per minute for efficiency)
            duration = end_timestamp - start_timestamp
            step = max(60, duration // 1000)  # At least 60s, max 1000 points

            logging.info("Querying Prometheus API for all metrics in time range...")

            # Query all metrics using regex pattern
            metrics_data = self.prom_client.process_prom_query_in_range(
                query='{__name__=~".+"}',
                start_time=start_time,
                end_time=end_time,
                granularity=step,
            )

            if not metrics_data:
                logging.warning("No metrics data returned from Prometheus API")  # ✅ ADDED
                return None

            # Create temporary directory for archive contents
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write metrics data
                metrics_file = os.path.join(temp_dir, "metrics.json")
                with open(metrics_file, "w") as f:
                    json.dump(metrics_data, f, indent=2)

                # Write metadata
                metadata = {
                    "start_timestamp": start_timestamp,
                    "end_timestamp": end_timestamp,
                    "duration_seconds": end_timestamp - start_timestamp,
                    "collection_method": "prometheus_api",
                    "prometheus_url": self.prometheus_url,
                    "export_timestamp": int(time.time()),
                }
                metadata_file = os.path.join(temp_dir, "metadata.json")
                with open(metadata_file, "w") as f:
                    json.dump(metadata, f, indent=2)

                # Create tar.gz archive
                archive_path = os.path.join(output_path, f"{archive_name}.tar.gz")
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(
                        metrics_file,
                        arcname="metrics.json",
                    )
                    tar.add(
                        metadata_file,
                        arcname="metadata.json",
                    )

                logging.info(
                    f"Successfully exported Prometheus metrics to {archive_path} "
                    f"({os.path.getsize(archive_path) / (1024 * 1024):.2f} MB)"
                )
                return archive_path

        except Exception as e:  
            logging.error(f"Failed to export Prometheus metrics via API: {str(e)}")
            return None
