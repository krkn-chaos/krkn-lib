from elasticsearch_dsl import (
    Keyword,
    Text,
    Date,
    Document,
    Float,
    Long,
    Nested,
)
import datetime


class ElasticAlert(Document):
    run_id = Keyword()
    severity = Text()
    alert = Text()
    created_at = Date()

    def __init__(
        self,
        run_id: str = None,
        severity: str = None,
        alert: str = None,
        created_at: datetime = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.run_id = run_id
        self.severity = severity
        self.alert = alert
        self.created_at = created_at


class ElasticMetricValue(Document):
    timestamp = Long()
    value = Float()

    def __init__(self, timestamp: int, value: float, **kwargs):
        super().__init__(**kwargs)
        self.timestamp = timestamp
        self.value = value


class ElasticMetric(Document):
    run_id = Keyword()
    name = Text()
    values = Nested(ElasticMetricValue)
    created_at = Date()

    def __init__(
        self,
        run_id: str,
        name: str,
        values: list[ElasticMetricValue],
        created_at: datetime,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.run_id = run_id
        self.name = name
        self.created_at = created_at
        self.values = values
