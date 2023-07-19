import logging
import re
import time
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional
import ast
import arcaflow_lib_kubernetes
import kubernetes
import os
import random
from kubernetes import client, config, utils, watch
from kubeconfig import KubeConfig
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.client import DynamicClient
from kubernetes.stream import stream
from urllib3 import HTTPResponse

from .resources import (
    PVC,
    ChaosEngine,
    ChaosResult,
    Container,
    LitmusChaosObject,
    Pod,
    Volume,
    VolumeMount,
    ApiRequestException,
    NodeInfo,
)

SERVICE_TOKEN_FILENAME = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SERVICE_CERT_FILENAME = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
class KrknLibKubernetes:
    """ """

    api_client: client.ApiClient = None
    cli: client.CoreV1Api = None
    batch_cli: client.BatchV1Api = None
    watch_resource: watch.Watch = None
    custom_object_client: client.CustomObjectsApi = None
    dyn_client: kubernetes.dynamic.client.DynamicClient = None

    def __init__(
        self, kubeconfig_path: str = None, *, kubeconfig_string: str = None
    ):
        """
        KrknLibKubernetes Constructor. Can be invoked with kubeconfig_path
        or, optionally, with a kubeconfig in string
        format using the keyword argument

        :param kubeconfig_path: kubeconfig path
        :param kubeconfig_string: (keyword argument)
               kubeconfig in string format

        Initialization with kubeconfig path:

        >>> KrknLibKubernetes("/home/test/.kube/config")

        Initialization with kubeconfig string:

        >>> kubeconfig_string="apiVersion: v1 ....."
        >>> KrknLibKubernetes(kubeconfig_string=kubeconfig_string)
        """

        if kubeconfig_string is not None and kubeconfig_path is not None:
            raise Exception(
                "please use either a kubeconfig path "
                "or a valid kubeconfig string"
            )

        if kubeconfig_string is not None:
            self.__initialize_clients_from_kconfig_string(kubeconfig_string)
        else:
            self.__initialize_clients(kubeconfig_path)

    def __del__(self):
        self.api_client.rest_client.pool_manager.clear()
        self.api_client.close()

    # Load kubeconfig and initialize kubernetes python client
    def __initialize_clients(self, kubeconfig_path: str = None):
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
                kube_addr = os.environ.get('KUBERNETES_PORT_443_TCP_ADDR')
                kube_port = os.environ.get('KUBERNETES_PORT_443_TCP_PORT')
                conf = KubeConfig()
                conf.set_cluster(name='krkn-cluster', server=f'https://{kube_addr}:{kube_port}', certificate_authority=SERVICE_CERT_FILENAME,)
                conf.set_credentials(name='user', token=content[0])
                conf.set_context(name='krkn-context', cluster='krkn-cluster', user='user')
                conf.use_context('krkn-context')            

        try:
            config.load_kube_config(kubeconfig_path)
            self.api_client = client.ApiClient()
            self.k8s_client = config.new_client_from_config(config_file=kubeconfig_path)
            self.cli = client.CoreV1Api(self.k8s_client)
            self.batch_cli = client.BatchV1Api(self.k8s_client)
            self.custom_object_client = client.CustomObjectsApi(self.k8s_client)
            self.dyn_client = DynamicClient(self.k8s_client)
            self.watch_resource = watch.Watch()
        except OSError:
            raise Exception(
                "Invalid kube-config file: {0}. "
                "No configuration found.".format(kubeconfig_path)
            )

    def __initialize_clients_from_kconfig_string(
        self,
        kubeconfig_str: str,
    ):
        """
        Initialize all clients from kubeconfig yaml string

        :param kubeconfig_str: kubeconfig in string format
        """

        try:
            kubeconfig = arcaflow_lib_kubernetes.parse_kubeconfig(
                kubeconfig_str
            )
            connection = arcaflow_lib_kubernetes.kubeconfig_to_connection(
                kubeconfig, True
            )
            self.api_client = arcaflow_lib_kubernetes.connect(connection)
            self.cli = client.CoreV1Api(self.api_client)
            self.batch_cli = client.BatchV1Api(self.api_client)
            self.watch_resource = watch.Watch()
            self.custom_object_client = client.CustomObjectsApi(
                self.api_client
            )
            self.dyn_client = DynamicClient(self.api_client)
        except ApiException as e:
            logging.error(
                "Failed to initialize kubernetes client: %s\n", str(e)
            )
            raise e
        except Exception as e:
            logging.error("failed to validate kubeconfig: %s\n", str(e))
            raise e

    def get_host(self) -> str:
        """
        Returns the Kubernetes server URL
        :return: kubernetes server URL
        """

        return self.cli.api_client.configuration.get_default_copy().host

    def get_clusterversion_string(self) -> str:
        """
        Return clusterversion status text on OpenShift, empty string
        on other distributions

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
                    if condition["type"] == "Progressing":
                        return condition["message"]
            return ""
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return ""
            else:
                raise e

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
            if label_selector:
                ret = self.cli.list_namespace(
                    pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_namespace(pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_namespaced_pod: %s\n",
                str(e),
            )
            raise e
        for namespace in ret.items:
            namespaces.append(namespace.metadata.name)
        return namespaces

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
        using kubernetes python client

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
        """"""
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
                ret = self.cli.list_node(
                    pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_node(pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_node: %s\n", str(e)
            )
            raise ApiRequestException(str(e))
        for node in ret.items:
            nodes.append(node.metadata.name)
        return nodes

    # TODO: refactoring to work both in kubernetes and OpenShift
    def list_killable_nodes(self, label_selector: str = None) -> list[str]:
        """
        List nodes in the cluster that can be killed (OpenShift only)

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

    #
    def list_pods(
        self, namespace: str, label_selector: str = None
    ) -> list[str]:
        """
        List pods in the given namespace

        :param namespace: namespace to search for pods
        :param label_selector: filter by label selector
                               (optional default `None`)
        :return: a list of pod names
        """
        pods = []
        try:
            if label_selector:
                ret = self.cli.list_namespaced_pod(
                    namespace, pretty=True, label_selector=label_selector
                )
            else:
                ret = self.cli.list_namespaced_pod(namespace, pretty=True)
        except ApiException as e:
            logging.error(
                "Exception when calling CoreV1Api->list_namespaced_pod: %s\n",
                str(e),
            )
            raise e
        for pod in ret.items:
            pods.append(pod.metadata.name)
        return pods

    def get_all_pods(self, label_selector: str = None) -> list[[str, str]]:
        """
        Return a list of tuples containing pod name [0] and namespace [1]
        :param label_selector: filter by label_selector
                               (optional default `None`)
        :return: list of tuples pod,namespace
        """
        pods = []
        if label_selector:
            ret = self.cli.list_pod_for_all_namespaces(
                pretty=True, label_selector=label_selector
            )
        else:
            ret = self.cli.list_pod_for_all_namespaces(pretty=True)
        for pod in ret.items:
            pods.append([pod.metadata.name, pod.metadata.namespace])
        return pods

    # to be tested, return value not sure
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
        Execute a base command and its parameters
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
            exec_command = ["bash", "-c"]
            exec_command.extend(command)
        else:
            exec_command.append(base_command)
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
            logging.error("failed to exec command on pod %s", str(e))
            raise e
        return ret

    def delete_pod(self, name: str, namespace: str = "default"):
        """
        Delete a pod in a namespace

        :param name: pod name
        :param namespace: namespace (optional default `default`)
        """
        try:
            self.cli.delete_namespaced_pod(name=name, namespace=namespace)
            while self.cli.read_namespaced_pod(name=name, namespace=namespace):
                time.sleep(1)
        except ApiException as e:
            if e.status == 404:
                logging.info("Pod already deleted")
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
                          overridden
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

        return utils.create_from_yaml(
            self.api_client, yaml_file=path, namespace=namespace
        )

    def get_pod_info(self, name: str, namespace: str = "default") -> Pod:
        """
        Retrieve information about a specific pod
        :param name: pod name
        :param namespace: namespace (optional default `default`)
        :return: Data class object of type Pod with the output of the above
                 kubectl command in the given format if the pod exists.
                 Returns None if the pod doesn't exist
        """

        pod_exists = self.check_if_pod_exists(name=name, namespace=namespace)
        if pod_exists:
            response = self.cli.read_namespaced_pod(
                name=name, namespace=namespace, pretty="true"
            )
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

            for i, container in enumerate(response.status.container_statuses):
                container_list[i].ready = container.ready

            # Create a list of volumes associated with the pod
            volume_list = []
            for volume in response.spec.volumes:
                volume_name = volume.name
                pvc_name = (
                    volume.persistent_volume_claim.claim_name
                    if volume.persistent_volume_claim is not None
                    else None
                )
                volume_list.append(Volume(name=volume_name, pvcName=pvc_name))

            # Create the Pod data class object
            pod_info = Pod(
                name=response.metadata.name,
                podIP=response.status.pod_ip,
                namespace=response.metadata.namespace,
                containers=container_list,
                nodeName=response.spec.node_name,
                volumes=volume_list,
            )
            return pod_info
        else:
            logging.error(
                "Pod '%s' doesn't exist in namespace '%s'", name, namespace
            )
            return None

    def get_litmus_chaos_object(
        self, kind: str, name: str, namespace: str = "default"
    ) -> LitmusChaosObject:
        """

        :param kind: the custom resource type
        :param name: the object name
        :param namespace: the namespace (optional default `default`)
        :return: data class object of a subclass of LitmusChaosObject
        """

        group = "litmuschaos.io"
        version = "v1alpha1"

        if kind.lower() == "chaosengine":
            plural = "chaosengines"
            response = self.custom_object_client.get_namespaced_custom_object(
                group=group,
                plural=plural,
                version=version,
                namespace=namespace,
                name=name,
            )
            try:
                engine_status = response["status"]["engineStatus"]
                exp_status = response["status"]["experiments"][0]["status"]
            except Exception:
                engine_status = "Not Initialized"
                exp_status = "Not Initialized"
            custom_object = ChaosEngine(
                kind="ChaosEngine",
                group=group,
                namespace=namespace,
                name=name,
                plural=plural,
                version=version,
                engineStatus=engine_status,
                expStatus=exp_status,
            )
        elif kind.lower() == "chaosresult":
            plural = "chaosresults"
            response = self.custom_object_client.get_namespaced_custom_object(
                group=group,
                plural=plural,
                version=version,
                namespace=namespace,
                name=name,
            )
            try:
                verdict = response["status"]["experimentStatus"]["verdict"]
                fail_step = response["status"]["experimentStatus"]["failStep"]
            except Exception:
                verdict = "N/A"
                fail_step = "N/A"
            custom_object = ChaosResult(
                kind="ChaosResult",
                group=group,
                namespace=namespace,
                name=name,
                plural=plural,
                version=version,
                verdict=verdict,
                failStep=fail_step,
            )
        else:
            logging.error("Invalid litmus chaos custom resource name")
            custom_object = None
        return custom_object

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
        :return:
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
        self, node: str, status: str, timeout: int, resource_version: str
    ):
        """
        Watch for a specific node status

        :param node: node name
        :param status: status of the resource
        :param timeout: timeout
        :param resource_version: version of the resource
        """
        count = timeout
        for event in self.watch_resource.stream(
            self.cli.list_node,
            field_selector=f"metadata.name={node}",
            timeout_seconds=timeout,
            resource_version=f"{resource_version}",
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

    #
    # TODO: Implement this with a watcher instead of polling
    def watch_managedcluster_status(
        self, managedcluster: str, status: str, timeout: int
    ):
        """
        Watch for a specific managedcluster status
        :param managedcluster: managedcluster name
        :param status: status of the resource
        :param timeout: timeout
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

    # TODO: is the signature correct? the method
    #  returns a list of nodes and the signature name is `get_node`
    def get_node(
        self, node_name: str, label_selector: str, instance_kill_count: int
    ) -> list[str]:
        """
        Returns active node(s)

        :param node_name: node name
        :param label_selector: filter by label
        :param instance_kill_count:
        :return:
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
        api_client = self.api_client
        resources = self.get_api_resources_by_group("", "v1")
        result = dict[str, int]()

        for resource in resources.resources:
            if resource.kind in objects:
                if api_client:
                    try:
                        path_params: Dict[str, str] = {}
                        query_params: List[str] = []
                        header_params: Dict[str, str] = {}
                        auth_settings = ["BearerToken"]
                        header_params[
                            "Accept"
                        ] = api_client.select_header_accept(
                            ["application/json"]
                        )

                        path = f"/api/{api_version}/{resource.name}"
                        (data) = api_client.call_api(
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
                    except ApiException as e:
                        logging.warning("ApiException -> %s", str(e))
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
        custom_object_api = client.CustomObjectsApi(self.api_client)
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
                        custom_resource = (
                            custom_object_api.list_cluster_custom_object(
                                group=api.name,
                                version=api.preferred_version.version,
                                plural=resource.name,
                            )
                        )
                        result[resource.kind] = len(custom_resource["items"])

            except Exception as e:
                logging.warning("CustomObjectsApi -> %s", str(e))
        return result

    def get_api_resources_by_group(self, group, version):
        api_client = self.api_client
        if api_client:
            try:
                path_params: Dict[str, str] = {}
                query_params: List[str] = []
                header_params: Dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = f"/apis/{group}/{version}"
                if group == "":
                    path = f"/api/{version}"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="V1APIResourceList",
                    auth_settings=auth_settings,
                )
                return data[0]
            except Exception as e:
                logging.warning("V1ApiException -> %s", str(e))

        return None

    def get_nodes_infos(self) -> list[NodeInfo]:
        """
        Returns a list of NodeInfo objects
        :return:
        """
        instance_type_label = "node.kubernetes.io/instance-type"
        node_type_master_label = "node-role.kubernetes.io/master"
        node_type_worker_label = "node-role.kubernetes.io/worker"
        node_type_infra_label = "node-role.kubernetes.io/infra"
        node_type_workload_label = "node-role.kubernetes.io/workload"
        node_type_application_label = "node-role.kubernetes.io/app"
        result = list[NodeInfo]()
        resp = self.cli.list_node()
        for node in resp.items:
            node_info = NodeInfo()
            if instance_type_label in node.metadata.labels.keys():
                node_info.instance_type = node.metadata.labels[
                    instance_type_label
                ]
            else:
                node_info.instance_type = "unknown"

            if node_type_infra_label in node.metadata.labels.keys():
                node_info.node_type = "infra"
            elif node_type_worker_label in node.metadata.labels.keys():
                node_info.node_type = "worker"
            elif node_type_master_label in node.metadata.labels.keys():
                node_info.node_type = "master"
            elif node_type_workload_label in node.metadata.labels.keys():
                node_info.node_type = "workload"
            elif node_type_application_label in node.metadata.labels.keys():
                node_info.node_type = "application"
            else:
                node_info.node_type = "unknown"

            node_info.architecture = node.status.node_info.architecture
            node_info.kernel_version = node.status.node_info.kernel_version
            node_info.kubelet_version = node.status.node_info.kubelet_version
            node_info.os_version = node.status.node_info.os_image
            result.append(node_info)

        return result

    def get_cluster_infrastructure(self) -> str:
        """
        Get the cluster Cloud infrastructure name when available
        :return: the cluster infrastructure name or `Unknown` when unavailable
        """
        api_client = self.api_client
        if api_client:
            try:
                path_params: Dict[str, str] = {}
                query_params: List[str] = []
                header_params: Dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/config.openshift.io/v1/infrastructures/cluster"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                json_obj = ast.literal_eval(data[0])
                return json_obj["status"]["platform"]
            except Exception as e:
                logging.warning("V1ApiException -> %s", str(e))
                return "Unknown"

        return None

    def get_cluster_network_plugins(self) -> list[str]:
        """
        Get the cluster Cloud network plugins list
        :return: the cluster infrastructure name or `Unknown` when unavailable
        """
        api_client = self.api_client
        network_plugins = list[str]()
        if api_client:
            try:
                path_params: Dict[str, str] = {}
                query_params: List[str] = []
                header_params: Dict[str, str] = {}
                auth_settings = ["BearerToken"]
                header_params["Accept"] = api_client.select_header_accept(
                    ["application/json"]
                )

                path = "/apis/config.openshift.io/v1/networks"
                (data) = api_client.call_api(
                    path,
                    "GET",
                    path_params,
                    query_params,
                    header_params,
                    response_type="str",
                    auth_settings=auth_settings,
                )
                json_obj = ast.literal_eval(data[0])
                for plugin in json_obj["items"]:
                    network_plugins.append(plugin["status"]["networkType"])
            except Exception as e:
                logging.warning("V1ApiException -> %s", str(e))
                network_plugins.append("Unknown")

    def get_ocp_prometheus_data(self) -> Optional[str]:
        prometheus_pod_name = "prometheus-k8s-0"
        prometheus_namespace = "openshift-monitoring"
        prometheus_backup_name = "krkn_prometheus_backup.tar.gz"
        prometheus_pod = self.get_pod_info(
            prometheus_pod_name, prometheus_namespace
        )
        if not prometheus_pod:
            return None
        try:
            # create backup folder
            logging.info("creating backup folder")
            create_directory_command = [
                "-p",
                "/prometheus/backup/prometheus",
            ]

            self.exec_cmd_in_pod(
                create_directory_command,
                prometheus_pod_name,
                prometheus_namespace,
                "prometheus",
                "mkdir",
            )

            # copy all prometheus files in the backup directory using
            # the find + cp trick
            # can be removed and added the --ignore-failed-read to the tar
            copy_all_files_command = [
                "/prometheus/",
                "-not",
                "-path",
                "/prometheus/",
                "-not",
                "-path",
                "/prometheus/backup/*",
                "-not",
                "-path",
                "/prometheus/backup",
                "-exec",
                "cp",
                "-R",
                "{}",
                "/prometheus/backup{}",
                ";",
            ]
            logging.info(
                "copying prometheus files in backup folder, please wait...."
            )
            self.exec_cmd_in_pod(
                copy_all_files_command,
                prometheus_pod_name,
                prometheus_namespace,
                "prometheus",
                "/usr/bin/find",
            )

            # create the prometheus archive
            targz_backup_folder_command = [
                "cfz",
                f"/prometheus/{prometheus_backup_name}",
                "-C",
                "/prometheus/backup/prometheus/",
                ".",
            ]
            logging.info("creating prometheus data archive, please wait....")
            self.exec_cmd_in_pod(
                targz_backup_folder_command,
                prometheus_pod_name,
                prometheus_namespace,
                "prometheus",
                "tar",
            )

            # stream the prometheus archive as base64 string
            with NamedTemporaryFile(delete=False) as file_buffer:
                logging.info(
                    f"downloading backup from prometheus pod in {file_buffer.name}, please wait...."
                )
                cat_command = [
                    "base64",
                    f"/prometheus/{prometheus_backup_name}",
                ]
                resp = stream(
                    self.cli.connect_get_namespaced_pod_exec,
                    prometheus_pod_name,
                    prometheus_namespace,
                    container="prometheus",
                    command=cat_command,
                    stderr=False,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )

                print(file_buffer.name)
                while resp.is_open():
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        out = resp.read_stdout()
                        # print("STDOUT: %s" % len(out))
                        file_buffer.write(out.encode("utf-8"))
                resp.close()

                file_buffer.flush()
                file_buffer.seek(0)
                return file_buffer.name
        except Exception as e:
            print(str(e))

        # finally delete
