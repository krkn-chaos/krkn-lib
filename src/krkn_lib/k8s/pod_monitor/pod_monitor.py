import re
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kubernetes import watch
from kubernetes.client import V1Pod, CoreV1Api

from krkn_lib.models.pod_monitor.models import (
    PodsSnapshot,
    MonitoredPod,
    PodEvent,
    PodStatus,
)


def _select_pods(
    select_partial: partial,
    namespace_pattern: str = None,
    name_pattern: str = None,
):
    initial_pods = select_partial()
    snapshot = PodsSnapshot()
    snapshot.resource_version = initial_pods.metadata.resource_version

    for pod in initial_pods.items:
        match_name = True
        match_namespace = True
        if namespace_pattern:
            match = re.match(namespace_pattern, pod.metadata.namespace)
            match_namespace = match is not None
        if name_pattern:
            match = re.match(name_pattern, pod.metadata.name)
            match_name = match is not None
        if match_name and match_namespace:
            mon_pod = MonitoredPod()
            snapshot.initial_pods.append(pod.metadata.name)
            mon_pod.name = pod.metadata.name
            mon_pod.namespace = pod.metadata.namespace
            snapshot.pods[mon_pod.name] = mon_pod
    return snapshot


def _monitor_pods(
    monitor_partial: partial,
    snapshot: PodsSnapshot,
    max_timeout: int,
    name_pattern: str = None,
    namespace_pattern: str = None,
) -> PodsSnapshot:
    w = watch.Watch(return_type=V1Pod)
    deleted_parent_pods = []
    restored_pods = []
    cluster_restored = False
    for event in w.stream(monitor_partial, timeout_seconds=max_timeout):
        match_name = True
        match_namespace = True
        event_type = event["type"]
        pod = event["object"]

        if namespace_pattern:
            match = re.match(namespace_pattern, pod.metadata.namespace)
            match_namespace = match is not None
        if name_pattern:
            match = re.match(name_pattern, pod.metadata.name)
            match_name = match is not None

        if match_name and match_namespace:
            pod_event = PodEvent()
            if event_type == "MODIFIED":
                if pod.metadata.deletion_timestamp is not None:
                    pod_event.status = PodStatus.DELETION_SCHEDULED
                    deleted_parent_pods.append(pod.metadata.name)
                elif _is_pod_ready(pod):
                    pod_event.status = PodStatus.READY
                    # if there are at least the same number of ready
                    # pods as the snapshot.initial_pods set we assume that
                    # the cluster is restored to the initial condition
                    restored_pods.append(pod.metadata.name)
                    if len(restored_pods) >= len(snapshot.initial_pods):
                        cluster_restored = True
                else:
                    pod_event.status = PodStatus.NOT_READY

            elif event_type == "DELETED":
                pod_event.status = PodStatus.DELETED
            elif event_type == "ADDED":
                pod_event.status = PodStatus.ADDED

            if pod_event.status == PodStatus.ADDED:
                snapshot.added_pods.append(pod.metadata.name)
                # in case a pod is respawn with the same name
                # the dictionary must not be reinitialized
                if pod.metadata.name not in snapshot.pods:
                    snapshot.pods[pod.metadata.name] = MonitoredPod()
                    snapshot.pods[pod.metadata.name].name = pod.metadata.name
                    snapshot.pods[pod.metadata.name].namespace = (
                        pod.metadata.namespace
                    )
            # skips events out of the snapshot
            if pod.metadata.name in snapshot.pods:
                snapshot.pods[pod.metadata.name].status_changes.append(
                    pod_event
                )
            # this flag is set when all the pods
            # that has been deleted or not ready
            # have been restored, if True the
            # monitoring is stopeed earlier
            if cluster_restored:
                w.stop()

    return snapshot


def _is_pod_ready(pod: V1Pod) -> bool:
    if not pod.status.container_statuses:
        return False
    for status in pod.status.container_statuses:
        if not status.ready:
            return False
    return True


def _is_pod_terminating(pod: V1Pod) -> bool:
    if pod.metadata.deletion_timestamp is not None:
        return True
    return False


