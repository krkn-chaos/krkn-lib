"""
Kubernetes object helper for unified resource retrieval.

Provides a central place for API mappings and shared logic for fetching Kubernetes objects,
with pagination support for large-scale deployments via the continue token mechanism.
Supports watching CRD objects for real-time event monitoring.
"""

import logging
from typing import Optional, Dict, List, Callable
from kubernetes import watch as k8s_watch

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

    # Mapping of namespaced resource kind to list method
    NAMESPACED_LIST_API_MAP = {
        'pod': ('cli', 'list_namespaced_pod'),
        'deployment': ('apps_api', 'list_namespaced_deployment'),
        'statefulset': ('apps_api', 'list_namespaced_stateful_set'),
        'daemonset': ('apps_api', 'list_namespaced_daemon_set'),
        'replicaset': ('apps_api', 'list_namespaced_replica_set'),
        'service': ('cli', 'list_namespaced_service'),
        'persistentvolumeclaim': ('cli', 'list_namespaced_persistent_volume_claim'),
        'job': ('batch_cli', 'list_namespaced_job'),
        'cronjob': ('batch_cli', 'list_namespaced_cron_job'),
    }

    # Mapping of cluster-scoped resources to (api_client_attr, method_name)
    CLUSTER_SCOPED_API_MAP = {
        'node': ('cli', 'read_node'),
        'persistentvolume': ('cli', 'read_persistent_volume'),
    }

    # Mapping of cluster-scoped resource kind to list method
    CLUSTER_SCOPED_LIST_API_MAP = {
        'node': ('cli', 'list_node'),
        'persistentvolume': ('cli', 'list_persistent_volume'),
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

    def list_objects_by_kind(
        self,
        kind: str,
        namespace: str = None,
        label_selector: str = None,
        limit: int = None
    ) -> List[Dict]:
        """
        List all Kubernetes objects of a specific kind with pagination support.

        Handles large-scale deployments by using the continue token mechanism to
        paginate through results when they exceed the limit. Uses krkn's list_continue_helper
        for consistent pagination behavior.

        Supported resource kinds:
        - Namespaced: Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, Service,
                      PersistentVolumeClaim, Job, CronJob
        - Cluster-scoped: Node, PersistentVolume

        :param kind: Kubernetes resource kind (e.g., "Pod", "Deployment", "Node")
        :param namespace: Namespace (required for namespaced resources)
        :param label_selector: Label selector for filtering (optional)
        :param limit: Max items per API request (optional, uses krkn default if not set)
        :return: List of objects as dictionaries
        :raises ValueError: If namespace required but not provided
        """
        kind_lower = kind.lower()

        if kind_lower not in self.NAMESPACED_LIST_API_MAP and kind_lower not in self.CLUSTER_SCOPED_LIST_API_MAP:
            logger.warning(f"Unsupported resource kind '{kind}' in list_objects_by_kind")
            return []

        # Set default limit from krkn if available
        if limit is None and hasattr(self.krkn, 'request_chunk_size'):
            limit = self.krkn.request_chunk_size

        if kind_lower in self.NAMESPACED_LIST_API_MAP:
            if namespace is None:
                raise ValueError(f"Namespace is required for namespaced resource type '{kind}'")
            api_client_attr, method_name = self.NAMESPACED_LIST_API_MAP[kind_lower]
            api_client = getattr(self.krkn, api_client_attr)
            method = getattr(api_client, method_name)

            # Build kwargs
            kwargs = {'pretty': True}
            if label_selector:
                kwargs['label_selector'] = label_selector
            if limit:
                kwargs['limit'] = limit

            # Use krkn's list_continue_helper for pagination
            response_list = self.krkn.list_continue_helper(method, namespace, **kwargs)
        else:  # cluster-scoped
            api_client_attr, method_name = self.CLUSTER_SCOPED_LIST_API_MAP[kind_lower]
            api_client = getattr(self.krkn, api_client_attr)
            method = getattr(api_client, method_name)

            # Build kwargs
            kwargs = {'pretty': True}
            if label_selector:
                kwargs['label_selector'] = label_selector
            if limit:
                kwargs['limit'] = limit

            # Use krkn's list_continue_helper for pagination
            response_list = self.krkn.list_continue_helper(method, **kwargs)

        # Flatten all items from all response pages
        all_objects = []
        for response in response_list:
            if response.items:
                for item in response.items:
                    all_objects.append(self.krkn.api_client.sanitize_for_serialization(item))

        return all_objects

    def watch_crd_objects(
        self,
        group: str,
        version: str,
        plural: str,
        namespace: str = None,
        name: str = None,
        label_selector: str = None,
        field_selector: str = None,
        timeout_seconds: int = None,
        event_handler: Callable[[str, Dict], None] = None
    ) -> Optional[List[Dict]]:
        """
        Watch CRD objects for real-time events (added, modified, deleted).

        Can be used to monitor custom resources as they change. Yields events
        until timeout or explicitly stopped.

        :param group: API group of the CRD (e.g., "example.com")
        :param version: API version (e.g., "v1", "v1alpha1")
        :param plural: Plural name of the custom resource (e.g., "widgets")
        :param namespace: Namespace for namespaced CRDs (optional)
        :param name: Watch specific resource by name (optional)
        :param label_selector: Watch resources matching labels (optional)
        :param field_selector: Watch resources matching fields (optional)
        :param timeout_seconds: Watch timeout in seconds (optional)
        :param event_handler: Callback function(event_type, object) for each event (optional)
        :return: List of all objects seen during watch (or None if handler is provided)

        Example:
            def handle_event(event_type, obj):
                print(f"{event_type}: {obj['metadata']['name']}")

            helpers.watch_crd_objects(
                "example.com", "v1", "widgets",
                namespace="default",
                event_handler=handle_event,
                timeout_seconds=60
            )
        """
        try:
            watcher = k8s_watch.Watch()
            watched_objects = [] if event_handler is None else None

            # Build kwargs for the watch call
            kwargs = {}
            if namespace:
                kwargs['namespace'] = namespace
            if label_selector:
                kwargs['label_selector'] = label_selector
            if field_selector:
                kwargs['field_selector'] = field_selector
            if timeout_seconds:
                kwargs['timeout_seconds'] = timeout_seconds

            # Get the dynamic client for CRDs
            if not hasattr(self.krkn, 'dyn_client'):
                logger.error("Dynamic client not available in krkn instance")
                return None

            dyn_client = self.krkn.dyn_client
            api = dyn_client.resources.get(group=group, api_version=version, kind=plural)

            # Build arguments for watch stream
            stream_args = []
            stream_kwargs = kwargs.copy()

            if namespace:
                stream_args = [namespace]
            if name:
                stream_kwargs['name'] = name

            # Stream the watch events
            for event in watcher.stream(api.get, *stream_args, **stream_kwargs):
                event_type = event['type']
                obj_dict = self.krkn.api_client.sanitize_for_serialization(event['object'])

                if event_handler:
                    # Use provided handler
                    try:
                        event_handler(event_type, obj_dict)
                    except Exception as e:
                        logger.error(f"Error in event handler: {e}")
                else:
                    # Collect objects if no handler provided
                    if watched_objects is not None:
                        watched_objects.append({
                            'type': event_type,
                            'object': obj_dict
                        })

            watcher.stop()
            return watched_objects

        except AttributeError as e:
            logger.error(f"Failed to get dynamic client: {e}")
            raise
        except Exception as e:
            logger.error(f"Error watching CRD objects {group}/{version}/{plural}: {e}")
            raise

