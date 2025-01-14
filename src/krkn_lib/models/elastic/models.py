import datetime

from elasticsearch_dsl import (
    Date,
    Document,
    Float,
    InnerDoc,
    Integer,
    Keyword,
    Long,
    Nested,
    Text,
)

from krkn_lib.models.telemetry.models import ChaosRunTelemetry


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


class ElasticMetricValue(InnerDoc):
    timestamp = Long()
    value = Float()

    def __init__(self, timestamp: int, value: float, **kwargs):
        super().__init__(**kwargs)
        self.timestamp = timestamp
        self.value = value


class ElasticMetric(Document):
    run_uuid = Keyword()
    name = Text()
    created_at = Date()
    timestamp = Long()
    value = Float()

    def __init__(
        self,
        run_uuid: str,
        name: str,
        created_at: datetime,
        timestamp: int,
        value: float,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.run_uuid = run_uuid
        self.name = name
        self.created_at = created_at
        self.timestamp = timestamp
        self.value = value


# Telemetry models


class ElasticScenarioParameters(InnerDoc):
    pass


class ElasticScenarioTelemetry(InnerDoc):
    start_timestamp = Float()
    end_timestamp = Float()
    scenario = Text(fields={"keyword": Keyword()})
    exit_status = Integer()
    parameters_base64 = Text()
    parameters = Nested(ElasticScenarioParameters)
    affected_pods = Text(multi=True)


class ElasticChaosRunTelemetry(Document):
    scenarios = Nested(ElasticScenarioTelemetry, multi=True)
    node_summary_infos = Text(multi=True)
    node_taints = Text(multi=True)
    kubernetes_objects_count = Nested(InnerDoc)
    network_plugins = Text()
    timestamp = Text()
    total_node_count = Integer()
    cloud_infrastructure = Text()
    cloud_type = Text()
    cluster_version = Text()
    run_uuid = Text(fields={"keyword": Keyword()})

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
                exit_status=sc.exit_status,
                parameters_base64=sc.parameters_base64,
                parameters=sc.parameters,
                affected_pods=sc.affected_pods,
            )
            for sc in chaos_run_telemetry.scenarios
        ]

        self.node_summary_infos = [
            info.__dict__ for info in chaos_run_telemetry.node_summary_infos
        ]
        self.node_taints = [
            taint.__dict__ for taint in chaos_run_telemetry.node_taints
        ]
        self.kubernetes_objects_count = (
            chaos_run_telemetry.kubernetes_objects_count
        )
        self.network_plugins = chaos_run_telemetry.network_plugins
        self.timestamp = chaos_run_telemetry.timestamp
        self.total_node_count = chaos_run_telemetry.total_node_count
        self.cloud_infrastructure = chaos_run_telemetry.cloud_infrastructure
        self.cloud_type = chaos_run_telemetry.cloud_type
        self.cluster_version = chaos_run_telemetry.cluster_version
        self.run_uuid = chaos_run_telemetry.run_uuid

    def to_json(self):
        return self.__dict__
