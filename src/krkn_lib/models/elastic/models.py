import datetime

from elasticsearch_dsl import (
    Boolean,
    Date,
    Document,
    Float,
    InnerDoc,
    Integer,
    Keyword,
    Nested,
    Text,
)

from krkn_lib.models.telemetry import ChaosRunTelemetry


class ElasticAlert(Document):
    run_uuid = Keyword()
    severity = Text()
    alert = Text()
    created_at = Date()

    def __init__(
        self,
        run_uuid: str = None,
        severity: str = None,
        alert: str = None,
        created_at: datetime = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.run_uuid = run_uuid
        self.severity = severity
        self.alert = alert
        self.created_at = created_at


class ElasticMetric(Document):
    run_uuid = Keyword()
    timestamp = Date()

    def __init__(
        self,
        run_uuid: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.run_uuid = run_uuid


# Telemetry models
class ElasticAffectedPod(InnerDoc):
    pod_name = Text(fields={"keyword": Keyword()})
    namespace = Text()
    total_recovery_time = Float()
    pod_readiness_time = Float()
    pod_rescheduling_time = Float()


class ElasticPodsStatus(InnerDoc):
    recovered = Nested(ElasticAffectedPod, multi=True)
    unrecovered = Nested(ElasticAffectedPod, multi=True)
    error = Text()


class ElasticAffectedNodes(InnerDoc):
    node_name = Text(fields={"keyword": Keyword()})
    node_id = Text()
    not_ready_time = Float()
    ready_time = Float()
    stopped_time = Float()
    running_time = Float()
    terminating_time = Float()


class ElasticScenarioParameters(InnerDoc):
    pass


class ElasticScenarioTelemetry(InnerDoc):
    start_timestamp = Float()
    end_timestamp = Float()
    scenario = Text(fields={"keyword": Keyword()})
    scenario_type = Text(fields={"keyword": Keyword()})
    exit_status = Integer()
    parameters_base64 = Text()
    parameters = Nested(ElasticScenarioParameters)
    affected_pods = Nested(ElasticPodsStatus)
    affected_nodes = Nested(ElasticAffectedNodes, multi=True)


class ElasticNodeInfo(InnerDoc):
    count = Integer()
    architecture = Text()
    instance_type = Text()
    node_type = Text()
    kernel_version = Text()
    kubelet_version = Text()
    os_version = Text()


class ElasticTaint(InnerDoc):
    key = Text()
    value = Text()
    effect = Text()


class ElasticHealthChecks(InnerDoc):
    url = Text()
    status = Boolean()
    status_code = Text()
    start_timestamp = Date()
    end_timestamp = Date()
    duration = Float()


class ElasticChaosRunTelemetry(Document):
    scenarios = Nested(ElasticScenarioTelemetry, multi=True)
    node_summary_infos = Nested(ElasticNodeInfo, multi=True)
    node_taints = Nested(ElasticTaint, multi=True)
    kubernetes_objects_count = Nested(InnerDoc)
    network_plugins = Text(multi=True)
    timestamp = Text()
    total_node_count = Integer()
    cloud_infrastructure = Text()
    cloud_type = Text()
    cluster_version = Text()
    major_version = Text()
    job_status = Boolean()
    run_uuid = Text(fields={"keyword": Keyword()})
    health_checks = Nested(ElasticHealthChecks, multi=True)

    class Index:
        name = "chaos_run_telemetry"

    def __init__(
        self, chaos_run_telemetry: ChaosRunTelemetry = None, **kwargs
    ):
        super().__init__(**kwargs)
        # cheap trick to avoid reinventing the wheel :-)
        if chaos_run_telemetry is None and kwargs:
            chaos_run_telemetry = ChaosRunTelemetry(json_dict=kwargs)
        self.scenarios = [
            ElasticScenarioTelemetry(
                start_timestamp=sc.start_timestamp,
                end_timestamp=sc.end_timestamp,
                scenario=sc.scenario,
                scenario_type=sc.scenario_type,
                exit_status=sc.exit_status,
                parameters_base64=sc.parameters_base64,
                parameters=sc.parameters,
                affected_pods=ElasticPodsStatus(
                    recovered=[
                        ElasticAffectedPod(
                            pod_name=pod.pod_name,
                            namespace=pod.namespace,
                            total_recovery_time=pod.total_recovery_time,
                            pod_readiness_time=pod.pod_readiness_time,
                            pod_rescheduling_time=pod.pod_rescheduling_time,
                        )
                        for pod in sc.affected_pods.recovered
                    ],
                    unrecovered=[
                        ElasticAffectedPod(
                            pod_name=pod.pod_name, namespace=pod.namespace
                        )
                        for pod in sc.affected_pods.unrecovered
                    ],
                    error=sc.affected_pods.error,
                ),
                affected_nodes=[
                    ElasticAffectedNodes(
                        node_name=node.node_name,
                        node_id=node.node_id,
                        not_ready_time=node.not_ready_time,
                        ready_time=node.ready_time,
                        stopped_time=node.stopped_time,
                        running_time=node.running_time,
                        terminating_time=node.terminating_time,
                    )
                    for node in sc.affected_nodes
                ],
            )
            for sc in chaos_run_telemetry.scenarios
        ]

        self.node_summary_infos = [
            ElasticNodeInfo(
                count=info.count,
                architecture=info.architecture,
                instance_type=info.instance_type,
                kernel_version=info.kernel_version,
                kubelet_version=info.kubelet_version,
                os_version=info.os_version,
            )
            for info in chaos_run_telemetry.node_summary_infos
        ]
        self.node_taints = [
            ElasticTaint(key=taint.key, value=taint.value, effect=taint.effect)
            for taint in chaos_run_telemetry.node_taints
        ]
        self.kubernetes_objects_count = (
            chaos_run_telemetry.kubernetes_objects_count
        )
        self.network_plugins = chaos_run_telemetry.network_plugins

        if chaos_run_telemetry.health_checks:
            self.health_checks = [
                ElasticHealthChecks(
                    url=info.url,
                    status=info.status,
                    status_code=info.status_code,
                    start_timestamp=datetime.datetime.fromisoformat(
                        str(info.start_timestamp)
                    ),
                    end_timestamp=datetime.datetime.fromisoformat(
                        str(info.end_timestamp)
                    ),
                    duration=info.duration,
                )
                for info in chaos_run_telemetry.health_checks
            ]
        else:
            self.health_checks = None

        self.timestamp = chaos_run_telemetry.timestamp
        self.total_node_count = chaos_run_telemetry.total_node_count
        self.cloud_infrastructure = chaos_run_telemetry.cloud_infrastructure
        self.cloud_type = chaos_run_telemetry.cloud_type
        self.cluster_version = chaos_run_telemetry.cluster_version
        self.run_uuid = chaos_run_telemetry.run_uuid
        self.job_status = chaos_run_telemetry.job_status
        self.major_version = chaos_run_telemetry.major_version
