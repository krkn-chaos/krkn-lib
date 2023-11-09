import logging

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn_lib.tests import BaseTest


class TestKrknPrometheus(BaseTest):
    url = "http://localhost:9090"

    def test_process_prom_query(self):
        prom_cli = KrknPrometheus(self.url)
        query = "node_boot_time_seconds"
        res = prom_cli.process_prom_query(query)

        self.assertTrue(len(res) > 0)
        self.assertTrue("metric" in res[0].keys())
        self.assertTrue("value" in res[0].keys())
        self.assertTrue(len(res[0]["value"]) == 2)

    def test_process_alert(self):
        prom_cli = KrknPrometheus(self.url)
        res = prom_cli.process_prom_query("node_boot_time_seconds")
        logging.disable(logging.NOTSET)
        control = (
            f"container: {res[0]['metric']['container']}, "
            f"endpoint: {res[0]['metric']['endpoint']}, "
            f"value: {res[0]['value'][1]}"
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

        with self.assertLogs(level="INFO") as lc:
            prom_cli.process_alert(alert_info)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "INFO")
            self.assertEqual(lc.records[0].msg, control)

        with self.assertLogs(level="DEBUG") as lc:
            prom_cli.process_alert(alert_debug)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "DEBUG")
            self.assertEqual(lc.records[0].msg, control)

        with self.assertLogs(level="WARNING") as lc:
            prom_cli.process_alert(alert_warning)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "WARNING")
            self.assertEqual(lc.records[0].msg, control)

        with self.assertLogs(level="ERROR") as lc:
            prom_cli.process_alert(alert_error)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "ERROR")
            self.assertEqual(lc.records[0].msg, control)

        with self.assertLogs(level="CRITICAL") as lc:
            prom_cli.process_alert(alert_critical)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "CRITICAL")
            self.assertEqual(lc.records[0].msg, control)

        with self.assertLogs(level="ERROR") as lc:
            prom_cli.process_alert(alert_not_exists)
            self.assertTrue(len(lc.records) == 1)
            self.assertEqual(lc.records[0].levelname, "ERROR")
            self.assertEqual(
                lc.records[0].msg, "invalid severity level: not_exists"
            )

    def test_parse_metric(self):
        prom_cli = KrknPrometheus(self.url)
        metric = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "value": [1699357840, "0.1"],
        }
        metric_single_value = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "value": ["0.1"],
        }
        metric_no_value = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "value": [],
        }

        metric_scalar_value = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "value": "scalar",
        }

        control = (
            f"10 minutes avg. 99th etcd commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['value'][1]}"
        )
        control_underscore = (
            f"10 minutes avg. 99th etcd commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['metric']['no_value']}"
        )
        control_no_value = (
            f"10 minutes avg. 99th etcd commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher than "
            f"30ms. {{{{$value}}}}"
        )
        control_scalar_value = (
            f"10 minutes avg. 99th etcd commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher than "
            f"30ms. {metric_scalar_value['value']}"
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
        # tests a replacement for a metric record containing a
        # single value instead of an array of two (just in case)
        result_single_value = prom_cli.parse_metric(
            description, metric_single_value
        )
        # tests a replacement for a metric with a scalar
        # value instead of an array (just in case)
        result_scalar_value = prom_cli.parse_metric(
            description, metric_scalar_value
        )
        # tests a replacement for a metric with an
        # empty array of values ( {{$value}} won't be replaced)
        result_no_value = prom_cli.parse_metric(description, metric_no_value)
        # tests a replacement for a label containing underscore
        # ( only alnum letters, _ and - are allowed in labels)
        result_underscore = prom_cli.parse_metric(
            description_underscore, metric
        )

        self.assertEqual(control, result)
        self.assertEqual(control, result_single_value)
        self.assertEqual(control_no_value, result_no_value)
        self.assertEqual(control_scalar_value, result_scalar_value)
        self.assertEqual(control_underscore, result_underscore)