def select_and_monitor_by_label(
    label_selector: str,
    max_timeout: int,
    v1_client: CoreV1Api,
) -> Future:
    """
    Monitors all the pods identified
    by a label selector and collects infos about the
    pods recovery after a kill scenario while the scenario is running.

    :param label_selector: the label selector used
        to filter the pods to monitor (must be the
        same used in `select_pods_by_label`)
    :param max_timeout: the expected time the pods should take
        to recover. If the killed pods are replaced in this time frame,
        but they didn't reach the Ready State, they will be marked as
        unrecovered. If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :param v1_client: kubernetes V1Api client
    :return:
        a future which result (PodsSnapshot) must be
        gathered to obtain the pod infos.

    """
    select_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        label_selector=label_selector,
        field_selector="status.phase=Running",
    )
    snapshot = _select_pods(select_partial)
    monitor_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        resource_version=snapshot.resource_version,
        label_selector=label_selector,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=None,
        namespace_pattern=None,
    )
    return future


def select_and_monitor_by_name_pattern_and_namespace_pattern(
    pod_name_pattern: str,
    namespace_pattern: str,
    max_timeout: int,
    v1_client: CoreV1Api,
):
    """
    Monitors all the pods identified by a pod name regex pattern
    and a namespace regex pattern, that collects infos about the
    pods recovery after a kill scenario while the scenario is running.
    Raises an exception if the regex format is not correct.

    :param pod_name_pattern: a regex representing the
        pod name pattern used to filter the pods to be monitored
        (must be the same used in
        `select_pods_by_name_pattern_and_namespace_pattern`)
    :param namespace_pattern: a regex representing the namespace
        pattern used to filter the pods to be monitored
        (must be the same used in
        `select_pods_by_name_pattern_and_namespace_pattern`)
    :param max_timeout: the expected time the pods should take to
        recover. If the killed pods are replaced in this time frame,
        but they didn't reach the Ready State, they will be marked as
        unrecovered. If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :param v1_client: kubernetes V1Api client
    :return:
        a future which result (PodsSnapshot) must be
        gathered to obtain the pod infos.

    """
    try:
        re.compile(pod_name_pattern)
    except re.error as e:
        raise Exception(f"invalid pod name pattern regex: {e}")

    try:
        re.compile(namespace_pattern)
    except re.error as e:
        raise Exception(f"invalid pod namespace regex: {e}")

    select_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        field_selector="status.phase=Running",
    )
    snapshot = _select_pods(
        select_partial,
        name_pattern=pod_name_pattern,
        namespace_pattern=namespace_pattern,
    )
    monitor_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        resource_version=snapshot.resource_version,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=pod_name_pattern,
        namespace_pattern=namespace_pattern,
    )
    return future


def select_and_monitor_by_namespace_pattern_and_label(
    namespace_pattern: str,
    label_selector: str,
    v1_client: CoreV1Api,
    max_timeout=30,
):
    """
    Monitors all the pods identified
    by a namespace regex pattern
    and a pod label selector, that collects infos about the
    pods recovery after a kill scenario while the scenario is running.
    Raises an exception if the regex format is not correct.

    :param label_selector: the label selector used to filter
        the pods to monitor (must be the same used in
        `select_pods_by_label`)
    :param v1_client: kubernetes V1Api client
    :param namespace_pattern: a regex representing the namespace
        pattern used to filter the pods to be monitored (must be
        the same used
        in `select_pods_by_name_pattern_and_namespace_pattern`)
    :param max_timeout: the expected time the pods should take to recover.
        If the killed pods are replaced in this time frame, but they
        didn't reach the Ready State, they will be marked as unrecovered.
        If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :return:
        a future which result (PodsSnapshot) must be
        gathered to obtain the pod infos.

    """
    try:
        re.compile(namespace_pattern)
    except re.error as e:
        raise Exception(f"invalid pod namespace regex: {e}")

    select_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        label_selector=label_selector,
        field_selector="status.phase=Running",
    )
    snapshot = _select_pods(
        select_partial,
        namespace_pattern=namespace_pattern,
    )
    monitor_partial = partial(
        v1_client.list_pod_for_all_namespaces,
        resource_version=snapshot.resource_version,
        label_selector=label_selector,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=None,
        namespace_pattern=namespace_pattern,
    )
    return future
