import logging
import math
import re
import sys
from datetime import datetime, timedelta

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
    def process_prom_query_in_range(
        self,
        query: str,
        start_time: datetime = None,
        end_time: datetime = None,
    ) -> list[dict[str:any]]:
        """
        Executes a query to the Prometheus API in PromQL language

        :param query: promQL query
        :param start_time: start time of the result set (default now - 1 day)
        :param end_time: end time of the result set (default min datetime)

        :return: a list of records in dictionary format
        """
        start_time = (
            datetime.now() - timedelta(days=1)
            if start_time is None
            else start_time
        )
        end_time = datetime.now() if end_time is None else end_time

        granularity = math.ceil(
            (end_time - start_time).total_seconds() / 11000
        )
        granularity = granularity if granularity > 0 else 1
        if self.prom_cli:
            try:
                return self.prom_cli.custom_query_range(
                    query=query,
                    start_time=start_time,
                    end_time=end_time,
                    step=f"{granularity}s",
                )
            except Exception as e:
                logging.error("Failed to get the metrics: %s" % e)
                raise e
        else:
            logging.info(
                "Skipping the prometheus query as the "
                "prometheus client couldn't "
                "be initialized\n"
            )

    def process_alert(
        self, alert: dict[str, str], start_time: datetime, end_time: datetime
    ):
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
        :param start_time: start time of the result set (if None
            no time filter is applied to the query)
        :param end_time: end time of the result set (if None
            no time filter is applied to the query)



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
            records = self.process_prom_query_in_range(
                alert["expr"], start_time, end_time
            )
            if len(records) == 0:
                return

            log_alert = getattr(logging, alert["severity"])
            if log_alert is None:
                raise Exception()

            # prints only one record per query result
            if len(records) > 0:
                result = self.parse_metric(alert["description"], records[0])
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

        values = []

        if "values" in record:
            if isinstance(record["values"], list):
                for value in record["values"]:
                    if isinstance(value, list):
                        values.append(value[1])

        labels = re.findall(r"{{\$labels\.([\w\-_]+)}}", description)
        for label in labels:
            if "metric" in record.keys() and label in record["metric"].keys():
                placeholder = "{{{{$labels.{0}}}}}".format(label)
                description = description.replace(
                    placeholder, record["metric"][label]
                )

        if "{{$value}}" in description:
            if len(values) > 0:
                # returns the first value in the series
                description = description.replace("{{$value}}", values[0])

        return description
