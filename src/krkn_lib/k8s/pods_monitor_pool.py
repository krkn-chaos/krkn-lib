from concurrent.futures import ThreadPoolExecutor, wait
from multiprocessing import Event

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import PodsMonitorThread, PodsStatus


class PodsMonitorPool:
    """
    This class has the purpose to manage pools of pod
    status monitoring threads for the Krkn Scenarios
    having multiple killing sessions at the same time (eg. Plugin scenarios)
    the methods reflects the behaviour of the underlying
    KrknKubernetes Primitives but each call to select_and_monitor_*
    method pushes a new thread that is managed by the pool.
    The join method joins all the threads in the pool simultaneously
    and merges the results on a single PodsStatus structure.
    """

    events: list[Event]

    def __init__(self, krkn_lib: KrknKubernetes):
        self.krkn_lib = krkn_lib
        self.pods_monitor_threads: list[PodsMonitorThread] = []
        self.pods_statuses = []
        self.events: list[Event] = []

    def select_and_monitor_by_label(
        self, label_selector: str, max_timeout: int
    ):
        """
        Pushes into the pool a monitoring thread for all the pods identified
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

        """
        event = Event()
        self.events.append(event)
        pods_and_namespaces = self.krkn_lib.select_pods_by_label(
            label_selector=label_selector
        )
        pod_monitor_thread = self.krkn_lib.monitor_pods_by_label(
            label_selector=label_selector,
            pods_and_namespaces=pods_and_namespaces,
            max_timeout=max_timeout,
            event=event,
        )
        self.pods_monitor_threads.append(pod_monitor_thread)

    def select_and_monitor_by_name_pattern_and_namespace_pattern(
        self, pod_name_pattern: str, namespace_pattern: str, max_timeout: int
    ):
        """
        Pushes into the pool a monitoring thread for all the pods identified
        by a pod name regex pattern
        and a namespace regex pattern, that collects infos about the
        pods recovery after a kill scenario while the scenario is running.

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

        """

        event = Event()
        self.events.append(event)

        pods_and_namespaces = (
            self.krkn_lib.select_pods_by_name_pattern_and_namespace_pattern(
                pod_name_pattern=pod_name_pattern,
                namespace_pattern=namespace_pattern,
            )
        )

        pods_monitor_thread = (
            self.krkn_lib.monitor_pods_by_name_pattern_and_namespace_pattern(
                pod_name_pattern=pod_name_pattern,
                namespace_pattern=namespace_pattern,
                pods_and_namespaces=pods_and_namespaces,
                max_timeout=max_timeout,
                event=event,
            )
        )

        self.pods_monitor_threads.append(pods_monitor_thread)

    def select_and_monitor_by_namespace_pattern_and_label(
        self,
        namespace_pattern: str,
        label_selector: str,
        max_timeout=30,
    ):
        """
        Pushes into the pool a monitoring thread for all the pods identified
        by a namespace regex pattern
        and a pod label selector, that collects infos about the
        pods recovery after a kill scenario while the scenario is running.

        :param label_selector: the label selector used to filter
            the pods to monitor (must be the same used in
            `select_pods_by_label`)
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

        """
        event = Event()
        self.events.append(event)
        pods_and_namespaces = (
            self.krkn_lib.select_pods_by_namespace_pattern_and_label(
                namespace_pattern=namespace_pattern,
                label_selector=label_selector,
            )
        )

        pod_monitor_thread = (
            self.krkn_lib.monitor_pods_by_namespace_pattern_and_label(
                namespace_pattern=namespace_pattern,
                label_selector=label_selector,
                pods_and_namespaces=pods_and_namespaces,
                max_timeout=max_timeout,
                event=event,
            )
        )
        self.pods_monitor_threads.append(pod_monitor_thread)

    def cancel(self):
        """
        cancels all the threads in the pool and makes return
        the join() call immediately
        """
        for event in self.events:
            event.set()

    def join(self) -> PodsStatus:
        """
        waits all the threads pushed into the pool to finish

        :return: a PodsStatus structure that is the merge between
            all the PodsStatus structures returned by every thread
            pushed into the pool.
        """
        futures = []
        pods_statuses: list[PodsStatus] = []
        final_status = PodsStatus()
        with ThreadPoolExecutor() as executor:
            for thread in self.pods_monitor_threads:
                futures.append(executor.submit(thread.join))
            done, _ = wait(futures)

            for future in done:
                pods_statuses.append(future.result())

        exceptions = [status.error for status in pods_statuses if status.error]
        if len(exceptions) > 0:
            merged_exception_message = ", ".join([str(e) for e in exceptions])
            final_status.error = merged_exception_message
            return final_status

        for pod_status in pods_statuses:
            final_status.merge(pod_status)

        return final_status
