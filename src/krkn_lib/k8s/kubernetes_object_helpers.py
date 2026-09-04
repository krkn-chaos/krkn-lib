"""
Kubernetes object helper for unified resource retrieval.

Provides a central place for API mappings and shared logic for fetching Kubernetes objects.
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class KubernetesObjectHelpers:
    """Helper class for retrieving Kubernetes objects of specific types."""

    # Mapping of namespaced resource kind to (api_client_attr, method_name)
    NAMESPACED_API_MAP = {
        'pod': ('cli', 'read_namespaced_pod'),
        'deployment': ('apps_api', 'read_namespaced_deployment'),
        'statefulset': ('apps_api', 'read_namespaced_stateful_set'),
        'daemonset': ('apps_api', 'read_namespaced_daemon_set'),
        'replicaset': ('apps_api', 'read_namespaced_replica_set'),
        'service': ('cli', 'read_namespaced_service'),
        'persistentvolumeclaim': ('cli', 'read_namespaced_persistent_volume_claim'),
        'job': ('batch_cli', 'read_namespaced_job'),
        'cronjob': ('batch_cli', 'read_namespaced_cron_job'),
    }

    # Mapping of cluster-scoped resources to (api_client_attr, method_name)
    CLUSTER_SCOPED_API_MAP = {
        'node': ('cli', 'read_node'),
        'persistentvolume': ('cli', 'read_persistent_volume'),
    }

    def __init__(self, krkn):
        """Initialize with a KrknKubernetes instance."""
        self.krkn = krkn

    def get_object_by_name(
        self,
        kind: str,
        name: str,
        namespace: str = None
    ) -> Optional[Dict]:
        """
        Get a Kubernetes object by kind and name, returning it as a dictionary.

        This is a universal helper that works with any supported Kubernetes resource type,
        handling both namespaced and cluster-scoped resources automatically.

        Supported resource kinds:
        - Namespaced: Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, Service,
                      PersistentVolumeClaim, Job, CronJob
        - Cluster-scoped: Node, PersistentVolume

        :param kind: Kubernetes resource kind (e.g., "Pod", "Deployment", "Node")
        :param name: Name of the object
        :param namespace: Namespace (required for namespaced resources, ignored for cluster-scoped)
        :return: Object as a dictionary, or None if not found or unsupported kind
        :raises ApiException: If the API call fails (e.g., object not found)
        """
        kind_lower = kind.lower()

        if kind_lower not in self.NAMESPACED_API_MAP and kind_lower not in self.CLUSTER_SCOPED_API_MAP:
            logger.warning(f"Unsupported resource kind '{kind}' in get_object_by_name")
            return None

        if kind_lower in self.NAMESPACED_API_MAP:
            if namespace is None:
                raise ValueError(f"Namespace is required for namespaced resource type '{kind}'")
            api_client_attr, method_name = self.NAMESPACED_API_MAP[kind_lower]
            api_client = getattr(self.krkn, api_client_attr)
            method = getattr(api_client, method_name)
            obj = method(name, namespace)
            return self.krkn.api_client.sanitize_for_serialization(obj)
        else:  # cluster-scoped
            api_client_attr, method_name = self.CLUSTER_SCOPED_API_MAP[kind_lower]
            api_client = getattr(self.krkn, api_client_attr)
            method = getattr(api_client, method_name)
            obj = method(name)
            return self.krkn.api_client.sanitize_for_serialization(obj)

