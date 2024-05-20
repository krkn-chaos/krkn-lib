from elasticsearch_dsl import Keyword, Text, Date, Document


class ElasticAlert(Document):
    run_id = Keyword()
    severity: Text()
    alert: Text()
    created_at: Date()
