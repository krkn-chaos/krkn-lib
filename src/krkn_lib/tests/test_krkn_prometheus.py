import datetime
import logging

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn_lib.tests import BaseTest


class TestKrknPrometheus(BaseTest):
    url = "http://localhost:9090"

    def test_process_prom_query(self):
        prom_cli = KrknPrometheus(self.url)
        query = "node_boot_time_seconds"
        start_time = datetime.datetime.now() - datetime.timedelta(days=10)

        end_time = datetime.datetime.now()
        res = prom_cli.process_prom_query_in_range(query, start_time, end_time)

        self.assertTrue(len(res) > 0)
        self.assertTrue("metric" in res[0].keys())
        self.assertTrue("values" in res[0].keys())
        for value in res[0]["values"]:
            self.assertEqual(len(value), 2)

    def process_query(self):
        prom_cli = KrknPrometheus(self.url)
        query = "node_boot_time_seconds"

        res = prom_cli.process_query(query)

        self.assertTrue(len(res) > 0)
        self.assertTrue("metric" in res[0].keys())
        self.assertTrue("values" in res[0].keys())
        for value in res[0]["values"]:
            self.assertEqual(len(value), 2)

    def test_process_alert(self):
        prom_cli = KrknPrometheus(self.url)
        res = prom_cli.process_prom_query_in_range(
            "node_boot_time_seconds", end_time=datetime.datetime.now()
        )
        logging.disable(logging.NOTSET)
        controls = []
        for result in res:
            for value in result["values"]:
                controls.append(
                    f"container: {res[0]['metric']['container']}, "
                    f"endpoint: {res[0]['metric']['endpoint']}, "
                    f"value: {value[1]}"
                )

        alert_info = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, value: {{$value}}",
            "severity": "info",
        }

        alert_debug = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, "
            "value: {{$value}}",
            "severity": "debug",
        }

        alert_warning = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, "
            "value: {{$value}}",
            "severity": "warning",
        }

        alert_error = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, "
            "value: {{$value}}",
            "severity": "error",
        }

        alert_critical = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, "
            "value: {{$value}}",
            "severity": "critical",
        }

        alert_not_exists = {
            "expr": "node_boot_time_seconds",
            "description": "container: {{$labels.container}}, "
            "endpoint: {{$labels.endpoint}}, "
            "value: {{$value}}",
            "severity": "not_exists",
        }
        # tests that the logger contains at least a record
        # on the selected log level and that the returned string from
        # the log is contained on the log printed

        with self.assertLogs(level="INFO") as lc:
            string_value = prom_cli.process_alert(
                alert_info,
                datetime.datetime.now() - datetime.timedelta(days=1),
                datetime.datetime.now(),
            )
            self.assertTrue(len(lc.records) > 0)
            logger_output = str(lc.output[0])
            self.assertTrue(string_value[1] in logger_output)
            with self.assertLogs(level="DEBUG") as lc:
                string_value = prom_cli.process_alert(
                    alert_debug,
                    datetime.datetime.now() - datetime.timedelta(days=1),
                    datetime.datetime.now(),
                )
                self.assertTrue(len(lc.records) > 0)
                logger_output = str(lc.output[0])
                self.assertTrue(string_value[1] in logger_output)

                with self.assertLogs(level="WARNING") as lc:
                    string_value = prom_cli.process_alert(
                        alert_warning,
                        datetime.datetime.now() - datetime.timedelta(days=1),
                        datetime.datetime.now(),
                    )
                    self.assertTrue(len(lc.records) > 0)
                    logger_output = str(lc.output[0])
                    self.assertTrue(string_value[1] in logger_output)

                with self.assertLogs(level="ERROR") as lc:
                    string_value = prom_cli.process_alert(
                        alert_error,
                        datetime.datetime.now() - datetime.timedelta(days=1),
                        datetime.datetime.now(),
                    )
                    self.assertTrue(len(lc.records) > 0)
                    logger_output = str(lc.output[0])

                    self.assertTrue(string_value[1] in logger_output)

                with self.assertLogs(level="CRITICAL") as lc:
                    string_value = prom_cli.process_alert(
                        alert_critical,
                        datetime.datetime.now() - datetime.timedelta(days=1),
                        datetime.datetime.now(),
                    )
                    self.assertTrue(len(lc.records) > 0)
                    logger_output = str(lc.output[0])
                    self.assertTrue(string_value[1] in logger_output)

                with self.assertLogs(level="ERROR") as lc:
                    string_value = prom_cli.process_alert(
                        alert_not_exists,
                        datetime.datetime.now() - datetime.timedelta(days=1),
                        datetime.datetime.now(),
                    )
                    self.assertTrue(len(lc.records) == 1)
                    self.assertEqual(lc.records[0].levelname, "ERROR")
                    self.assertEqual(
                        lc.records[0].msg, "invalid severity level: not_exists"
                    )
                    logger_output = str(lc.output[0])
                    self.assertTrue(string_value[1] in logger_output)

    def test_parse_metric(self):
        prom_cli = KrknPrometheus(self.url)
        metric = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "values": [[1699357840, "0.1"]],
        }
        metric_no_value = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "values": [],
        }

        control = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['values'][0][1]}"
        )

        control_underscore = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['metric']['no_value']}"
        )

        control_no_value = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher than "
            f"30ms. {{{{$value}}}}"
        )

        description = (
            "10 minutes avg. 99th etcd commit {{$labels.instance}} latency"
            " on {{$labels.pod}} higher than 30ms. {{$value}}"
        )
        description_underscore = (
            "10 minutes avg. 99th etcd commit {{$labels.instance}} "
            "latency on {{$labels.pod}} higher than 30ms. {{$labels.no_value}}"
        )

        # tests a standard label and vale replacement
        result = prom_cli.parse_metric(description, metric)

        # tests a replacement for a metric with an
        # empty array of values ( {{$value}} won't be replaced)
        result_no_value = prom_cli.parse_metric(description, metric_no_value)
        # tests a replacement for a label containing underscore
        # ( only alnum letters, _ and - are allowed in labels)
        result_underscore = prom_cli.parse_metric(
            description_underscore, metric
        )

        self.assertEqual(control, result)
        self.assertEqual(control_no_value, result_no_value)
        self.assertEqual(control_underscore, result_underscore)
