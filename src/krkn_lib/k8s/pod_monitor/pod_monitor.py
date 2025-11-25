import logging
import re
import threading
import time
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
    stop_event=None,
) -> PodsSnapshot:
    w = watch.Watch(return_type=V1Pod)
    deleted_parent_pods = []
    restored_pods = []
    cluster_restored = False
    start_time = time.time()

    # Use a shorter timeout for each iteration to check stop_event
    # more frequently. This allows cancellation to be detected
    # within 5 seconds instead of waiting for max_timeout
    stream_timeout = 5  # Check for cancellation every 5 seconds

    def _check_cancel():
        """Helper function to check if cancellation was requested"""
        if stop_event and stop_event.is_set():
            logging.info(
                "Pod monitoring cancellation detected, stopping watch"
            )
            w.stop()
            return True
        return False

    def _check_timeout():
        """Helper function to check if max_timeout has been exceeded"""
        elapsed = time.time() - start_time
        if elapsed >= max_timeout:
            logging.info(
                f"Pod monitoring reached max timeout of {max_timeout} seconds"
            )
            w.stop()
            return True
        return False

    try:
        while True:
            # Check for cancellation before starting each stream iteration
            if _check_cancel():
                break

            # Check if we've exceeded the max timeout
            if _check_timeout():
                break

            # Calculate remaining timeout for this iteration
            elapsed = time.time() - start_time
            remaining_timeout = max_timeout - elapsed
            if remaining_timeout <= 0:
                break

            # Use the shorter of remaining_timeout or stream_timeout
            current_timeout = min(stream_timeout, remaining_timeout)

            # Stream with shorter timeout to allow frequent cancellation checks
            for event in w.stream(
                monitor_partial, timeout_seconds=current_timeout
            ):
                # Check if stopped at the start of each iteration
                if _check_cancel():
                    break

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
                            # pods as the snapshot.initial_pods set we assume
                            # that the cluster is restored to the initial
                            # condition
                            restored_pods.append(pod.metadata.name)
                            if len(restored_pods) >= len(
                                snapshot.initial_pods
                            ):
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
                            snapshot.pods[pod.metadata.name].name = (
                                pod.metadata.name
                            )
                            snapshot.pods[pod.metadata.name].namespace = (
                                pod.metadata.namespace
                            )
                    # skips events out of the snapshot
                    if pod.metadata.name in snapshot.pods:
                        snapshot.pods[pod.metadata.name].status_changes.append(
                            pod_event
                        )

                    # Check for cancellation after processing each event
                    if _check_cancel():
                        break

                    # this flag is set when all the pods that has been
                    # deleted or not ready have been restored, if True
                    # the monitoring is stopped earlier
                    if cluster_restored:
                        logging.info(
                            "Cluster restored, stopping pod monitoring"
                        )
                        w.stop()
                        break

            # If we break out of the inner for loop, check why and
            # break outer loop if needed
            if _check_cancel() or cluster_restored:
                break

    except Exception as e:
        # If cancellation was requested, this is expected
        if stop_event and stop_event.is_set():
            logging.info("Pod monitoring stopped due to cancellation")
        else:
            logging.error(f"Error during pod monitoring: {e}")
            raise

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
    Monitors all the pods identified by a label selector and collects
    infos about the pods recovery after a kill scenario while the
    scenario is running.

    :param label_selector: the label selector used to filter the pods
        to monitor (must be the same used in `select_pods_by_label`)
    :param max_timeout: the expected time the pods should take to
        recover. If the killed pods are replaced in this time frame,
        but they didn't reach the Ready State, they will be marked as
        unrecovered. If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :param v1_client: kubernetes V1Api client
    :return:
        a future which result (PodsSnapshot) must be gathered to obtain
        the pod infos. Call cancel() on the future to stop monitoring
        early.

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
    stop_event = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=None,
        namespace_pattern=None,
        stop_event=stop_event,
    )
    # Store stop_event on the future so cancel() can trigger it
    future._stop_event = stop_event
    # Override cancel to also set the stop event
    original_cancel = future.cancel

    def cancel_with_stop():
        stop_event.set()
        return original_cancel()

    future.cancel = cancel_with_stop
    return future


def select_and_monitor_by_name_pattern_and_namespace_pattern(
    pod_name_pattern: str,
    namespace_pattern: str,
    max_timeout: int,
    v1_client: CoreV1Api,
):
    """
    Monitors all the pods identified by a pod name regex pattern and a
    namespace regex pattern, that collects infos about the pods
    recovery after a kill scenario while the scenario is running.
    Raises an exception if the regex format is not correct.

    :param pod_name_pattern: a regex representing the pod name pattern
        used to filter the pods to be monitored (must be the same used
        in `select_pods_by_name_pattern_and_namespace_pattern`)
    :param namespace_pattern: a regex representing the namespace
        pattern used to filter the pods to be monitored (must be the
        same used in
        `select_pods_by_name_pattern_and_namespace_pattern`)
    :param max_timeout: the expected time the pods should take to
        recover. If the killed pods are replaced in this time frame,
        but they didn't reach the Ready State, they will be marked as
        unrecovered. If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :param v1_client: kubernetes V1Api client
    :return:
        a future which result (PodsSnapshot) must be gathered to
        obtain the pod infos.

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
    stop_event = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=pod_name_pattern,
        namespace_pattern=namespace_pattern,
        stop_event=stop_event,
    )
    # Store stop_event on the future so cancel() can trigger it
    future._stop_event = stop_event
    # Override cancel to also set the stop event
    original_cancel = future.cancel

    def cancel_with_stop():
        stop_event.set()
        return original_cancel()

    future.cancel = cancel_with_stop
    return future


def select_and_monitor_by_namespace_pattern_and_label(
    namespace_pattern: str,
    label_selector: str,
    v1_client: CoreV1Api,
    max_timeout=30,
):
    """
    Monitors all the pods identified by a namespace regex pattern and
    a pod label selector, that collects infos about the pods recovery
    after a kill scenario while the scenario is running. Raises an
    exception if the regex format is not correct.

    :param label_selector: the label selector used to filter the pods
        to monitor (must be the same used in `select_pods_by_label`)
    :param v1_client: kubernetes V1Api client
    :param namespace_pattern: a regex representing the namespace
        pattern used to filter the pods to be monitored (must be the
        same used in
        `select_pods_by_name_pattern_and_namespace_pattern`)
    :param max_timeout: the expected time the pods should take to
        recover. If the killed pods are replaced in this time frame,
        but they didn't reach the Ready State, they will be marked as
        unrecovered. If during the time frame the pods are not replaced
        at all the error field of the PodsStatus structure will be
        valorized with an exception.
    :return:
        a future which result (PodsSnapshot) must be gathered to obtain
        the pod infos.

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
    stop_event = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _monitor_pods,
        monitor_partial,
        snapshot,
        max_timeout,
        name_pattern=None,
        namespace_pattern=namespace_pattern,
        stop_event=stop_event,
    )
    # Store stop_event on the future so cancel() can trigger it
    future._stop_event = stop_event
    # Override cancel to also set the stop event
    original_cancel = future.cancel

    def cancel_with_stop():
        stop_event.set()
        return original_cancel()

    future.cancel = cancel_with_stop
    return future
