import logging
import re
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
    expected_ready_pods: int = None,
) -> PodsSnapshot:
    """
    Monitor pods with automatic retry on watch stream disconnection.

    :param monitor_partial: Partial function for monitoring pods
    :param snapshot: Snapshot to populate with pod events
    :param max_timeout: Maximum time to monitor (seconds)
    :param name_pattern: Regex pattern for pod names
    :param namespace_pattern: Regex pattern for namespaces
    :param max_retries: Maximum number of retries on connection error
        (default: 3)
    :param expected_ready_pods: Number of ready pods to wait for before
        stopping monitoring. If None, defaults to len(snapshot.initial_pods)
    :return: PodsSnapshot with collected pod events
    """

    start_time = time.time()
    retry_count = 0
    deleted_parent_pods = []
    restored_pods = []
    cluster_restored = False

    # Set the target number of ready pods
    if expected_ready_pods is None:
        expected_ready_pods = len(snapshot.initial_pods)

    logging.info(
        f"Monitoring pods - waiting for {expected_ready_pods} "
        f"ready pods (initial pods: {len(snapshot.initial_pods)})"
    )

    while retry_count <= max_retries:
        try:
            # Calculate remaining timeout if retrying
            if retry_count > 0:
                elapsed = time.time() - start_time
                remain_timeout = max(1, int(max_timeout - elapsed))
                logging.info("remain timeout " + str(remain_timeout))
                if remain_timeout <= 0:
                    logging.info(
                        "Maximum timeout reached, stopping monitoring"
                    )
                    break
                logging.info(
                    "Reconnecting watch stream"
                    f"(attempt {retry_count}/{max_retries}),"
                    f"remaining timeout: {remain_timeout}s"
                )
            else:
                remain_timeout = max_timeout

            w = watch.Watch(return_type=V1Pod)

            for e in w.stream(monitor_partial, timeout_seconds=remain_timeout):
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

                if match_name and match_namespace:
                    # Capture client timestamp immediately when event
                    # is received for consistency
                    client_timestamp = time.time()
                    pod_name = pod.metadata.name

                    # Determine server timestamp and status based on
                    # event type
                    server_timestamp = None
                    status = PodStatus.UNDEFINED

                    if event_type == "MODIFIED":
                        if pod.metadata.deletion_timestamp is not None:
                            status = PodStatus.DELETION_SCHEDULED
                            server_timestamp = (
                                _get_pod_deletion_timestamp(pod)
                            )
                            if pod_name not in deleted_parent_pods:
                                deleted_parent_pods.append(pod_name)
                        elif _is_pod_ready(pod):
                            status = PodStatus.READY
                            server_timestamp = (
                                _get_pod_ready_timestamp(pod)
                            )
                            # Track ready pods
                            if pod_name not in restored_pods:
                                restored_pods.append(pod_name)

                            # Check if expected number of pods are ready
                            ready_count = len(restored_pods)

                            if ready_count >= expected_ready_pods:
                                cluster_restored = True
                                logging.info(
                                    f"Expected ready pods reached: "
                                    f"{ready_count}/{expected_ready_pods}"
                                )
                        else:
                            status = PodStatus.NOT_READY
                            # For NOT_READY, use client timestamp
                            # since there's no specific server timestamp
                            server_timestamp = client_timestamp

                    elif event_type == "DELETED":
                        status = PodStatus.DELETED
                        if pod.metadata.deletion_timestamp:
                            server_timestamp = (
                                _get_pod_deletion_timestamp(pod)
                            )
                    elif event_type == "ADDED":
                        status = PodStatus.ADDED
                        server_timestamp = (
                            _get_pod_creation_timestamp(pod)
                        )

                    # Create PodEvent with both timestamps set at once
                    pod_event = PodEvent(
                        timestamp=client_timestamp,
                        server_timestamp=server_timestamp
                    )
                    pod_event.status = status

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
                        # Skip duplicate READY events to ensure consistent
                        # timing measurements
                        if pod_event.status == PodStatus.READY:
                            already_ready = any(
                                event.status == PodStatus.READY
                                for event in snapshot.pods[
                                    pod_name
                                ].status_changes
                            )
                            if already_ready:
                                # Skip duplicate READY event, but still
                                # check cluster_restored below
                                if cluster_restored:
                                    logging.info(
                                        "Cluster restored, stopping monitoring"
                                    )
                                    w.stop()
                                    return snapshot
                                continue
                        snapshot.pods[pod_name].status_changes.append(
                            pod_event
                        )

                    # Check if cluster is restored and stop monitoring
                    # early. This check happens after processing the event
                    # to ensure we capture the final READY state.
                    if cluster_restored:
                        logging.info(
                            "Cluster restored, stopping monitoring"
                        )
                        w.stop()
                        return snapshot

            # If we exit the loop normally (timeout reached), we're done
            logging.info("Watch stream completed normally")
            w.stop()
            return snapshot

        except ProtocolError as e:

            if retry_count > max_retries:
                logging.warning(
                    f"Watch stream connection broken after {max_retries}"
                    f"retries. ProtocolError: {e}. Returning snapshot "
                    "with data collected so far."
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


def _get_pod_ready_timestamp(pod: V1Pod) -> float:
    """
    Extract the server-side timestamp when the pod became ready.
    Uses the lastTransitionTime from the Ready condition in pod status.

    :param pod: V1Pod object
    :return: Unix timestamp (float) when pod became ready,
        or current time if not available
    """
    if pod.status.conditions:
        for condition in pod.status.conditions:
            if condition.type == "Ready" and condition.status == "True":
                if condition.last_transition_time:
                    # Convert Kubernetes datetime to Unix timestamp
                    # in seconds
                    ts = condition.last_transition_time.timestamp()
                    logging.debug(
                        f"Pod {pod.metadata.name} ready timestamp: "
                        f"{ts} (from condition)"
                    )
                    return ts
    # Fallback to current time if not available
    fallback = time.time()
    logging.debug(
        f"Pod {pod.metadata.name} ready timestamp fallback: " f"{fallback}"
    )
    return fallback


def _get_pod_deletion_timestamp(pod: V1Pod) -> float:
    """
    Extract the server-side timestamp when the pod deletion was
    scheduled.

    :param pod: V1Pod object
    :return: Unix timestamp (float) when deletion was scheduled,
        or current time if not available
    """
    if pod.metadata.deletion_timestamp:
        ts = pod.metadata.deletion_timestamp.timestamp()
        logging.debug(f"Pod {pod.metadata.name} deletion timestamp: {ts}")
        return ts
    fallback = time.time()
    logging.debug(
        f"Pod {pod.metadata.name} deletion timestamp fallback: " f"{fallback}"
    )
    return fallback


def _get_pod_creation_timestamp(pod: V1Pod) -> float:
    """
    Extract the server-side timestamp when the pod was created.

    :param pod: V1Pod object
    :return: Unix timestamp (float) when pod was created,
        or current time if not available
    """
    if pod.metadata.creation_timestamp:
        ts = pod.metadata.creation_timestamp.timestamp()
        logging.debug(f"Pod {pod.metadata.name} creation timestamp: {ts}")
        return ts
    fallback = time.time()
    logging.debug(
        f"Pod {pod.metadata.name} creation timestamp fallback: " f"{fallback}"
    )
    return fallback


def select_and_monitor_by_label(
    label_selector: str,
    max_timeout: int,
    v1_client: CoreV1Api,
    expected_ready_pods: int = None,
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
    :param expected_ready_pods: Number of ready pods to wait for before
        stopping monitoring. If None, defaults to len(snapshot.initial_pods)
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
        expected_ready_pods=expected_ready_pods,
    )
    return future


def select_and_monitor_by_name_pattern_and_namespace_pattern(
    pod_name_pattern: str,
    namespace_pattern: str,
    max_timeout: int,
    v1_client: CoreV1Api,
    expected_ready_pods: int = None,
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
    :param expected_ready_pods: Number of ready pods to wait for before
        stopping monitoring. If None, defaults to len(snapshot.initial_pods)
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
        expected_ready_pods=expected_ready_pods,
    )
    return future


def select_and_monitor_by_namespace_pattern_and_label(
    namespace_pattern: str,
    label_selector: str,
    v1_client: CoreV1Api,
    max_timeout=30,
    expected_ready_pods: int = None,
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
    :param expected_ready_pods: Number of ready pods to wait for before
        stopping monitoring. If None, defaults to len(snapshot.initial_pods)
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
        expected_ready_pods=expected_ready_pods,
    )
    return future
