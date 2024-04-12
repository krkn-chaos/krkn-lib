from concurrent.futures import ThreadPoolExecutor, wait
from multiprocessing import Event

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import PodsStatus, PodsMonitorThread


class PodsMonitorPool:
    """
    This class has the purpose to manage pools of pod
    status monitoring and result collection in the Krkn Scenarios
    having multiple killing sessions at the same time (eg. Plugin scenarios)
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
        """ """

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
        for event in self.events:
            event.set()

    def join(self) -> PodsStatus:
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
            final_status.error = Exception(merged_exception_message)
            return final_status

        for pod_status in pods_statuses:
            final_status.merge(pod_status)

        return final_status
