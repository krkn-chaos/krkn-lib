import logging
import re
import threading
import time
import traceback
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kubernetes import watch
from kubernetes.client import CoreV1Api, V1Pod
from urllib3.exceptions import ProtocolError

from krkn_lib.models.pod_monitor.models import (
    MonitoredPod,
    PodEvent,
    PodsSnapshot,
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
    max_retries: int = 3,
    stop_event: threading.Event = None,
) -> PodsSnapshot:
    """
    Monitor pods with automatic retry on watch stream disconnection.

    :param monitor_partial: Partial function for monitoring pods
        (without resource_version)
    :param snapshot: Snapshot to populate with pod events
    :param max_timeout: Maximum time to monitor (seconds)
    :param name_pattern: Regex pattern for pod names
    :param namespace_pattern: Regex pattern for namespaces
    :param max_retries: Maximum number of retries on connection error
        (default: 3)
    :param stop_event: Optional threading.Event to signal early termination
    :return: PodsSnapshot with collected pod events
    """

    if stop_event is not None and not isinstance(stop_event, threading.Event):
        raise TypeError(
            "stop_event must be a threading.Event instance or None"
        )

    start_time = time.time()
    retry_count = 0
    deleted_parent_pods = []
    restored_pods = []
    cluster_restored = False

    while retry_count <= max_retries:
        # Check if stop event is set before each iteration
        if stop_event and stop_event.is_set():
            return snapshot

        # Calculate remaining timeout at start of each iteration
        elapsed = time.time() - start_time
        remain_timeout = max(1, int(max_timeout - elapsed))
        if remain_timeout <= 0:
            logging.info("Maximum timeout reached, stopping monitoring")
            break

        try:
            # Log reconnection info if retrying
            if retry_count > 0:
                logging.info("remain timeout " + str(remain_timeout))
                logging.info(
                    "Reconnecting watch stream"
                    f"(attempt {retry_count}/{max_retries}),"
                    f"remaining timeout: {remain_timeout}s"
                )

            w = watch.Watch(return_type=V1Pod)

            # Use short watch intervals when stop_event is provided
            # for responsive interrupts
            if stop_event:
                watch_timeout = min(5, remain_timeout)
            else:
                watch_timeout = remain_timeout

            # Build watch call with current resource_version
            # to avoid duplicate events
            current_rv = snapshot.resource_version
            for e in w.stream(
                monitor_partial,
                resource_version=current_rv,
                timeout_seconds=watch_timeout,
            ):
                match_name = True
                match_namespace = True
                event_type = e["type"]
                pod = e["object"]

                if namespace_pattern:
                    match = re.match(namespace_pattern, pod.metadata.namespace)
                    match_namespace = match is not None
                if name_pattern:
                    match = re.match(name_pattern, pod.metadata.name)
                    match_name = match is not None

                # Update resource_version from each event
                # to avoid duplicates on watch restart
                if pod.metadata.resource_version:
                    snapshot.resource_version = pod.metadata.resource_version

                if match_name and match_namespace:
                    pod_event = PodEvent()
                    pod_name = pod.metadata.name
                    if event_type == "MODIFIED":
                        if pod.metadata.deletion_timestamp is not None:
                            pod_event.status = PodStatus.DELETION_SCHEDULED
                            if pod_name not in deleted_parent_pods:
                                deleted_parent_pods.append(pod_name)
                        elif _is_pod_ready(pod):
                            pod_event.status = PodStatus.READY
                            # if there are at least the same number of ready
                            # pods as the snapshot.initial_pods set we assume
                            # the cluster is restored to the initial condition
                            if pod_name not in restored_pods:
                                restored_pods.append(pod_name)
                            inital_pod_len = len(snapshot.initial_pods)
                            if len(restored_pods) >= inital_pod_len:
                                cluster_restored = True
                        else:
                            pod_event.status = PodStatus.NOT_READY

                    elif event_type == "DELETED":
                        pod_event.status = PodStatus.DELETED
                    elif event_type == "ADDED":
                        pod_event.status = PodStatus.ADDED

                    if pod_event.status == PodStatus.ADDED:

                        if pod_name not in snapshot.added_pods:
                            snapshot.added_pods.append(pod_name)
                        # in case a pod is respawn with the same name
                        # the dictionary must not be reinitialized
                        if pod_name not in snapshot.pods:
                            snapshot.pods[pod_name] = MonitoredPod()
                            snapshot.pods[pod_name].name = pod_name
                            snapshot.pods[pod_name].namespace = (
                                pod.metadata.namespace
                            )
                    # skips events out of the snapshot
                    if pod_name in snapshot.pods:
                        snapshot.pods[pod_name].status_changes.append(
                            pod_event
                        )
                    # this flag is set when all the pods
                    # that has been deleted or not ready
                    # have been restored, if True the
                    # monitoring is stopped earlier
                    # Check if stop event is set during monitoring
                    if stop_event and stop_event.is_set():
                        w.stop()
                        return snapshot

                    if cluster_restored:
                        logging.info("Cluster restored, stopping monitoring")
                        w.stop()
                        return snapshot

            # If we exit the for loop normally (watch timeout reached)
            # With short intervals for stop_event, continue looping
            # until max_timeout
            if stop_event:
                elapsed = time.time() - start_time
                if elapsed < max_timeout:
                    continue  # Continue with next short interval
            logging.info("Watch stream completed normally")
            break

        except ProtocolError as e:

            if retry_count > max_retries:
                logging.warning(
                    f"Watch stream connection broken after "
                    f"{max_retries} retries. ProtocolError: {e}. "
                    "Returning snapshot with data collected so far."
                )
                break

            # Log retry attempt
            logging.info(
                f"Watch stream connection broken (ProtocolError): {e}. "
                f"Retry {retry_count}/{max_retries} in progress..."
            )
            backoff_time = 1

            # Check if we have time for backoff
            elapsed = time.time() - start_time
            if elapsed + backoff_time >= max_timeout:
                logging.info(
                    "Not enough time remaining for backoff, "
                    "returning snapshot with data collected."
                )
                break

            logging.debug(f"Waiting {backoff_time}s before retry...")
            time.sleep(backoff_time)

        except Exception as e:
            logging.error("Error in monitor pods: " + str(e))
            logging.error("Stack trace:\n%s", traceback.format_exc())
            raise Exception(e)

        retry_count += 1

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
    stop_event: threading.Event = None,
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
    :param stop_event: Optional threading.Event to signal early termination
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
        stop_event=stop_event,
    )
    return future


def select_and_monitor_by_name_pattern_and_namespace_pattern(
    pod_name_pattern: str,
    namespace_pattern: str,
    max_timeout: int,
    v1_client: CoreV1Api,
    stop_event: threading.Event = None,
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
    :param stop_event: Optional threading.Event to signal early termination
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
    )
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
    return future


def select_and_monitor_by_namespace_pattern_and_label(
    namespace_pattern: str,
    label_selector: str,
    v1_client: CoreV1Api,
    max_timeout=30,
    stop_event: threading.Event = None,
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
    :param stop_event: Optional threading.Event to signal early termination
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
        stop_event=stop_event,
    )
    return future
