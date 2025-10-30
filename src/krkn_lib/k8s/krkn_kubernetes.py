import ast
import json
import logging
import os
import random
import re
import threading
import time
import warnings
from queue import Queue
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import kubernetes
import urllib3
import yaml
from jinja2 import Environment, PackageLoader
from kubeconfig import KubeConfig
from kubernetes import client, config, utils, watch
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.client import DynamicClient
from kubernetes.stream import stream
from urllib3 import HTTPResponse

from krkn_lib.models.k8s import (
    PVC,
    AffectedNode,
    ApiRequestException,
    Container,
    NodeResources,
    Pod,
    ServiceHijacking,
    Volume,
    VolumeMount,
)
from krkn_lib.models.krkn import HogConfig, HogType
from krkn_lib.models.telemetry import ClusterEvent, NodeInfo, Taint
from krkn_lib.utils import filter_dictionary, get_random_string
from krkn_lib.utils.safe_logger import SafeLogger

SERVICE_TOKEN_FILENAME = "/var/run/secrets/k8s.io/serviceaccount/token"
SERVICE_CERT_FILENAME = "/var/run/secrets/k8s.io/serviceaccount/ca.crt"


class KrknKubernetes:
    """ """

    request_chunk_size: int = 250
    watch_resource: watch.Watch = None
    __kubeconfig_string: str = None
    __kubeconfig_path: str = None
    client_config: kubernetes.client.Configuration = None

    @property
    def api_client(self) -> client.ApiClient:
        return client.ApiClient(self.client_config)

    @property
    def cli(self) -> client.CoreV1Api:
        return client.CoreV1Api(self.api_client)

    @property
    def version_client(self) -> client.VersionApi:
        return client.VersionApi(self.api_client)

    @property
    def batch_cli(self) -> client.BatchV1Api:
        return client.BatchV1Api(self.api_client)

    @property
    def apps_api(self) -> client.AppsV1Api:
        return client.AppsV1Api(self.api_client)

    @property
    def net_cli(self) -> client.NetworkingV1Api:
        return client.NetworkingV1Api(self.api_client)

    @property
    def dyn_client(cls) -> DynamicClient:
        return DynamicClient(cls.api_client)

    @property
    def custom_object_client(cls) -> client.CustomObjectsApi:
        return client.CustomObjectsApi(cls.api_client)

    def __init__(
        self,
        kubeconfig_path: str,
        request_chunk_size: int = 250,
    ):
        """
        KrknKubernetes Constructor. Can be invoked with kubeconfig_path
        or, optionally, with a kubeconfig in string
        format using the keyword argument

        :param kubeconfig_path: kubeconfig path
        :param: request_chunk_size: int of chunk size to limit requests to

        Initialization with kubeconfig path:

        >>> KrknKubernetes(log_writer, "/home/test/.kube/config")

        """
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        urllib3.disable_warnings(DeprecationWarning)
        warnings.filterwarnings(
            action="ignore", message="unclosed", category=ResourceWarning
        )

        self.request_chunk_size = request_chunk_size

        if kubeconfig_path is not None:
            self.__initialize_config(kubeconfig_path)
            self.__kubeconfig_path = kubeconfig_path

    def __del__(self):
        self.api_client.rest_client.pool_manager.clear()
        self.api_client.close()

    # Load kubeconfig and initialize k8s python client
    def __initialize_config(self, kubeconfig_path: str = None):
        """
        Initialize all clients from kubeconfig path

        :param kubeconfig_path: kubeconfig path,
            (optional default KUBE_CONFIG_DEFAULT_LOCATION)
        """
        if kubeconfig_path is None:
            kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
        if "~/" in kubeconfig_path:
            kubeconfig_path = os.path.expanduser(kubeconfig_path)
        if not os.path.isfile(kubeconfig_path):
            if os.path.isfile(SERVICE_TOKEN_FILENAME):
                with open(SERVICE_TOKEN_FILENAME) as f:
                    content = f.read().splitlines()
                    if not content:
                        raise Exception("Token file exists but empty.")
                kube_addr = os.environ.get("KUBERNETES_PORT_443_TCP_ADDR")
                kube_port = os.environ.get("KUBERNETES_PORT_443_TCP_PORT")
                conf = KubeConfig()
                conf.set_cluster(
                    name="krkn-cluster",
                    server=f"https://{kube_addr}:{kube_port}",
                    certificate_authority=SERVICE_CERT_FILENAME,
                )
                conf.set_credentials(name="user", token=content[0])
                conf.set_context(
                    name="krkn-context", cluster="krkn-cluster", user="user"
                )
                conf.use_context("krkn-context")
                self.client_config = client.Configuration().get_default_copy()

        try:
            config.load_kube_config(kubeconfig_path)

            self.client_config = client.Configuration().get_default_copy()
            http_proxy = os.getenv("http_proxy", None)
            if http_proxy is not None:
                os.environ["HTTP_PROXY"] = http_proxy
                self.client_config.proxy = http_proxy
                proxy_auth = urlparse(http_proxy)
                auth_string = proxy_auth.username + ":" + proxy_auth.password
                self.client_config.proxy_headers = urllib3.util.make_headers(
                    proxy_basic_auth=auth_string
                )

            client.Configuration.set_default(self.client_config)
            self.watch_resource = watch.Watch()
            # Get the logger for the kubernetes client
            kubernetes_logger = logging.getLogger('kubernetes')

            # Set the logging level to a higher level than DEBUG, 
            # such as INFO, WARNING, or ERROR
            # This will effectively disable DEBUG level messages.
            kubernetes_logger.setLevel(logging.INFO)
        except OSError:
            raise Exception(
                "Invalid kube-config file: {0}. "
                "No configuration found.".format(kubeconfig_path)
            )

    def _get_clusterversion_string(self) -> str:
        """
        Return clusterversion status text on OpenShift, empty string
        on other distributions

        *** IT MUST BE CONSIDERED A PRIVATE METHOD (CANNOT USE
        *** DOUBLE UNDERSCORE TO MANTAIN IT VISIBLE ON SUB-CLASSES)
        *** USED IN KrknKubernetes and KrknOpenshift TO AUTODETECT
        *** THE CLUSTER TYPE

        :return: clusterversion status
        """

        try:
            cvs = self.custom_object_client.list_cluster_custom_object(
                "config.openshift.io",
                "v1",
                "clusterversions",
            )
            for cv in cvs["items"]:
                for condition in cv["status"]["conditions"]:
                    if condition["type"] == "Available":
                        return condition["message"].split(" ")[-1]
            return ""
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return ""
            else:
                raise e

    def is_kubernetes(self) -> bool:
        """
        Checks if it's a kubernetes cluster
        :return: true if it's kubernetes false if not
        """
        value = self._get_clusterversion_string()
        return value is None or value == ""

    def get_kubeconfig_path(self) -> str:
        """
        Returns a path of the kubeconfig with which
        has been initialized the class. If the class
        has been initialized with a kubeconfig string,
        a temporary file will be created and the
        path returned.

        :return: a valid kubeconfig path
        """
        if self.__kubeconfig_path:
            return self.__kubeconfig_path

    def get_version(self) -> str:
        try:
            api_response = self.version_client.get_code()
            major_version = api_response.major
            minor_version = api_response.minor
            return major_version + "." + minor_version
        except ApiException as e:
            print("Exception when calling VersionApi->get_code: %s\n" % e)

    def get_host(self) -> str:
        """
        Returns the Kubernetes server URL

        :return: k8s server URL
        """

        return self.cli.api_client.configuration.get_default_copy().host

    def list_continue_helper(self, func, *args, **keyword_args):
        """
        List continue helper, be able to get all objects past the request limit

        :param func: function to call of the kubernetes cli
        :param args: any set arguments for the function
        :param keyword_args: key value pair arguments to pass to the function
        :return: list of all resources after segmentation
        """
        ret_overall = []
        try:
            ret = func(*args, **keyword_args)
            ret_overall.append(ret)
            continue_string = ret.metadata._continue

            while continue_string:
                ret = func(*args, **keyword_args, _continue=continue_string)
                ret_overall.append(ret)

                continue_string = ret.metadata._continue

        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->%s: %s\n" % (str(func), e)
            )

        return ret_overall

    # Return of all data of namespaces
    def list_all_namespaces(self, label_selector: str = None) -> list[str]:
        """
        List all namespaces with info

        :param label_selector: filter by label
            selector (optional default `None`)
        :return: list of namespaces json data
        """

        try:
            if label_selector:
                ret = self.list_continue_helper(
                    self.cli.list_namespace,
                    pretty=True,
                    label_selector=label_selector,
                    limit=self.request_chunk_size,
                )
            else:
                ret = self.list_continue_helper(
                    self.cli.list_namespace,
                    pretty=True,
                    limit=self.request_chunk_size,
                )
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_namespaced_pod: %s\n",
                str(e),
            )
            raise e

        return ret

    #
    def list_namespaces(self, label_selector: str = None) -> list[str]:
        """
        List all namespaces

        :param label_selector: filter by label
            selector (optional default `None`)
        :return: list of namespaces names
        """

        namespaces = []
        try:
            ret = self.list_all_namespaces(label_selector)
        except ApiException as e:
            logging.error(
                "Exception when calling list_namespaces: %s\n",
                str(e),
            )
            raise e
        for ret_list in ret:
            for namespace in ret_list.items:
                namespaces.append(namespace.metadata.name)
        return namespaces

    def list_namespaces_by_regex(self, regex: str) -> list[str]:
        """
        Lists all the namespaces matching a regex

        :param regex: The regular expression against which the
            namespaces will be compared
        :return: a list of namespaces matching the regex

        """
        namespaces = self.list_namespaces()
        filtered_namespaces = [ns for ns in namespaces if re.match(regex, ns)]
        return filtered_namespaces

    def get_namespace_status(self, namespace_name: str) -> str:
        """
        Get status of a given namespace

        :param namespace_name: namespace name
        :return: namespace status
        """

        ret = ""
        try:
            ret = self.cli.read_namespace_status(namespace_name)
            return ret.status.phase
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "CoreV1Api->read_namespace_status: %s\n",
                str(e),
            )
            raise ApiRequestException("%s" % str(e))

    def delete_namespace(self, namespace: str) -> client.V1Status:
        """
        Delete a given namespace
        using k8s python client

        :param namespace: namespace name
        :return: V1Status API object
        """

        try:
            api_response = self.cli.delete_namespace(namespace)
            logging.debug(
                "Namespace deleted. status='%s'", str(api_response.status)
            )
            return api_response

        except Exception as e:
            logging.error(
                "Exception when calling CoreV1Api->delete_namespace: %s\n",
                str(e),
            )
            raise e

    def check_namespaces(
        self, namespaces: list[str], label_selector: str = None
    ) -> list[str]:
        """
        Check if all the watch_namespaces are valid

        :param namespaces: list of namespaces to check
        :param label_selector: filter by label_selector
            (optional default `None`)
        :return: a list of matching namespaces
        """
        try:
            valid_namespaces = self.list_namespaces(label_selector)
            regex_namespaces = set(namespaces) - set(valid_namespaces)
            final_namespaces = set(namespaces) - set(regex_namespaces)
            valid_regex = set()
            if regex_namespaces:
                for namespace in valid_namespaces:
                    for regex_namespace in regex_namespaces:
                        if re.search(regex_namespace, namespace):
                            final_namespaces.add(namespace)
                            valid_regex.add(regex_namespace)
                            break
            invalid_namespaces = regex_namespaces - valid_regex
            if invalid_namespaces:
                raise ApiRequestException(
                    "There exists no namespaces matching: {0}".format(
                        invalid_namespaces
                    )
                )
            return list(final_namespaces)
        except Exception as e:
            logging.error("%s", str(e))
            raise e

    #
    def list_nodes(self, label_selector: str = None) -> list[str]:
        """
        List nodes in the cluster

        :param label_selector: filter by label
            selector (optional default `None`)
        :return: a list of node names
        """
        nodes = []
        try:
            if label_selector:
                ret = self.list_continue_helper(
                    self.cli.list_node,
                    pretty=True,
                    label_selector=label_selector,
                    limit=self.request_chunk_size,
                )
            else:
                ret = self.list_continue_helper(
                    self.cli.list_node,
                    pretty=True,
                    limit=self.request_chunk_size,
                )
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_node: %s\n", str(e)
            )
            raise ApiRequestException(str(e))
        for ret_list in ret:
            for node in ret_list.items:
                nodes.append(node.metadata.name)
        return nodes

    # TODO: refactoring to work both in k8s and OpenShift
    def list_killable_nodes(self, label_selector: str = None) -> list[str]:
        """
        List nodes in the cluster that can be killed

        :param label_selector: filter by label
            selector (optional default `None`)
        :return: a list of node names that can be killed
        """
        nodes = []
        kraken_node_name = self.find_kraken_node()
        try:
            if label_selector:
                ret = self.cli.list_node(
                    pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_node(pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_node: %s\n", str(e)
            )
            raise e
        for node in ret.items:
            if kraken_node_name != node.metadata.name:
                for cond in node.status.conditions:
                    if (
                        str(cond.type) == "Ready"
                        and str(cond.status) == "True"
                    ):
                        nodes.append(node.metadata.name)
        return nodes

    def list_killable_managedclusters(
        self, label_selector: str = None
    ) -> list[str]:
        """
        List managed clusters attached to the hub that can be killed

        :param label_selector: filter by label selector
            (optional default `None`)
        :return: a list of managed clusters names
        """
        managedclusters = []
        try:
            ret = self.custom_object_client.list_cluster_custom_object(
                group="cluster.open-cluster-management.io",
                version="v1",
                plural="managedclusters",
                label_selector=label_selector,
            )
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "CustomObjectsApi->list_cluster_custom_object: %s\n",
                str(e),
            )
            raise e
        for managedcluster in ret["items"]:
            conditions = managedcluster["status"]["conditions"]
            available = list(
                filter(
                    lambda condition: condition["reason"]
                    == "ManagedClusterAvailable",
                    conditions,
                )
            )
            if available and available[0]["status"] == "True":
                managedclusters.append(managedcluster["metadata"]["name"])
        return managedclusters

    def list_pods(
        self,
        namespace: str,
        label_selector: str = None,
        field_selector: str = None,
        exclude_label: str = None,
    ) -> list[str]:
        """
        List pods in the given namespace

        :param namespace: namespace to search for pods
        :param label_selector: filter by label selector
            (optional default `None`)
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"
        :param exclude_label: exclude pods matching this label
            in format "key=value" (optional default `None`)
        :return: a list of pod names
        """
        pods = []
        try:
            ret = self.get_all_pod_info(
                namespace, label_selector, field_selector
            )
        except ApiException as e:
            logging.error(
                "Exception when calling list_pods: %s\n",
                str(e),
            )
            raise e
        for ret_list in ret:
            for pod in ret_list.items:
                # Skip pods with the exclude label if specified
                if exclude_label and pod.metadata.labels:
                    exclude_key, exclude_value = exclude_label.split("=", 1)
                    if (
                        exclude_key in pod.metadata.labels
                        and pod.metadata.labels[exclude_key] == exclude_value
                    ):
                        continue
                pods.append(pod.metadata.name)
        return pods

    def create_obj(self, obj_body: json, namespace: str, api_func):
        try:
            api_func(body=obj_body, namespace=namespace)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->%s: %s\n"
                % (str(api_func), e)
            )
            raise e

    def create_net_policy(self, body: str, namespace: str):
        """
        Create a network policy

        :param body: json body of network policy to create
        :param namespace: namespace to find daemonsets in
        """
        self.create_obj(
            body, namespace, self.net_cli.create_namespaced_network_policy
        )

    def get_daemonset(self, namespace: str) -> list[str]:
        """
        Return a list of daemon set names

        :param namespace: namespace to find daemonsets in
        :return: list of daemonset names
        """
        daemonsets = []
        try:
            ret = self.apps_api.list_namespaced_daemon_set(
                namespace, pretty=True
            )
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "AppsV1Api->list_namespaced_daemon_set: %s\n",
                str(e),
            )
            raise e
        for daemonset in ret.items:
            daemonsets.append(daemonset.metadata.name)
        return daemonsets

    def get_deployment_ns(self, namespace: str) -> list[str]:
        """
        Return a list of deployment set names

        :param namespace: namespace to find deployments in
        :return: list of deployment names
        """
        deployments = []
        try:
            ret = self.apps_api.list_namespaced_deployment(
                namespace, pretty=True
            )
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "AppsV1Api->list_namespaced_deployment: %s\n",
                str(e),
            )
            raise e
        for deployment in ret.items:
            deployments.append(deployment.metadata.name)
        return deployments

    def delete_deployment(self, name: str, namespace: str):
        """
        Delete a deployments given a certain name and namespace

        :param name: name of deployment
        :param namespace: namespace deployment is in
        """
        try:
            self.apps_api.delete_namespaced_deployment(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Deployment already deleted")
            else:
                logging.error("Failed to delete deployment %s", str(e))
                raise e

    def delete_daemonset(self, name: str, namespace: str):
        """
        Delete a daemonset given a certain name and namespace

        :param name: name of daemonset
        :param namespace: namespace daemonset is in
        """
        try:
            self.apps_api.delete_namespaced_daemon_set(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Daemon Set already deleted")
            else:
                logging.error("Failed to delete daemonset %s", str(e))
                raise e

    def delete_statefulset(self, name: str, namespace: str):
        """
        Delete a statefulset given a certain name and namespace

        :param name: name of statefulset
        :param namespace: namespace statefulset is in
        """
        try:
            self.apps_api.delete_namespaced_stateful_set(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Statefulset already deleted")
            else:
                logging.error("Failed to delete statefulset %s", str(e))
                raise e

    def delete_replicaset(self, name: str, namespace: str):
        """
        Delete a replicaset given a certain name and namespace

        :param name: name of replicaset
        :param namespace: namespace replicaset is in
        """
        try:
            self.apps_api.delete_namespaced_replica_set(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Replica set already deleted")
            else:
                logging.error("Failed to delete replicaset %s", str(e))
                raise e

    def delete_services(self, name: str, namespace: str):
        """
        Delete a service given a certain name and namespace

        :param name: name of service
        :param namespace: namespace service is in
        """
        try:
            self.cli.delete_namespaced_service(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Service already deleted")
            else:
                logging.error("Failed to delete service %s", str(e))
                raise e

    def delete_net_policy(self, name: str, namespace: str):
        """
        Delete a network policy given a certain name and namespace

        :param name: name of network policy
        :param namespace: namespace network policy is in
        """
        try:
            self.net_cli.delete_namespaced_network_policy(name, namespace)
        except ApiException as e:
            if e.status == 404:
                logging.info("Network policy already deleted")
            else:
                logging.error("Failed to delete network policy %s", str(e))
                raise e

    def get_deployment_ready(self, name: str, namespace: str):
        """
        Return a deployments detailed information

        :param name: name of deployment
        :param namespace: namespace deployment is in
        """
        try:
            return self.apps_api.read_namespaced_deployment_scale(
                name, namespace
            )
        except ApiException as e:
            if e.status == 404:
                logging.info("Get deployment data")
            else:
                logging.error("Failed to get deployment data %s", str(e))
                raise e

    def get_all_pods(
        self, label_selector: str = None, field_selector: str = None
    ) -> list[[str, str]]:
        """
        Return a list of tuples containing pod name [0] and namespace [1]

        :param label_selector: filter by label_selector
            (optional default `None`)
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"
        :return: list of tuples pod,namespace
        """
        pods = []
        if label_selector:
            ret = self.list_continue_helper(
                self.cli.list_pod_for_all_namespaces,
                pretty=True,
                label_selector=label_selector,
                limit=self.request_chunk_size,
                field_selector=field_selector,
            )
        else:
            ret = self.list_continue_helper(
                self.cli.list_pod_for_all_namespaces,
                pretty=True,
                limit=self.request_chunk_size,
                field_selector=field_selector,
            )
        for ret_list in ret:
            for pod in ret_list.items:
                pods.append([pod.metadata.name, pod.metadata.namespace])
        return pods

    def get_namespaced_net_policy(self, namespace):
        """
        Return a list of network policy names

        :param namespace: find only statefulset in given namespace
        :return: list of network policy names
        """
        nps = []
        try:
            ret = self.net_cli.list_namespaced_network_policy(namespace)
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "AppsV1Api->list_namespaced_stateful_set: %s\n",
                str(e),
            )
            raise e
        for np in ret.items:
            nps.append(np.metadata.name)
        return nps

    def get_all_statefulset(self, namespace) -> list[str]:
        """
        Return a list of statefulset names

        :param namespace: find only statefulset in given namespace
        :return: list of statefulset names
        """
        sss = []
        try:
            ret = self.apps_api.list_namespaced_stateful_set(
                namespace, pretty=True
            )
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "AppsV1Api->list_namespaced_stateful_set: %s\n",
                str(e),
            )
            raise e
        for ss in ret.items:
            sss.append(ss.metadata.name)
        return sss

    def get_all_replicasets(self, namespace: str) -> list[str]:
        """
        Return a list of replicasets names

        :param namespace: find only replicasets in given namespace
        :return: list of replicasets names
        """
        rss = []
        try:
            ret = self.apps_api.list_namespaced_replica_set(
                namespace, pretty=True
            )
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "AppsV1Api->list_namespaced_replica_set: %s\n",
                str(e),
            )
            raise e
        for rs in ret.items:
            rss.append(rs.metadata.name)
        return rss

    def get_all_services(self, namespace: str) -> list[str]:
        """
        Return a list of service names

        :param namespace: find only services in given namespace
        :return: list of service names
        """
        services = []
        try:
            ret = self.cli.list_namespaced_service(namespace, pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling "
                "CoreV1Api->list_namespaced_service: %s\n",
                str(e),
            )
            raise e
        for serv in ret.items:
            services.append(serv.metadata.name)
        return services

    # Outputs a json blob with informataion about all pods in a given namespace
    def get_all_pod_info(
        self,
        namespace: str = "default",
        label_selector: str = None,
        field_selector: str = None,
    ) -> list[str]:
        """
        Get details of all pods in a namespace

        :param namespace: namespace (optional default `default`)
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"

        :return list of pod details
        """
        try:
            if label_selector:
                ret = self.list_continue_helper(
                    self.cli.list_namespaced_pod,
                    namespace,
                    pretty=True,
                    label_selector=label_selector,
                    limit=self.request_chunk_size,
                    field_selector=field_selector,
                )
            else:
                ret = self.list_continue_helper(
                    self.cli.list_namespaced_pod,
                    namespace,
                    limit=self.request_chunk_size,
                    field_selector=field_selector,
                )
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_namespaced_pod: %s\n"
                % e
            )

        return ret

    # to be tested, return value not sure

    def get_pod_shell(
        self, pod_name: str, namespace: str, container: str = None
    ) -> Optional[str]:
        """
        Gets the shell running on a Pod. Currently checking against
        /bin/bash and /bin/sh.

        :param pod_name: pod where the command must be executed
        :param namespace: namespace of the pod
        :param container: container where the command
            must be executed (optional default `None`)
        """
        try:
            ret = self.__exec_cmd_in_pod_unsafe(
                ['test -f /bin/bash && echo "True"'],
                pod_name,
                namespace,
                container,
                None,
                True,
                True,
            )
            if ret != "":
                return "bash"
        except Exception:
            pass

        try:
            ret = self.__exec_cmd_in_pod_unsafe(
                ['test -f /bin/sh && echo "True"'],
                pod_name,
                namespace,
                container,
                None,
                True,
                False,
            )

            if ret != "":
                return "sh"
        except Exception:
            pass

        return None

    def exec_cmd_in_pod(
        self,
        command: list[str],
        pod_name: str,
        namespace: str,
        container: str = None,
        base_command: str = None,
        std_err: bool = True,
    ) -> str:
        """
        Executes a base command and its parameters
        in a pod or a container

        :param command: command parameters list or full command string
            if the command must be piped to `bash -c`
            (in that case `base_command` parameter
            must is omitted`)
        :param pod_name: pod where the command must be executed
        :param namespace: namespace of the pod
        :param container: container where the command
            must be executed (optional default `None`)
        :param base_command: base command that must be executed
            along the parameters (optional, default `bash -c` is tested and if
            not present will fallback on `sh -c` )
        :return: the command stdout
        """
        try:
            shell = self.get_pod_shell(pod_name, namespace, container)
            if not shell:
                raise Exception(
                    "impossible to determine the shell to run command"
                )

            if shell == "bash":
                return self.__exec_cmd_in_pod_unsafe(
                    command,
                    pod_name,
                    namespace,
                    container,
                    base_command,
                    std_err,
                    run_on_bash=True,
                )

            return self.__exec_cmd_in_pod_unsafe(
                command,
                pod_name,
                namespace,
                container,
                base_command,
                std_err,
                run_on_bash=False,
            )
        except Exception as e:
            logging.error(f"failed to execute command: {e}")
            raise e

    def __exec_cmd_in_pod_unsafe(
        self,
        command: list[str],
        pod_name: str,
        namespace: str,
        container: str = None,
        base_command: str = None,
        std_err: bool = True,
        run_on_bash=True,
    ) -> str:
        """
        PRIVATE
        Executes a base command and its parameters
        in a pod or a container


        :param command: command parameters list or full command string
            if the command must be piped to `bash -c`
            (in that case `base_command` parameter
            must is omitted`)
        :param pod_name: pod where the command must be executed
        :param namespace: namespace of the pod
        :param container: container where the command
            must be executed (optional default `None`)
        :param base_command: base command that must be executed
            along the parameters (optional, default `bash -c`)
        :param run_on_bash: if True and base_command is null
         will execute `command` on `bash -c` otherwise on `sh -c`
        :return: the command stdout
        """
        exec_command = []
        # this check makes no sense since the type has been declared in the
        # method signature, but unfortunately python do not enforce on type
        # checks at compile time so this check
        # ensures that the command variable is actually a list.
        if not isinstance(command, list):
            command = [command]

        if base_command is None:
            if run_on_bash:
                exec_command = ["bash", "-c"]
            else:
                exec_command = ["sh", "-c"]
            exec_command.extend(command)
        else:
            exec_command = [base_command]
            exec_command.extend(command)

        try:
            if container:
                ret = stream(
                    self.cli.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    container=container,
                    command=exec_command,
                    stderr=std_err,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
            else:
                ret = stream(
                    self.cli.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=exec_command,
                    stderr=std_err,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
        except Exception as e:
            raise e
        # apparently stream API doesn't rise an Exception
        # if the command fails to be executed

        if "OCI runtime exec failed" in ret:
            raise Exception(ret)

        return ret

    def exec_command_on_node(
        self,
        node_name: str,
        command: [str],
        exec_pod_name: str,
        exec_pod_namespace: str = "default",
        exec_pod_container: str = None,
    ) -> str:
        """
        Creates a privileged pod on a specific node and
        executes a command on it to affect the node itself.
        The pod mounts also the dbus socket /run/dbus/system_bus_socket
        to exec kernel related commands like timedatectl.
        To see the pod spec check the template on
        src/krkn_lib/k8s/templates/

        :param node_name: the name of the node where the command will be
            executed
        :param command: the command and the options to be executed
            as a list of strings eg. ["ls", "-al"]
        :param exec_pod_name: the name of the pod that will be created
        :param exec_pod_namespace: the namespace where the pod will be created
            (default "default")
        :param exec_pod_container: the container of the pod on which
            the pod will be executed (default None)
        :return: the command output
        """

        file_loader = PackageLoader("krkn_lib.k8s", "templates")
        env = Environment(loader=file_loader, autoescape=True)
        pod_template = env.get_template("node_exec_pod.j2")
        pod_body = yaml.safe_load(
            pod_template.render(nodename=node_name, podname=exec_pod_name)
        )

        logging.info(
            f"Creating pod to exec command {command} on node {node_name}"
        )
        try:
            self.create_pod(pod_body, exec_pod_namespace, 500)
        except Exception as e:
            logging.error(
                f"failed to create pod {exec_pod_name} on node {node_name},"
                f" namespace: {exec_pod_namespace}"
            )
            raise e

        while not self.is_pod_running(exec_pod_name, exec_pod_namespace):
            time.sleep(5)
            continue
        try:
            response = self.exec_cmd_in_pod(
                command,
                exec_pod_name,
                exec_pod_namespace,
                exec_pod_container,
            )
            return response
        except Exception as e:
            raise e

    def delete_pod(self, name: str, namespace: str = "default"):
        """
        Delete a pod in a namespace

        :param name: pod name
        :param namespace: namespace (optional default `default`)
        """
        try:
            starting_creation_timestamp = self.cli.read_namespaced_pod(
                name=name, namespace=namespace
            ).metadata.creation_timestamp
            self.cli.delete_namespaced_pod(name=name, namespace=namespace)

            while self.cli.read_namespaced_pod(name=name, namespace=namespace):

                ending_creation_timestamp = self.cli.read_namespaced_pod(
                    name=name, namespace=namespace
                ).metadata.creation_timestamp
                if starting_creation_timestamp != ending_creation_timestamp:
                    break
                time.sleep(1)
        except ApiException as e:
            if e.status == 404:
                return
            else:
                logging.error("Failed to delete pod %s", str(e))
                raise e

    def create_pod(self, body: any, namespace: str, timeout: int = 120):
        """
        Create a pod in a namespace

        :param body: an object representation of a valid pod yaml manifest
        :param namespace: namespace where the pod is created
        :param timeout: request timeout
        """
        try:
            pod_stat = None
            pod_stat = self.cli.create_namespaced_pod(
                body=body, namespace=namespace
            )
            end_time = time.time() + timeout
            while True:
                pod_stat = self.cli.read_namespaced_pod(
                    name=body["metadata"]["name"], namespace=namespace
                )
                if pod_stat.status.phase == "Running":
                    break
                if time.time() > end_time:
                    raise Exception("Starting pod failed")
                time.sleep(1)
        except Exception as e:
            logging.error("Pod creation failed %s", str(e))
            if pod_stat:
                logging.error(pod_stat.status.container_statuses)
            self.delete_pod(body["metadata"]["name"], namespace)
            raise e

    def read_pod(self, name: str, namespace: str = "default") -> client.V1Pod:
        """
        Read a pod definition

        :param name: pod name
        :param namespace: namespace (optional default `default`)
        :return: V1Pod definition of the pod
        """
        return self.cli.read_namespaced_pod(name=name, namespace=namespace)

    def get_pod_log(
        self, name: str, namespace: str = "default"
    ) -> HTTPResponse:
        """
        Read the logs from a pod

        :param name: pod name
        :param namespace: namespace (optional default `default`)
        :return: pod logs
        """
        return self.cli.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            _return_http_data_only=True,
            _preload_content=False,
        )

    def get_containers_in_pod(
        self, pod_name: str, namespace: str = "default"
    ) -> list[str]:
        """
        Get container names of a pod

        :param pod_name: pod name
        :param namespace: namespace (optional default `default`)
        :return: a list of container names
        """
        pod_info = self.cli.read_namespaced_pod(pod_name, namespace)
        container_names = []

        for cont in pod_info.spec.containers:
            container_names.append(cont.name)
        return container_names

    def delete_job(
        self, name: str, namespace: str = "default"
    ) -> client.V1Status:
        """
        Delete a job from a namespace

        :param name: job name
        :param namespace: namespace (optional default `default`)
        :return: V1Status API object
        """
        try:
            api_response = self.batch_cli.delete_namespaced_job(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground", grace_period_seconds=0
                ),
            )
            logging.debug("Job deleted. status='%s'", str(api_response.status))
            return api_response
        except ApiException as api:
            logging.warning(
                "Exception when calling "
                "BatchV1Api->create_namespaced_job: %s",
                api,
            )
            logging.warning("Job already deleted\n")
        except Exception as e:
            logging.error(
                "Exception when calling "
                "BatchV1Api->delete_namespaced_job: %s\n",
                str(e),
            )
            raise e

    def create_job(
        self, body: any, namespace: str = "default"
    ) -> client.V1Job:
        """
        Create a job in a namespace

        :param body: an object representation of a valid job yaml manifest
        :param namespace: namespace (optional default `default`),
            `Note:` if namespace is specified in the body won't
            override
        :return: V1Job API object
        """
        try:
            api_response = self.batch_cli.create_namespaced_job(
                body=body, namespace=namespace
            )
            return api_response
        except ApiException as api:
            logging.warning(
                "Exception when calling BatchV1Api->create_job: %s", api
            )
            if api.status == 409:
                logging.warning("Job already present")
        except Exception as e:
            logging.error(
                "Exception when calling "
                "BatchV1Api->create_namespaced_job: %s",
                str(e),
            )
            raise e

    def create_manifestwork(
        self, body: any, namespace: str = "default"
    ) -> object:
        """
        Create an open cluster management manifestwork in a namespace.
        ManifestWork is used to define a group of Kubernetes resources
        on the hub to be applied to the managed cluster.

        :param body: an object representation of
            a valid manifestwork yaml manifest
        :param namespace: namespace (optional default `default`)
        :return: a custom object representing the newly created manifestwork
        """

        try:
            api_response = (
                self.custom_object_client.create_namespaced_custom_object(
                    group="work.open-cluster-management.io",
                    version="v1",
                    plural="manifestworks",
                    body=body,
                    namespace=namespace,
                )
            )
            return api_response
        except ApiException as e:
            print(
                "Exception when calling "
                "CustomObjectsApi->create_namespaced_custom_object: %s\n",
                str(e),
            )

    def delete_manifestwork(self, namespace: str):
        """
        Delete a manifestwork from a namespace

        :param namespace: namespace from where the manifestwork must be deleted
        :return: a custom object representing the deleted resource
        """

        try:
            api_response = (
                self.custom_object_client.delete_namespaced_custom_object(
                    group="work.open-cluster-management.io",
                    version="v1",
                    plural="manifestworks",
                    name="managedcluster-scenarios-template",
                    namespace=namespace,
                )
            )
            return api_response
        except ApiException as e:
            print(
                "Exception when calling "
                "CustomObjectsApi->delete_namespaced_custom_object: %s\n",
                str(e),
            )

    def get_job_status(
        self, name: str, namespace: str = "default"
    ) -> client.V1Job:
        """
        Get a job status

        :param name: job name
        :param namespace: namespace (optional default `default`)
        :return: V1Job API object
        """
        try:
            return self.batch_cli.read_namespaced_job_status(
                name=name, namespace=namespace
            )
        except Exception as e:
            logging.error(
                "Exception when calling "
                "BatchV1Api->read_namespaced_job_status: %s\n",
                str(e),
            )
            raise

    def monitor_nodes(
        self,
    ) -> (bool, list[str]):
        """
        Monitor the status of the cluster nodes
        and set the status to true or false

        :return: cluster status and a list of node names
        """
        nodes = self.list_nodes()
        notready_nodes = []
        node_kerneldeadlock_status = "False"
        for node in nodes:
            try:
                node_info = self.cli.read_node_status(node, pretty=True)
            except ApiException as e:
                logging.error(
                    "Exception when calling "
                    "CoreV1Api->read_node_status: %s\n",
                    str(e),
                )
                raise e
            for condition in node_info.status.conditions:
                if condition.type == "KernelDeadlock":
                    node_kerneldeadlock_status = condition.status
                elif condition.type == "Ready":
                    node_ready_status = condition.status
                else:
                    continue
            if (
                node_kerneldeadlock_status != "False"
                or node_ready_status != "True"
            ):  # noqa  # noqa
                notready_nodes.append(node)
        if len(notready_nodes) != 0:
            status = False
        else:
            status = True
        return status, notready_nodes

    def monitor_namespace(self, namespace: str) -> (bool, list[str]):
        """
        Monitor the status of the pods in the specified namespace
        and set the status to true or false

        :param namespace: namespace
        :return: the list of pods and the status
            (if one or more pods are not running False otherwise True)
        """
        pods = self.list_pods(namespace)
        notready_pods = []
        for pod in pods:
            try:
                pod_info = self.cli.read_namespaced_pod_status(
                    pod, namespace, pretty=True
                )
            except ApiException as e:
                logging.error(
                    "Exception when calling "
                    "CoreV1Api->read_namespaced_pod_status: %s\n",
                    str(e),
                )
                raise e
            pod_status = pod_info.status.phase
            if (
                pod_status != "Running"
                and pod_status != "Completed"
                and pod_status != "Succeeded"
            ):
                notready_pods.append(pod)
        if len(notready_pods) != 0:
            status = False
        else:
            status = True
        return status, notready_pods

    def monitor_component(
        self, iteration: int, component_namespace: str
    ) -> (bool, list[str]):
        """
        Monitor component namespace

        :param iteration: iteration number
        :param component_namespace: namespace
        :return: the status of the component namespace
        """

        watch_component_status, failed_component_pods = self.monitor_namespace(
            component_namespace
        )
        logging.info(
            "Iteration %s: %s: %s",
            iteration,
            component_namespace,
            watch_component_status,
        )
        return watch_component_status, failed_component_pods

    def apply_yaml(self, path, namespace="default") -> list[str]:
        """
        Apply yaml config to create Kubernetes resources

        :param path:  path to the YAML file
        :param namespace: namespace to create
            the resource (optional default `default`)
        :return: the list of names of created objects
        """
        try:
            return utils.create_from_yaml(
                self.api_client, yaml_file=path, namespace=namespace
            )
        except Exception as e:
            logging.error("Error trying to apply_yaml" + str(e))

    def get_pod_info(
        self,
        name: str,
        namespace: str = "default",
        delete_expected: bool = False,
    ) -> Optional[Pod]:
        """
        Retrieve information about a specific pod


        :param name: pod name
        :param namespace: namespace (optional default `default`)
        :return: Data class object of type Pod with the output of the above
            kubectl command in the given format if the pod exists.
            Returns None if the pod doesn't exist
        """
        try:
            pod_info = None
            response = self.cli.read_namespaced_pod(
                name=name, namespace=namespace, pretty="true"
            )
            if response:
                container_list = []

                # Create a list of containers present in the pod
                for container in response.spec.containers:
                    volume_mount_list = []
                    for volume_mount in container.volume_mounts:
                        volume_mount_list.append(
                            VolumeMount(
                                name=volume_mount.name,
                                mountPath=volume_mount.mount_path,
                            )
                        )
                    container_list.append(
                        Container(
                            name=container.name,
                            image=container.image,
                            volumeMounts=volume_mount_list,
                        )
                    )

                for i, container in enumerate(
                    response.status.container_statuses
                ):
                    container_list[i].ready = container.ready
                    container_list[i].containerId = (
                        response.status.container_statuses[i].container_id
                    )

                # Create a list of volumes associated with the pod
                volume_list = []
                for volume in response.spec.volumes:
                    volume_name = volume.name
                    pvc_name = (
                        volume.persistent_volume_claim.claim_name
                        if volume.persistent_volume_claim is not None
                        else None
                    )
                    volume_list.append(
                        Volume(name=volume_name, pvcName=pvc_name)
                    )

                # Create the Pod data class object
                pod_info = Pod(
                    name=response.metadata.name,
                    podIP=response.status.pod_ip,
                    namespace=response.metadata.namespace,
                    containers=container_list,
                    nodeName=response.spec.node_name,
                    volumes=volume_list,
                    status=response.status.phase,
                    creation_timestamp=response.metadata.creation_timestamp,
                )
        except Exception:
            if not delete_expected:
                logging.error(
                    "Pod '%s' doesn't exist in namespace '%s'", name, namespace
                )
            else:
                logging.info(
                    "Pod '%s' doesn't exist in namespace '%s'", name, namespace
                )
            return None
        return pod_info

    def check_if_namespace_exists(self, name: str) -> bool:
        """
        Check if a namespace exists by parsing through

        :param name: namespace name
        :return: boolean value indicating whether
            the namespace exists or not
        """

        v1_projects = self.dyn_client.resources.get(
            api_version="v1", kind="Namespace"
        )
        project_list = v1_projects.get()
        return True if name in str(project_list) else False

    def check_if_pod_exists(
        self, name: str, namespace: str = "default"
    ) -> bool:
        """
        Check if a pod exists in the given namespace

        :param name: pod name
        :param namespace: namespace (optional default `default`)
        :return: boolean value indicating whether the pod exists or not
        """

        namespace_exists = self.check_if_namespace_exists(namespace)
        if namespace_exists:
            pod_list = self.list_pods(namespace=namespace)
            if name in pod_list:
                return True
        else:
            logging.error("Namespace '%s' doesn't exist", str(namespace))
        return False

    def check_if_pvc_exists(
        self, name: str, namespace: str = "default"
    ) -> bool:
        """
        Check if a PVC exists by parsing through the list of projects.

        :param name: PVC name
        :param namespace: namespace (optional default `default`)
        :return: boolean value indicating whether
            the Persistent Volume Claim exists or not
        """

        namespace_exists = self.check_if_namespace_exists(namespace)
        if namespace_exists:
            response = self.cli.list_namespaced_persistent_volume_claim(
                namespace=namespace
            )
            pvc_list = [pvc.metadata.name for pvc in response.items]
            if name in pvc_list:
                return True
        else:
            logging.error("Namespace '%s' doesn't exist", str(namespace))
        return False

    def get_pvc_info(self, name: str, namespace: str) -> PVC:
        """
        Retrieve information about a Persistent Volume Claim in a
        given namespace

        :param name: name of the persistent volume claim
        :param namespace: namespace (optional default `default`)
        :return: A PVC data class containing the name, capacity, volume name,
            namespace and associated pod names
            of the PVC if the PVC exists
            Returns None if the PVC doesn't exist
        """

        pvc_exists = self.check_if_pvc_exists(name=name, namespace=namespace)
        if pvc_exists:
            pvc_info_response = (
                self.cli.read_namespaced_persistent_volume_claim(
                    name=name, namespace=namespace, pretty=True
                )
            )
            pod_list_response = self.cli.list_namespaced_pod(
                namespace=namespace
            )

            capacity = pvc_info_response.status.capacity["storage"]
            volume_name = pvc_info_response.spec.volume_name

            # Loop through all pods in the namespace to find associated PVCs
            pvc_pod_list = []
            for pod in pod_list_response.items:
                for volume in pod.spec.volumes:
                    if (
                        volume.persistent_volume_claim is not None
                        and volume.persistent_volume_claim.claim_name == name
                    ):
                        pvc_pod_list.append(pod.metadata.name)

            pvc_info = PVC(
                name=name,
                capacity=capacity,
                volumeName=volume_name,
                podNames=pvc_pod_list,
                namespace=namespace,
            )
            return pvc_info
        else:
            logging.error(
                "PVC '%s' doesn't exist in namespace '%s'",
                str(name),
                str(namespace),
            )
            return None

    def find_kraken_node(self) -> str:
        """
        Find the node kraken is deployed on
        Set global kraken node to not delete

        :return: node where kraken is running (`None` if not found)
        """
        pods = self.get_all_pods()
        kraken_pod_name = None
        node_name = None
        kraken_project = None

        for pod in pods:
            if "kraken-deployment" in pod[0]:
                kraken_pod_name = pod[0]
                kraken_project = pod[1]
                break
        # have to switch to proper project

        if kraken_pod_name:
            # get kraken-deployment pod, find node name
            try:
                node_name = self.get_pod_info(
                    kraken_pod_name, kraken_project
                ).nodeName
            except Exception as e:
                logging.info("%s", str(e))
                raise e
        return node_name

    def watch_node_status(
        self, node: str, status: str, timeout: int, affected_node: AffectedNode
    ):
        """
        Watch for a specific node status

        :param node: node name
        :param status: status of the resource
        :param timeout: timeout
        :param resource_version: version of the resource
        """
        count = timeout
        timer_start = time.time()
        for event in self.watch_resource.stream(
            self.cli.list_node,
            field_selector=f"metadata.name={node}",
            timeout_seconds=timeout,
        ):
            conditions = [
                status
                for status in event["object"].status.conditions
                if status.type == "Ready"
            ]
            if conditions[0].status == status:
                self.watch_resource.stop()
                break
            else:
                count -= 1
                logging.info(
                    "Status of node %s: %s",
                    node,
                    str(conditions[0].status),
                )
            if not count:
                self.watch_resource.stop()
        end_time = time.time()
        affected_node.set_affected_node_status(status, end_time - timer_start)
        return affected_node

    #
    # TODO: Implement this with a watcher instead of polling
    def watch_managedcluster_status(
        self, managedcluster: str, status: str, timeout: int
    ) -> bool:
        """
        Watch for a specific managedcluster status

        :param managedcluster: managedcluster name
        :param status: status of the resource
        :param timeout: timeout
        :return: boolean value indicating if the timeout occurred
        """
        elapsed_time = 0
        while True:
            conditions = (
                self.custom_object_client.get_cluster_custom_object_status(
                    "cluster.open-cluster-management.io",
                    "v1",
                    "managedclusters",
                    managedcluster,
                )["status"]["conditions"]
            )
            available = list(
                filter(
                    lambda condition: condition["reason"]
                    == "ManagedClusterAvailable",
                    conditions,
                )
            )
            if status == "True":
                if available and available[0]["status"] == "True":
                    logging.info(
                        "Status of managedcluster %s: Available",
                        managedcluster,
                    )
                    return True
            else:
                if not available:
                    logging.info(
                        "Status of managedcluster %s: Unavailable",
                        managedcluster,
                    )
                    return True
            time.sleep(2)
            elapsed_time += 2
            if elapsed_time >= timeout:
                logging.info(
                    "Timeout waiting for managedcluster %s to become: %s",
                    managedcluster,
                    status,
                )
                return False

    def get_node_resource_version(self, node: str) -> str:
        """
        Get the resource version for the specified node

        :param node: node name
        :return: resource version
        """
        return self.cli.read_node(name=node).metadata.resource_version

    def list_ready_nodes(self, label_selector: str = None) -> list[str]:
        """
        Returns a list of ready nodes

        :param label_selector: filter by label
            selector (optional default `None`)
        :return: a list of node names
        """

        nodes = []
        try:
            if label_selector:
                ret = self.cli.list_node(
                    pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_node(pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_node: %s\n", str(e)
            )
            raise e
        for node in ret.items:
            for cond in node.status.conditions:
                if str(cond.type) == "Ready" and str(cond.status) == "True":
                    nodes.append(node.metadata.name)

        return nodes

    def list_schedulable_nodes(self, label_selector: str = None) -> list[str]:
        """
        Lists all the nodes that do not have `NoSchedule` or `NoExecute` taints
        and where pods can be scheduled
        :param label_selector: a label selector to filter the nodes
        :return: a list of node names
        """
        nodes = []
        try:
            if label_selector:
                ret = self.cli.list_node(
                    pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_node(pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_node: %s\n", str(e)
            )
            raise e
        for node in ret.items:
            if node.spec.taints:
                try:
                    for taint in node.spec.taints:
                        if taint.effect in ["NoSchedule", "NoExecute"]:
                            raise Exception
                except Exception:
                    continue
            nodes.append(node.metadata.name)
        return nodes

    # TODO: is the signature correct? the method
    #  returns a list of nodes and the signature name is `get_node`
    def get_node(
        self, node_name: str, label_selector: str, instance_kill_count: int
    ) -> list[str]:
        """
        Gets active node(s)

        :param node_name: node name
        :param label_selector: filter by label
        :param instance_kill_count:
        :return: active node(s)
        """
        if node_name in self.list_ready_nodes():
            return [node_name]
        elif node_name:
            logging.info(
                "Node with provided node_name "
                "does not exist or the node might "
                "be in NotReady state."
            )
        nodes = self.list_ready_nodes(label_selector)
        if not nodes:
            raise Exception(
                "Ready nodes with the provided label selector do not exist"
            )
        logging.info(
            "Ready nodes with the label selector %s: %s", label_selector, nodes
        )
        number_of_nodes = len(nodes)
        if instance_kill_count == number_of_nodes:
            return nodes
        nodes_to_return = []
        for i in range(instance_kill_count):
            node_to_add = nodes[random.randint(0, len(nodes) - 1)]
            nodes_to_return.append(node_to_add)
            nodes.remove(node_to_add)
        return nodes_to_return

    def get_all_kubernetes_object_count(
        self, objects: list[str]
    ) -> dict[str, int]:
        objects_found = dict[str, int]()
        objects_found.update(
            self.get_kubernetes_core_objects_count("v1", objects)
        )
        objects_found.update(self.get_kubernetes_custom_objects_count(objects))
        return objects_found

    def path_exists_in_pod(
        self, pod_name: str, container_name: str, namespace: str, path: str
    ) -> bool:
        exists = self.exec_cmd_in_pod(
            [f'test -d {path} && echo "True"'],
            pod_name,
            namespace,
            container_name,
        ).rstrip()
        exists = exists if exists else "False"
        return exists == "True"

    def get_kubernetes_core_objects_count(
        self, api_version: str, objects: list[str]
    ) -> dict[str, int]:
        """
        Counts all the occurrences of Kinds contained in
        the object parameter in the CoreV1 Api

        :param api_version: api version
        :param objects: list of the kinds that must be counted
        :return: a dictionary of Kinds and the number of objects counted
        """

        result = dict[str, int]()

        try:
            resources = self.cli.get_api_resources()
            for resource in resources.resources:
                if resource.kind in objects:
                    if self.api_client:
                        path_params: Dict[str, str] = {}
                        query_params: List[str] = []
                        header_params: Dict[str, str] = {}
                        auth_settings = ["BearerToken"]
                        header_params["Accept"] = (
                            self.api_client.select_header_accept(
                                ["application/json"]
                            )
                        )

                        path = f"/api/{api_version}/{resource.name}"
                        (data) = self.api_client.call_api(
                            path,
                            "GET",
                            path_params,
                            query_params,
                            header_params,
                            response_type="str",
                            auth_settings=auth_settings,
                        )

                        json_obj = ast.literal_eval(data[0])
                        count = len(json_obj["items"])
                        result[resource.kind] = count
        except ApiException:
            pass
        return result

    def get_kubernetes_custom_objects_count(
        self, objects: list[str]
    ) -> dict[str, int]:
        """
        Counts all the occurrences of Kinds contained in
        the object parameter in the CustomObject Api

        :param objects: list of Kinds that must be counted
        :return: a dictionary of Kinds and number of objects counted
        """
        groups = client.ApisApi(self.api_client).get_api_versions().groups
        result = dict[str, int]()
        for api in groups:
            versions = []
            for v in api.versions:
                name = ""
                if (
                    v.version == api.preferred_version.version
                    and len(api.versions) > 1
                ):
                    name += "*"
                name += v.version
                versions.append(name)
            try:
                data = self.get_api_resources_by_group(
                    api.name, api.preferred_version.version
                )
                for resource in data.resources:
                    if resource.kind in objects:
                        cust_cli = self.custom_object_client
                        custom_resource = cust_cli.list_cluster_custom_object(
                            group=api.name,
                            version=api.preferred_version.version,
                            plural=resource.name,
                        )
                        result[resource.kind] = len(custom_resource["items"])

            except Exception:
                pass
        return result

    def get_api_resources_by_group(self, group, version):
        try:
            api_response = self.custom_object_client.get_api_resources(
                group, version
            )
            return api_response
        except Exception:
            pass

        return None

    def get_node_cpu_count(self, node_name: str) -> int:
        """
        Returns the number of cpus of a specified node

        :param node_name: the name of the node
        :return: the number of cpus or 0 if any exception is raised
        """
        api_client = self.api_client

        if api_client:
            try:
                v1 = self.cli
                node = v1.read_node(node_name)
                cpu_capacity = node.status.capacity.get("cpu")
                return int(cpu_capacity)
            except Exception:
                return 0

    def get_node_ip(self, node_name: str):
        """
        Returns the ip address of a node

        :param node_name: the name of the node
        :return: the ip address or None if not found
        """
        api_client = self.api_client
        try:
            if api_client:
                v1 = self.cli
                node = v1.read_node(node_name)
                for address in node.status.addresses:
                    if address.type == "InternalIP":
                        return address.address
                return None
            else:
                return None
        except Exception:
            raise Exception("failed to get node ip address")

    def get_nodes_infos(self) -> (list[NodeInfo], list[Taint]):
        """
        Returns a list of NodeInfo objects
        :return: the list of NodeInfo objects
        """
        instance_type_label = "node.k8s.io/instance-type"
        instance_type_label_alt = "node.kubernetes.io/instance-type"
        node_type_master_label = "node-role.kubernetes.io/master"
        node_type_worker_label = "node-role.kubernetes.io/worker"
        node_type_infra_label = "node-role.kubernetes.io/infra"
        node_type_workload_label = "node-role.kubernetes.io/workload"
        node_type_application_label = "node-role.kubernetes.io/app"
        result = list[NodeInfo]()
        node_index = set[NodeInfo]()
        taints = list[Taint]()
        resp = self.list_continue_helper(
            self.cli.list_node, limit=self.request_chunk_size
        )
        for node_resp in resp:
            for node in node_resp.items:
                node_info = NodeInfo()
                if node.spec.taints is not None:
                    for node_taint in node.spec.taints:
                        taint = Taint()
                        taint.node_name = node.metadata.name
                        taint.effect = node_taint.effect
                        taint.key = node_taint.key
                        taint.value = node_taint.value
                        taints.append(taint)
                if instance_type_label in node.metadata.labels.keys():
                    node_info.instance_type = node.metadata.labels[
                        instance_type_label
                    ]
                elif instance_type_label_alt in node.metadata.labels.keys():
                    node_info.instance_type = node.metadata.labels[
                        instance_type_label_alt
                    ]
                else:
                    node_info.instance_type = "unknown"

                if node_type_infra_label in node.metadata.labels.keys():
                    node_info.nodes_type = "infra"
                elif node_type_worker_label in node.metadata.labels.keys():
                    node_info.nodes_type = "worker"
                elif node_type_master_label in node.metadata.labels.keys():
                    node_info.nodes_type = "master"
                elif node_type_workload_label in node.metadata.labels.keys():
                    node_info.nodes_type = "workload"
                elif (
                    node_type_application_label in node.metadata.labels.keys()
                ):
                    node_info.nodes_type = "application"
                else:
                    node_info.nodes_type = "unknown"

                node_info.architecture = node.status.node_info.architecture
                node_info.architecture = node.status.node_info.architecture
                node_info.kernel_version = node.status.node_info.kernel_version
                node_info.kubelet_version = (
                    node.status.node_info.kubelet_version
                )
                node_info.os_version = node.status.node_info.os_image
                if node_info in node_index:
                    result[result.index(node_info)].count += 1
                else:
                    node_index.add(node_info)
                    result.append(node_info)
        return result, taints

    def delete_file_from_pod(
        self, pod_name: str, container_name: str, namespace: str, filename: str
    ):
        """
        Deletes a file from a pod

        :param pod_name: pod name
        :param container_name: container name
        :param namespace: namespace of the pod
        :param filename: full-path of the file that
            will be removed from the pod
        """
        try:
            # delete the backup file
            rm_command = [
                "-f",
                filename,
            ]
            self.exec_cmd_in_pod(
                rm_command,
                pod_name,
                namespace,
                container_name,
                "rm",
            )
        except Exception as e:
            raise ApiException(str(e))

    def get_archive_volume_from_pod_worker(
        self,
        pod_name: str,
        container_name: str,
        namespace: str,
        remote_archive_path: str,
        remote_archive_prefix: str,
        local_download_path: str,
        local_file_prefix: str,
        queue: Queue,
        queue_size: int,
        downloaded_file_list: list[(int, str)],
        delete_remote_after_download: bool,
        thread_number: int,
        safe_logger: SafeLogger,
    ):
        """
        Download worker for the create_download_multipart_archive
        method. The method will dequeue from the thread-safe queue
        parameter until the queue will be empty and will download
        the i-th tar volume popped from the queue itself.
        the file will be downloaded in base64 string format in order
        to avoid archive corruptions caused by the Kubernetes WebSocket API.


        :param pod_name: pod name from which the tar volume
            must be downloaded
        :param container_name: container name from which the
            tar volume be downloaded
        :param namespace: namespace of the pod
        :param remote_archive_path: remote path where the archive volume
            is stored
        :param remote_archive_prefix: prefix of the file used to
            create the archive.to this prefix will be appended sequential
            number of the archive assigned to
            the worker in a two digit format and the tar exception
            (ex for a prefix like prefix - the remote filename
            will become prefix-00.tar)
        :param local_download_path: local path where the tar volume
            will be download
        :param local_file_prefix: local prefix to apply to the
            local file downloaded.To the prefix will be appended the
            sequential number of the archive assigned to the worker
            and the extension tar.b64
        :param queue: the queue from which the sequential
            number wil be popped
        :param queue_size: total size of the queue
        :param downloaded_file_list: the list of
            archive number and local filename  downloaded
            file will be appended once the download terminates
            shared between the threads
        :param delete_remote_after_download: if set True once
            the download will terminate the remote file will be deleted.
        :param thread_number: the assigned thread number
        :param safe_logger: SafeLogger class, will allow thread-safe
            logging
        """
        while not queue.empty():
            file_number = queue.get()
            if not isinstance(file_number, int):
                safe_logger.error(
                    f"[Thread #{thread_number}] wrong queue "
                    f"element format, download failed"
                )
                return

            local_file_name = (
                f"{local_download_path}/{local_file_prefix}"
                f"{file_number:02d}.tar.b64"
            )
            remote_file_name = (
                f"{remote_archive_path}/{remote_archive_prefix}part."
                f"{file_number:02d}"
            )

            try:
                with open(local_file_name, "x") as file_buffer:
                    base64_dump = [
                        "base64",
                        remote_file_name,
                    ]
                    resp = stream(
                        self.cli.connect_get_namespaced_pod_exec,
                        pod_name,
                        namespace,
                        container=container_name,
                        command=base64_dump,
                        stderr=False,
                        stdin=False,
                        stdout=True,
                        tty=False,
                        _preload_content=False,
                    )

                    while resp.is_open():
                        resp.update(timeout=1)
                        if resp.peek_stdout():
                            out = resp.read_stdout()
                            file_buffer.write(out)
                    resp.close()
                    file_buffer.flush()
                    file_buffer.seek(0)
                    downloaded_file_list.append((file_number, local_file_name))
                    safe_logger.info(
                        f"[Thread #{thread_number}] : "
                        f"{queue.unfinished_tasks-1}/"
                        f"{queue_size} "
                        f"{local_file_name} downloaded "
                    )

            except Exception as e:
                safe_logger.error(
                    f"[Thread #{thread_number}]: failed "
                    f"to download {remote_file_name}"
                    f" from pod: {pod_name}, "
                    f"container: {container_name}, "
                    f"namespace: {namespace}"
                    f" with exception: {str(e)}. Aborting download."
                )
            finally:
                queue.task_done()
                if delete_remote_after_download:
                    try:
                        # delete the backup file
                        self.delete_file_from_pod(
                            pod_name,
                            container_name,
                            namespace,
                            remote_file_name,
                        )
                    except Exception as e:
                        safe_logger.error(
                            f"[Thread #{thread_number}]: failed to "
                            f"remove remote archive "
                            f"{remote_file_name}: {str(e)}"
                        )

    def archive_and_get_path_from_pod(
        self,
        pod_name: str,
        container_name: str,
        namespace: str,
        remote_archive_path: str,
        target_path: str,
        archive_files_prefix: str,
        download_path: str = "/tmp",
        archive_part_size: int = 30000,
        max_threads: int = 5,
        safe_logger: SafeLogger = None,
    ) -> list[(int, str)]:
        """
        Archives and downloads a folder content
        from container in a base64 tarball.
        The function is designed to leverage multi-threading
        in order to maximize the download speed.
        a `max_threads` number of `download_archive_part_from_pod`
        calls will be made in parallel.

        :param pod_name: pod name from which the folder
            must be downloaded
        :param container_name: container name from which the
            folder must be downloaded
        :param namespace: namespace of the pod
        :param remote_archive_path: path in the container
            where the temporary archive
            will be stored (will be deleted once the download
            terminates, must be writable
            and must have enough space to temporarly store the archive)
        :param target_path: the path that will be archived
            and downloaded from the container
        :param archive_files_prefix: prefix string that will be added
            to the files
        :param download_path: the local path
            where the archive will be saved
        :param archive_part_size: the archive will be split into multiple
            files of the specified `archive_part_size`
        :param max_threads: maximum number of threads that will be launched
        :param safe_logger: SafeLogger, if omitted a default SafeLogger will
            be instantiated that will simply use the logging package
            to print logs to stdout.
        :return: the list of the archive number and filenames downloaded
        """
        if safe_logger is None:
            safe_logger = SafeLogger()

        remote_archive_prefix = f"{archive_files_prefix}-"
        local_file_prefix = remote_archive_prefix
        queue = Queue()
        downloaded_files = list[(int, str)]()
        try:
            # create the folder archive splitting
            # in tar files of size `chunk_size`
            # due to pipes and scripts the command is executed in

            if not os.path.isdir(download_path):
                os.mkdir(download_path)
            if not self.path_exists_in_pod(
                pod_name, container_name, namespace, remote_archive_path
            ):
                raise Exception("remote archive path does not exist")

            if not self.path_exists_in_pod(
                pod_name, container_name, namespace, target_path
            ):
                raise Exception("remote target path does not exist")

            # to support busybox (minimal) split naming options
            # we first split with the default suffix (aa, ab, ac etc.)
            tar_command = (
                f"tar cpf >(split -a 2 -b {archive_part_size}k - "
                f"{remote_archive_path}/{remote_archive_prefix}part.)"
                f" -C {target_path} . --exclude {remote_archive_prefix}*"
            )

            safe_logger.info("creating data archive, please wait....")
            self.exec_cmd_in_pod(
                [tar_command],
                pod_name,
                namespace,
                container_name,
            )
            # and then we rename the filenames replacing
            # suffix letters with numbers
            rename_command = (
                f"COUNTER=0; for i in "
                f"`ls {remote_archive_path}/{remote_archive_prefix}*`; "
                f"do mv $i {remote_archive_path}/{remote_archive_prefix}part."
                f"`printf '%02d' $COUNTER`; COUNTER=$((COUNTER+1)); done"
            )

            self.exec_cmd_in_pod(
                [rename_command],
                pod_name,
                namespace,
                container_name,
            )

            # count how many tar files has been created
            count_files_command = (
                f"ls {remote_archive_path}/{remote_archive_prefix}* | wc -l"
            )

            archive_file_number = self.exec_cmd_in_pod(
                [count_files_command],
                pod_name,
                namespace,
                container_name,
            )

            for i in range(int(archive_file_number)):
                queue.put(i)
            queue_size = queue.qsize()
            for i in range(max_threads):
                worker = threading.Thread(
                    target=self.get_archive_volume_from_pod_worker,
                    args=(
                        pod_name,
                        container_name,
                        namespace,
                        remote_archive_path,
                        remote_archive_prefix,
                        download_path,
                        local_file_prefix,
                        queue,
                        queue_size,
                        downloaded_files,
                        True,
                        i,
                        safe_logger,
                    ),
                )
                worker.daemon = True
                worker.start()
            queue.join()
        except Exception as e:
            safe_logger.error(
                f"failed to create archive {target_path} on pod: {pod_name}, "
                f"container: {container_name}, namespace:{namespace} "
                f"with exception: {str(e)}"
            )
            raise e

        return downloaded_files

    def is_pod_running(self, pod_name: str, namespace: str) -> bool:
        """
        Checks if a pod and all its containers are running

        :param pod_name:str: the name of the pod to check
        :param namespace:str: the namespace of the pod to check
        :return: True if is running or False if not
        """
        try:
            response = self.cli.read_namespaced_pod(
                name=pod_name, namespace=namespace, pretty="true"
            )

            is_ready = True

            for status in response.status.container_statuses:
                if not status.ready:
                    is_ready = False
            return is_ready
        except Exception:
            return False

    def is_pod_terminating(self, pod_name: str, namespace: str) -> bool:
        """
        Checks if a pod is scheduled for deletion so it's terminating

        :param pod_name:str: the name of the pod to check
        :param namespace:str: the namespace of the pod to check
        :return: True if is Terminating or False if not
        """
        try:
            response = self.cli.read_namespaced_pod(
                name=pod_name, namespace=namespace, pretty="true"
            )
            if response.metadata.deletion_timestamp:
                return True

            return False
        except Exception:
            return False

    def collect_and_parse_cluster_events(
        self,
        start_timestamp: int,
        end_timestamp: int,
        local_timezone: str,
        cluster_timezone: str = "UTC",
        limit: int = 500,
        namespace: str = None,
    ) -> list[ClusterEvent]:
        """
        Collects cluster events querying `/api/v1/events`
        filtered in a given time interval and writes them in
        a temporary file in json format.

        :param start_timestamp: timestamp of the minimum date
            after that the event is relevant
        :param end_timestamp: timestamp of the maximum date
            before that the event is relevant
        :param local_timezone: timezone of the local system
        :param cluster_timezone: timezone of the remote cluster
        :param limit: limit of the number of events to be fetched
            from the cluster
        :param namespace: Namespace from which the events must be
            collected, if None all-namespaces will be selected
        :return: Returns a list of parsed ClusterEvents

        """
        events = []
        try:
            if namespace:
                events_list = self.cli.list_namespaced_event(namespace)

            else:
                events_list = self.cli.list_event_for_all_namespaces()
            events_list = events_list.items
            for obj in events_list:
                in_filtered_time = filter_dictionary(
                    obj.first_timestamp,
                    start_timestamp,
                    end_timestamp,
                    cluster_timezone,
                    local_timezone,
                )
                if in_filtered_time:
                    events.append(ClusterEvent(k8s_obj=obj))

        except Exception as e:
            logging.error(str(e))

        return events

    def parse_events_from_file(
        self, events_filename: str
    ) -> Optional[list[ClusterEvent]]:
        if not events_filename or not os.path.exists(events_filename):
            logging.error(f"events file do not exist {events_filename}")
            return

        events = []
        with open(events_filename, "r") as jstream:
            try:
                json_obj = json.load(jstream)
                for event in json_obj:
                    events.append(ClusterEvent(k8s_json_dict=event))
            except Exception:
                logging.error(
                    f"failed to parse events file: {events_filename}"
                )

        return events

    def create_token_for_sa(
        self, namespace: str, service_account: str, token_expiration=43200
    ) -> Optional[str]:
        """
        Creates a token for an existing ServiceAccount in a namespace
        that will expire in <token_expiration> seconds (optional)

        :param namespace: the namespace where the SA belongs
        :param service_account: the name of the SA
        :param token_expiration: the duration of the SA in seconds,
            default 12h
        :return: the token or None if something went wrong.
        """
        body = {
            "kind": "TokenRequest",
            "apiVersion": "authentication.k8s.io/v1",
            "spec": {
                "expirationSeconds": token_expiration,
            },
        }

        path = (
            f"/api/v1/namespaces/{namespace}/"
            f"serviceaccounts/{service_account}/token"
        )

        path_params: Dict[str, str] = {}
        query_params: List[str] = []
        header_params: Dict[str, str] = {}
        auth_settings = ["BearerToken"]
        header_params["Accept"] = self.api_client.select_header_accept(
            ["application/json"]
        )
        try:
            (data) = self.api_client.call_api(
                path,
                "POST",
                path_params,
                query_params,
                header_params,
                body=body,
                response_type="str",
                auth_settings=auth_settings,
            )
            json_obj = ast.literal_eval(data[0])
            return json_obj["status"]["token"]
        except Exception as e:
            logging.error(
                f"failed to create token for SA: {service_account} "
                f"on namespace: {namespace} with error: {e}"
            )
            return None

    def select_pods_by_label(
        self, label_selector: str, field_selector: str = None
    ) -> list[(str, str)]:
        """
        Selects the pods identified by a label_selector

        :param label_selector: a label selector string
            in the format "key=value"
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"
        :return: a list of pod_name and namespace tuples
        """
        pods_and_namespaces = self.get_all_pods(label_selector, field_selector)
        pods_and_namespaces = [(pod[0], pod[1]) for pod in pods_and_namespaces]

        return pods_and_namespaces

    def select_service_by_label(
        self, namespace: str, label_selector: str
    ) -> list[str]:
        """
        Selects all the services marked by a label in the
        format key=value deployed on a namespace

        :param namespace: namespace where the service are searched
        :param label_selector: label selector in the format key=value
        :return: the list of services matching the criteria
        """
        splitted_selector = label_selector.split("=")
        if len(splitted_selector) != 2:
            raise Exception(
                f"{label_selector} not valid, selector must "
                f"be in key=value format"
            )
        services = self.cli.list_namespaced_service(namespace, pretty=True)
        selected_services = []
        for service in services.items:
            for key, value in service.metadata.labels.items():
                if (
                    key == splitted_selector[0]
                    and value == splitted_selector[1]
                ):
                    selected_services.append(service.metadata.name)
        return selected_services

    def select_pods_by_name_pattern_and_namespace_pattern(
        self,
        pod_name_pattern: str,
        namespace_pattern: str,
        field_selector: str = None,
    ) -> list[(str, str)]:
        """
        Selects the pods identified by a namespace_pattern
        and a pod_name pattern.

        :param pod_name_pattern: a pod_name pattern to match
        :param namespace_pattern: a namespace pattern to match
        :param max_timeout: the maximum time in seconds to wait
            before considering the pod "not recovered" after the Chaos
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"
        :return: a list of pod_name and namespace tuples
        """
        namespace_re = re.compile(namespace_pattern)
        podname_re = re.compile(pod_name_pattern)
        namespaces = self.list_namespaces()
        pods_and_namespaces = []
        for namespace in namespaces:
            if namespace_re.match(namespace):
                pods = self.list_pods(namespace, field_selector=field_selector)
                for pod in pods:
                    if podname_re.match(pod):
                        pods_and_namespaces.append((pod, namespace))

        return pods_and_namespaces

    def select_pods_by_namespace_pattern_and_label(
        self,
        namespace_pattern: str,
        label_selector: str,
        field_selector: str = None,
    ) -> list[(str, str)]:
        """
        Selects the pods identified by a label_selector
        and a namespace pattern

        :param namespace_pattern: a namespace pattern to match
        :param label_selector: a label selector string
            in the format "key=value"
        :param field_selector: filter results by config details
            select only running pods by setting "status.phase=Running"
        :return: a list of pod_name and namespace tuples
        """
        namespace_re = re.compile(namespace_pattern)
        pods_and_namespaces = self.get_all_pods(label_selector, field_selector)
        pods_and_namespaces = [
            (pod[0], pod[1])
            for pod in pods_and_namespaces
            if namespace_re.match(pod[1])
        ]
        return pods_and_namespaces

    def replace_service_selector(
        self, new_selectors: list[str], service_name: str, namespace: str
    ) -> Optional[dict[Any]]:
        """
        Replaces a service selector with one or more new selectors
        Patching the target service

        :param new_selectors: a list of selectors in the format "key=value"
        :param service_name: the service name that needs to be patched
        :param namespace: the namespace of the service

        :return: the original service spec
            (useful to restore it after the scenario)
            returns None if self.api_client hasn't been initialized
        """

        if self.api_client:
            try:
                service = self.cli.read_namespaced_service(
                    service_name, namespace
                )
            except ApiException:
                logging.error(f"{service_name} not found in {namespace}")
                return None
            original_service = self.api_client.sanitize_for_serialization(
                service
            )

            splitted_selectors = [
                s.split("=") for s in new_selectors if len(s.split("=")) == 2
            ]
            selectors = {}
            for selector in splitted_selectors:
                selectors[selector[0]] = selector[1]

            if len(splitted_selectors) == 0:
                return None
            try:
                body = [
                    {
                        "op": "replace",
                        "path": "/spec/selector",
                        "value": selectors,
                    }
                ]
                path_params: Dict[str, str] = {}
                query_params: List[str] = []
                header_params: Dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = self.api_client.select_header_accept(
                    ["application/json"]
                )
                header_params["Content-Type"] = (
                    self.api_client.select_header_accept(
                        ["application/json-patch+json"]
                    )
                )

                path = (
                    f"/api/v1/namespaces/{namespace}/services/"
                    f"{service_name}"
                )
                self.api_client.call_api(
                    path,
                    "PATCH",
                    path_params,
                    query_params,
                    header_params,
                    body=body,
                    response_type="str",
                    auth_settings=auth_settings,
                )

            except ApiException as e:
                logging.error(
                    f"Failed to patch service, "
                    f"Kubernetes Api Exception: {str(e)}"
                )
                raise e
            if "status" in original_service:
                original_service.pop("status")
            if "managedFields" in original_service["metadata"]:
                original_service["metadata"].pop("managedFields")
            if "annotations" in original_service["metadata"]:
                original_service["metadata"].pop("annotations")
            if "creationTimestamp" in original_service["metadata"]:
                original_service["metadata"].pop("creationTimestamp")
            if "resourceVersion" in original_service["metadata"]:
                original_service["metadata"].pop("resourceVersion")
            if "uid" in original_service["metadata"]:
                original_service["metadata"].pop("uid")
            return original_service

        else:
            return None

    def deploy_service_hijacking(
        self,
        namespace: str,
        plan: dict[any],
        image: str,
        port_number: int = 5000,
        port_name: str = "flask",
        stats_route: str = "/stats",
        privileged: bool = True,
    ) -> ServiceHijacking:
        """
        Deploys a pod running the service-hijacking webservice
        along with the test plan deployed in krkn stored in a
        ConfigMap and bound as a file to the container

        :param namespace: The namespace where the Pod and the
            ConfigMap will be deployed
        :param plan: the dictionary converted test plan to be
            executed in the service
        :param image: the image container image of the service
        :param port_number: the port where the pod will be listening
            default 5000
        :param port_name: the port name if the Service is pointing to
            a string name instead of a port number
        :param stats_route: overrides the defautl route where the stats
            action will be mapped, change it only if you have a /stats
            route in your test_plan
        :return: a structure containing all the infos of the
            Pod and the ConfigMap deployment
        """
        pod_name = f"service-hijacking-pod-{get_random_string(5)}"
        config_map_name = f"service-hijacking-cm-{get_random_string(5)}"
        selector_key = "service-hijacking"
        selector_value = f"sh-{get_random_string(5)}"

        file_loader = PackageLoader("krkn_lib.k8s", "templates")
        env = Environment(loader=file_loader, autoescape=True)
        config_map_template = env.get_template(
            "service_hijacking_config_map.j2"
        )
        plan_dump = yaml.dump(plan)
        cm_body = yaml.safe_load(
            config_map_template.render(
                name=config_map_name, namespace=namespace, plan=plan_dump
            )
        )
        self.cli.create_namespaced_config_map(
            namespace=namespace, body=cm_body
        )

        pod_template = env.get_template("service_hijacking_pod.j2")
        pod_body = yaml.safe_load(
            pod_template.render(
                name=pod_name,
                namespace=namespace,
                selector_key=selector_key,
                selector_value=selector_value,
                image=image,
                port_name=port_name,
                config_map_name=config_map_name,
                port_number=port_number,
                stats_route=stats_route,
                privileged=privileged,
            )
        )

        self.create_pod(namespace=namespace, body=pod_body)

        return ServiceHijacking(
            pod_name=pod_name,
            namespace=namespace,
            selector="=".join([selector_key, selector_value]),
            config_map_name=config_map_name,
        )

    def undeploy_service_hijacking(self, service_infos: ServiceHijacking):
        """
        Undeploys the resource created for the ServiceHijacking Scenario

        :param service_infos: the structure returned by the
            deploy_service_hijacking method
        """
        self.delete_pod(service_infos.pod_name, service_infos.namespace)
        self.cli.delete_namespaced_config_map(
            service_infos.config_map_name, service_infos.namespace
        )

    def service_exists(self, service_name: str, namespace: str) -> bool:
        """
        Checks wheter a kubernetes Service exist or not
        :param service_name: the name of the service to check
        :param namespace: the namespace where the service should exist
        :return: True if the service exists, False if not
        """
        try:
            _ = self.cli.read_namespaced_service(service_name, namespace)
            return True
        except ApiException:
            return False

    def deploy_syn_flood(
        self,
        pod_name: str,
        namespace: str,
        image: str,
        target: str,
        target_port: int,
        packet_size: int,
        window_size: int,
        duration: int,
        node_selectors: dict[str, list[str]],
    ):
        """
        Deploys a Pod to run the Syn Flood scenario

        :param pod_name: The name of the pod that will be deployed
        :param namespace: The namespace where the pod will be deployed
        :param image: the syn flood scenario container image
        :param target: the target hostname or ip address
        :param target_port: the target TCP port
        :param packet_size: the SYN packet size in bytes
        :param window_size: the TCP window size in bytes
        :param duration: the duration of the flood in seconds
        :param node_selectors: the node selectors of the node(s) where
            the pod will be scheduled by kubernetes
        """
        file_loader = PackageLoader("krkn_lib.k8s", "templates")
        env = Environment(loader=file_loader, autoescape=True)
        pod_template = env.get_template("syn_flood_pod.j2")
        pod_body = yaml.safe_load(
            pod_template.render(
                name=pod_name,
                namespace=namespace,
                has_node_selectors=len(node_selectors.keys()) > 0,
                node_selectors=node_selectors,
                image=image,
                target=target,
                duration=duration,
                target_port=target_port,
                packet_size=packet_size,
                window_size=window_size,
            )
        )

        self.create_pod(namespace=namespace, body=pod_body)

    def deploy_hog(self, pod_name: str, hog_config: HogConfig):
        """
        Deploys a Pod to run the Syn Flood scenario

        :param pod_name: The name of the pod that will be deployed
        :param hog_config: Hog Configuration
        """
        compiled_regex = re.compile(r"^.+=.*$")
        has_selector = hog_config.node_selector is not None and bool(
            compiled_regex.match(hog_config.node_selector)
        )
        if has_selector:
            node_selector = hog_config.node_selector.split("=")
        else:
            node_selector = {"", ""}
        file_loader = PackageLoader("krkn_lib.k8s", "templates")
        env = Environment(loader=file_loader, autoescape=True)
        io_volume = {"volumes": [hog_config.io_target_pod_volume]}
        yaml_data = yaml.dump(io_volume, default_flow_style=False, indent=2)
        pod_template = env.get_template("hog_pod.j2")
        pod_body = yaml.safe_load(
            pod_template.render(
                name=pod_name,
                namespace=hog_config.namespace,
                hog_type=hog_config.type.value,
                hog_type_io=HogType.io.value,
                has_selector=has_selector,
                node_selector_key=node_selector[0],
                node_selector_value=node_selector[1],
                image=hog_config.image,
                duration=hog_config.duration,
                cpu_load_percentage=hog_config.cpu_load_percentage,
                cpu_method=hog_config.cpu_method,
                io_block_size=hog_config.io_block_size,
                io_write_bytes=hog_config.io_write_bytes,
                io_target_pod_folder=hog_config.io_target_pod_folder,
                io_volume_mount=yaml_data,
                memory_vm_bytes=hog_config.memory_vm_bytes,
                workers=hog_config.workers,
                target_pod_folder=hog_config.io_target_pod_folder,
                tolerations=hog_config.tolerations,
            )
        )

        self.create_pod(namespace=hog_config.namespace, body=pod_body)

    def get_node_resources_info(self, node_name: str) -> NodeResources:
        resources = NodeResources()
        path_params: dict[str, str] = {}
        query_params: list[str] = []
        header_params: dict[str, str] = {}
        auth_settings = ["BearerToken"]
        header_params["Accept"] = self.api_client.select_header_accept(
            ["application/json"]
        )
        path = f"/api/v1/nodes/{node_name}/proxy/stats/summary"
        (data) = self.api_client.call_api(
            path,
            "GET",
            path_params,
            query_params,
            header_params,
            response_type="str",
            auth_settings=auth_settings,
        )

        json_obj = ast.literal_eval(data[0])
        resources.cpu = json_obj["node"]["cpu"]["usageNanoCores"]
        resources.memory = json_obj["node"]["memory"]["availableBytes"]
        resources.disk_space = json_obj["node"]["fs"]["availableBytes"]
        return resources

    def get_container_ids(self, pod_name: str, namespace: str) -> list[str]:
        """
        Gets the container ids of the selected pod
        :param pod_name: name of the pod
        :param namespace: namespace of the pod

        :return: a list of container id
        """

        container_ids: list[str] = []

        pod = self.get_pod_info(pod_name, namespace)
        if pod:
            for container in pod.containers:
                container_ids.append(
                    re.sub(r".*://", "", container.containerId)
                )
        return container_ids

    def get_pod_pids(
        self,
        base_pod_name: str,
        base_pod_namespace: str,
        base_pod_container_name: str,
        pod_name: str,
        pod_namespace: str,
        pod_container_id: str,
    ) -> Optional[list[str]]:
        """
        Retrieves the PIDs assigned to the pod in the node. The command
        must be executed inside a privileged Pod with `hostPID` set to true

        :param base_pod_name: name of the pod where the command is run
        :param base_pod_namespace: namespace of the pod
            where the command is run
        :param base_pod_container_name: container name of the pod
            where the command is run
        :param pod_name: Pod name associated with the PID
        :param pod_namespace: namespace of the Pod associated with the PID
        :param pod_container_id: container id of Pod associated with the PID

        :return: list of pids None.
        """

        if not self.check_if_pod_exists(base_pod_name, base_pod_namespace):
            raise Exception(
                f"base pod {base_pod_name} does not exist in "
                f"namespace {base_pod_namespace}"
            )
        if not self.check_if_pod_exists(pod_name, pod_namespace):
            raise Exception(
                f"target pod {pod_name} does not exist in "
                f"namespace {pod_namespace}"
            )

        cmd = (
            f"for dir in /proc/[0-9]*; do grep -q {pod_container_id}  "
            f"$dir/cgroup 2>/dev/null "
            "&& echo ${dir/\/proc\//}; done"  # NOQA
        )

        pids = self.exec_cmd_in_pod(
            [cmd],
            base_pod_name,
            base_pod_namespace,
            base_pod_container_name,
        )
        if pids:
            pids_list = pids.split("\n")
            pids_list = list(filter(None, pids_list))
            return pids_list
        return None

    def list_pod_network_interfaces(
        self, pod_name: str, namespace: str, container_name: str = None
    ) -> list[str]:
        """
        Lists the network interfaces of a pod (Linux only)
        :param pod_name: the name of the pod
        :param namespace: the namespaces of the pod
        :param container_name: the container of the pod where the interfaces
            will be listed, if None the first will be picked
        :return: the list of the interfaces
        """

        if not self.check_if_pod_exists(pod_name, namespace):
            raise Exception(
                f"target pod {pod_name} does not exist in "
                f"namespace {namespace}"
            )

        cmd = "ls /sys/class/net"
        nics_str = self.exec_cmd_in_pod(
            [cmd],
            pod_name,
            namespace,
            container_name,
        )
        nics = nics_str.split("\n")
        try:
            nics.remove("lo")
            nics.remove("")
        except ValueError:
            pass
        return nics
