import logging
import re
import sys

from prometheus_api_client import PrometheusConnect


class KrknPrometheus:
    prom_cli: PrometheusConnect

    def __init__(
        self, prometheus_url: str, prometheus_bearer_token: str = None
    ):
        """
        Instantiates a KrknPrometheus class with the Prometheus API
        Endpoint url and the bearer token to access it (optional if
        the endpoint doesn't need authentication).

        :param prometheus_url: the prometheus API endpoint
        :param prometheus_bearer_token: the bearer token to authenticate
            the query (optional).
        """
        headers = {}
        if prometheus_bearer_token is not None:
            bearer = "Bearer " + prometheus_bearer_token
            headers = {"Authorization": bearer}
        try:
            self.prom_cli = PrometheusConnect(
                url=prometheus_url, headers=headers, disable_ssl=True
            )
        except Exception as e:
            logging.error("Not able to initialize the client %s" % e)
            sys.exit(1)

    # Process custom prometheus query
    def process_prom_query(self, query: str) -> list[dict[str:any]]:
        """
        Executes a query to the Prometheus API in PromQL language

        :param query: promQL query
        :return: a list of records in dictionary format
        """
        if self.prom_cli:
            try:
                return self.prom_cli.custom_query(query=query, params=None)
            except Exception as e:
                logging.error("Failed to get the metrics: %s" % e)
                sys.exit(1)
        else:
            logging.info(
                "Skipping the prometheus query as the "
                "prometheus client couldn't "
                "be initialized\n"
            )

    def process_alert(self, alert: dict[str, str]):
        """
        Processes Krkn alarm in the format

        expr: <promQL query>
        description: <the message that will be logged in the console>
        severity <the log level that will be used>

        Description:
        The description may contain two kind of expressions that will be
        properly replaced and valorized; the supported expression are:

        - `{{$value}}` the scalar value returned by the query (if the query
        is designed to return a scalar value

        - `{{$label.<label_name>}}` one of the metric properties
        returned by the query

        If a value is not found in the the description won't be replaced.

        Severity:
        The severity represents the log level that will be used to print the
        description in the console. The supported levels are:
        - info
        - debug
        - warning
        - error
        - critical

        If a non existing value is set an error message will be print instead
        of the the description.

        :params alert: a dictionary containing the following keys :
            expr, description, severity


        """
        if "expr" not in alert.keys():
            logging.error(
                f"invalid alert: {alert} `expr` field is missing, skipping."
            )
            return
        if "description" not in alert.keys():
            logging.error(
                f"invalid alert: {alert} `description` field "
                f"is missing, skipping."
            )
            return
        if "severity" not in alert.keys():
            logging.error(
                f"invalid alert: {alert} `severity` field "
                f"is missing, skipping."
            )
            return

        if alert["severity"] not in [
            "debug",
            "info",
            "warning",
            "error",
            "critical",
        ]:
            logging.error(f"invalid severity level: {alert['severity']}")
            return

        try:
            records = self.process_prom_query(alert["expr"])
            if len(records) == 0:
                return

            log_alert = getattr(logging, alert["severity"])
            if log_alert is None:
                raise Exception()
            for record in records:
                result = self.parse_metric(alert["description"], record)
                log_alert(result)
        except Exception as e:
            logging.error(
                f"failed to execute query: {alert['expr']} with exception {e}"
            )

    def parse_metric(self, description: str, record: dict[str:any]) -> str:
        """
        Parses the expression contained in the Krkn alert description replacing
        them with the respective values contained in the record
        previously returned by a PromQL query.

        :param description: the description containing the expression
            in the Krkn alert format
        :param record: the PromQL record from where the data will be extracted
        :return: the description with the expressions replaced by the correct
            values
        """
        result = description
        expressions = re.findall(r"{{\$[\w\-_]+[.[\w\-_]+]*}}", description)
        for expression in expressions:
            if expression == "{{$value}}":
                value = None
                if "value" in record:
                    if isinstance(record["value"], list):
                        if len(record["value"]) > 0:
                            if len(record["value"]) == 1:
                                value = record["value"][0]
                            else:
                                value = record["value"][1]
                    else:
                        value = record["value"]
                if value is not None:
                    result = result.replace(expression, value)

            elif re.match(r"^{{\$labels\.([\w\-_]+)}}$", expression):
                label = re.findall(r"^{{\$labels\.([\w\-_]+)}}", expression)
                if (
                    "metric" in record.keys()
                    and label[0] in record["metric"].keys()
                ):
                    result = result.replace(
                        expression, record["metric"][label[0]]
                    )
        return result
