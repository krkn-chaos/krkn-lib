import logging
import re
import time
import arcaflow_lib_kubernetes
from kubernetes import client, config, utils, watch
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.client import DynamicClient
from kubernetes.stream import stream


from .resources import (
    PVC,
    ChaosEngine,
    ChaosResult,
    Container,
    LitmusChaosObject,
    Pod,
    Volume,
    VolumeMount,
)


# Load kubeconfig and initialize kubernetes python client
def initialize_clients(kubeconfig_path: str = None):
    """
    Initialize all clients from kubeconfig path

    :param kubeconfig_path: kubeconfig path,
           (optional default KUBE_CONFIG_DEFAULT_LOCATION)
    """
    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION

    try:
        f = open(kubeconfig_path)
        with f:
            kubeconfig_str = f.read()
            initialize_clients_from_kconfig_string(str(kubeconfig_str))

    except OSError:
        raise Exception(
            f"Invalid kube-config file: {kubeconfig_path}. "
            "No configuration found."
        )


def initialize_clients_from_kconfig_string(
    kubeconfig_str: str,
):
    """
    Initialize all clients from kubeconfig yaml string

    :param kubeconfig_str: kubeconfig in string format
    """
    global cli
    global batch_cli
    global watch_resource
    global api_client
    global dyn_client
    global custom_object_client

    try:
        kubeconfig = arcaflow_lib_kubernetes.parse_kubeconfig(kubeconfig_str)
        connection = arcaflow_lib_kubernetes.kubeconfig_to_connection(
            kubeconfig, True
        )
        api_client = arcaflow_lib_kubernetes.connect(connection)
        cli = client.CoreV1Api(api_client)
        batch_cli = client.BatchV1Api(api_client)
        watch_resource = watch.Watch()
        custom_object_client = client.CustomObjectsApi(api_client)
        dyn_client = DynamicClient(api_client)
    except ApiException as e:
        logging.error(f"Failed to initialize kubernetes client: {e}\n")
        raise e
    except Exception as e:
        logging.error(f"failed to validate kubeconfig: {e}\n")
        raise e


def get_host() -> str:
    """
    Returns the Kubernetes server URL
    :return: kubernetes server URL
    """

    return cli.api_client.configuration.Configuration.get_default_copy().host


def get_clusterversion_string() -> str:
    """
    Return clusterversion status text on OpenShift, empty string
    on other distributions

    :return: clusterversion status
    """

    try:
        cvs = custom_object_client.list_cluster_custom_object(
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
            raise


#
def list_namespaces(label_selector: str = None) -> list[str]:
    """
    List all namespaces

    :param label_selector: filter by label selector (optional default `None`)
    :return: list of namespaces names
    """

    namespaces = []
    try:
        if label_selector:
            ret = cli.list_namespace(
                pretty=True, label_selector=label_selector
            )
        else:
            ret = cli.list_namespace(pretty=True)
    except ApiException as e:
        logging.error(
            f"Exception when calling CoreV1Api->list_namespaced_pod: {e}\n"
        )
        raise e
    for namespace in ret.items:
        namespaces.append(namespace.metadata.name)
    return namespaces


def get_namespace_status(namespace_name: str) -> str:
    """
    Get status of a given namespace

    :param namespace_name: namespace name
    :return: namespace status
    """

    ret = ""
    try:
        ret = cli.read_namespace_status(namespace_name)
    except ApiException as e:
        logging.error(
            f"Exception when calling CoreV1Api->read_namespace_status: {e}\n"
        )
    return ret.status.phase


def delete_namespace(namespace: str) -> client.V1Status:
    """
    Delete a given namespace using kubernetes python client

    :param namespace: namespace name
    :return: V1Status API object
    """

    try:
        api_response = cli.delete_namespace(namespace)
        logging.debug(
            f"Namespace deleted. status='{str(api_response.status)}'"
        )
        return api_response

    except Exception as e:
        logging.error(
            "Exception when calling CoreV1Api->delete_namespace: {e}\n"
        )
        raise e


def check_namespaces(
    namespaces: list[str], label_selector: str = None
) -> list[str]:
    """
    Check if all the watch_namespaces are valid

    :param namespaces: list of namespaces to check
    :param label_selector: filter by label_selector (optional default `None`)
    :return: a list of matching namespaces
    """
    """"""
    try:
        valid_namespaces = list_namespaces(label_selector)
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
            raise Exception(
                f"There exists no namespaces matching: {invalid_namespaces}"
            )
        return list(final_namespaces)
    except Exception as e:
        logging.error(f"{e}")
        raise e


#
def list_nodes(label_selector: str = None) -> list[str]:
    """
    List nodes in the cluster

    :param label_selector: filter by label selector (optional default `None`)
    :return: a list of node names
    """
    nodes = []
    try:
        if label_selector:
            ret = cli.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_node(pretty=True)
    except ApiException as e:
        logging.error(f"Exception when calling CoreV1Api->list_node: {e}\n")
        raise e
    for node in ret.items:
        nodes.append(node.metadata.name)
    return nodes


#
def list_killable_nodes(label_selector: str = None) -> list[str]:
    """
    List nodes in the cluster that can be killed

    :param label_selector: filter by label selector (optional default `None`)
    :return: a list of node names that can be killed
    """
    nodes = []
    kraken_node_name = find_kraken_node()
    try:
        if label_selector:
            ret = cli.list_node(pretty=True, label_selector=label_selector)
        else:
            ret = cli.list_node(pretty=True)
    except ApiException as e:
        logging.error(f"Exception when calling CoreV1Api->list_node: {e}\n")
        raise e
    for node in ret.items:
        if kraken_node_name != node.metadata.name:
            for cond in node.status.conditions:
                if str(cond.type) == "Ready" and str(cond.status) == "True":
                    nodes.append(node.metadata.name)
    return nodes


def list_killable_managedclusters(label_selector: str = None) -> list[str]:
    """
    List managed clusters attached to the hub that can be killed

    :param label_selector: filter by label selector (optional default `None`)
    :return: a list of managed clusters names
    """
    managedclusters = []
    try:
        ret = custom_object_client.list_cluster_custom_object(
            group="cluster.open-cluster-management.io",
            version="v1",
            plural="managedclusters",
            label_selector=label_selector,
        )
    except ApiException as e:
        logging.error(
            f"Exception when calling "
            f"CustomObjectsApi->list_cluster_custom_object: {e}\n"
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
def list_pods(namespace: str, label_selector: str = None) -> list[str]:
    """
    List pods in the given namespace

    :param namespace: namespace to search for pods
    :param label_selector: filter by label selector (optional default `None`)
    :return: a list of pod names
    """
    pods = []
    try:
        if label_selector:
            ret = cli.list_namespaced_pod(
                namespace, pretty=True, label_selector=label_selector
            )
        else:
            ret = cli.list_namespaced_pod(namespace, pretty=True)
    except ApiException as e:
        logging.error(
            f"Exception when calling CoreV1Api->list_namespaced_pod: {e}\n"
        )
        raise e
    for pod in ret.items:
        pods.append(pod.metadata.name)
    return pods


def get_all_pods(label_selector: str = None) -> list[[str, str]]:
    """
    Return a list of tuples containing pod name [0] and namespace [1]
    :param label_selector: filter by label_selector (optional default `None`)
    :return: list of tuples pod,namespace
    """
    pods = []
    if label_selector:
        ret = cli.list_pod_for_all_namespaces(
            pretty=True, label_selector=label_selector
        )
    else:
        ret = cli.list_pod_for_all_namespaces(pretty=True)
    for pod in ret.items:
        pods.append([pod.metadata.name, pod.metadata.namespace])
    return pods


# to be tested, return value not sure
def exec_cmd_in_pod(
    command: list[str],
    pod_name: str,
    namespace: str,
    container: str = None,
    base_command: str = "bash",
) -> str:
    """
    Execute a base command and its parameters
    in a pod or a container

    :param command: command parameters
    :param pod_name: pod where the command must be executed
    :param namespace: namespace of the pod
    :param container: container where the command
           must be executed (optional default `None`)
    :param base_command: base command that must be executed
           along the parameters (optional, default `bash`)
    :return: the command stdout
    """
    exec_command = [base_command, "-c", command]
    try:
        if container:
            ret = stream(
                cli.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                container=container,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
        else:
            ret = stream(
                cli.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
    except Exception as e:
        logging.error(f"failed to exec command on pod {e}")
        raise e
    return ret


def delete_pod(name: str, namespace: str = "default"):
    """
    Delete a pod in a namespace

    :param name: pod name
    :param namespace: namespace (optional default `default`)
    """
    try:
        cli.delete_namespaced_pod(name=name, namespace=namespace)
        while cli.read_namespaced_pod(name=name, namespace=namespace):
            time.sleep(1)
    except ApiException as e:
        if e.status == 404:
            logging.info("Pod already deleted")
        else:
            logging.error(f"Failed to delete pod {e}")
            raise e


def create_pod(body: any, namespace: str, timeout: int = 120):
    """
    Create a pod in a namespace

    :param body: an object representation of a valid pod yaml manifest
    :param namespace: namespace where the pod is created
    :param timeout: request timeout
    """
    try:
        pod_stat = None
        pod_stat = cli.create_namespaced_pod(body=body, namespace=namespace)
        end_time = time.time() + timeout
        while True:
            pod_stat = cli.read_namespaced_pod(
                name=body["metadata"]["name"], namespace=namespace
            )
            if pod_stat.status.phase == "Running":
                break
            if time.time() > end_time:
                raise Exception("Starting pod failed")
            time.sleep(1)
    except Exception as e:
        logging.error(f"Pod creation failed {e}")
        if pod_stat:
            logging.error(pod_stat.status.container_statuses)
        delete_pod(body["metadata"]["name"], namespace)
        raise e


def read_pod(name: str, namespace: str = "default") -> client.V1Pod:
    """
    Read a pod definition

    :param name: pod name
    :param namespace: namespace (optional default `default`)
    :return: V1Pod definition of the pod
    """
    return cli.read_namespaced_pod(name=name, namespace=namespace)


def get_pod_log(name: str, namespace: str = "default") -> str:
    """
    Read the logs from a pod

    :param name: pod name
    :param namespace: namespace (optional default `default`)
    :return: pod logs
    """
    return cli.read_namespaced_pod_log(
        name=name,
        namespace=namespace,
        _return_http_data_only=True,
        _preload_content=False,
    )


def get_containers_in_pod(
    pod_name: str, namespace: str = "default"
) -> list[str]:
    """
    Get container names of a pod

    :param pod_name: pod name
    :param namespace: namespace (optional default `default`)
    :return: a list of container names
    """
    pod_info = cli.read_namespaced_pod(pod_name, namespace)
    container_names = []

    for cont in pod_info.spec.containers:
        container_names.append(cont.name)
    return container_names


def delete_job(name: str, namespace: str = "default") -> client.V1Status:
    """
    Delete a job from a namespace

    :param name: job name
    :param namespace: namespace (optional default `default`)
    :return: V1Status API object
    """
    try:
        api_response = batch_cli.delete_namespaced_job(
            name=name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                propagation_policy="Foreground", grace_period_seconds=0
            ),
        )
        logging.debug("Job deleted. status='%s'" % str(api_response.status))
        return api_response
    except ApiException as api:
        logging.warning(
            f"Exception when calling BatchV1Api->create_namespaced_job: {api}"
        )
        logging.warning("Job already deleted\n")
    except Exception as e:
        logging.error(
            f"Exception when calling BatchV1Api->delete_namespaced_job: {e}\n"
        )
        raise e


def create_job(body: any, namespace: str = "default") -> client.V1Job:
    """
    Create a job in a namespace
    :param body: an object representation of a valid job yaml manifest
    :param namespace: namespace (optional default `default`)
    :return: V1Job API object
    """
    try:
        api_response = batch_cli.create_namespaced_job(
            body=body, namespace=namespace
        )
        return api_response
    except ApiException as api:
        logging.warning(
            f"Exception when calling BatchV1Api->create_job: {api}"
        )
        if api.status == 409:
            logging.warning("Job already present")
    except Exception as e:
        logging.error(
            f"Exception when calling BatchV1Api->create_namespaced_job: {e}"
        )
        raise e


def create_manifestwork(body: any, namespace: str = "default") -> object:
    """
    Create an open cluster management manifestwork in a namespace.
    ManifestWork is used to define a group of Kubernetes resources
    on the hub to be applied to the managed cluster.

    :param body: an object representation of a valid manifestwork yaml manifest
    :param namespace: namespace (optional default `default`)
    :return: a custom object representing the newly created manifestwork
    """

    try:
        api_response = custom_object_client.create_namespaced_custom_object(
            group="work.open-cluster-management.io",
            version="v1",
            plural="manifestworks",
            body=body,
            namespace=namespace,
        )
        return api_response
    except ApiException as e:
        print(
            f"Exception when calling "
            f"CustomObjectsApi->create_namespaced_custom_object: {e}\n"
        )


def delete_manifestwork(namespace: str):
    """
    Delete a manifestwork from a namespace

    :param namespace: namespace from where the manifestwork must be deleted
    :return: a custom object representing the deleted resource
    """

    try:
        api_response = custom_object_client.delete_namespaced_custom_object(
            group="work.open-cluster-management.io",
            version="v1",
            plural="manifestworks",
            name="managedcluster-scenarios-template",
            namespace=namespace,
        )
        return api_response
    except ApiException as e:
        print(
            f"Exception when calling "
            f"CustomObjectsApi->delete_namespaced_custom_object: {e}\n"
        )


def get_job_status(name: str, namespace: str = "default") -> client.V1Job:
    """
    Get a job status

    :param name: job name
    :param namespace: namespace (optional default `default`)
    :return: V1Job API object
    """
    try:
        return batch_cli.read_namespaced_job_status(
            name=name, namespace=namespace
        )
    except Exception as e:
        logging.error(
            f"Exception when calling "
            f"BatchV1Api->read_namespaced_job_status: {e}\n"
        )
        raise


def monitor_nodes() -> (bool, list[str]):
    """
    Monitor the status of the cluster nodes and set the status to true or false

    :return: cluster status and a list of node names
    """
    nodes = list_nodes()
    notready_nodes = []
    node_kerneldeadlock_status = "False"
    for node in nodes:
        try:
            node_info = cli.read_node_status(node, pretty=True)
        except ApiException as e:
            logging.error(
                f"Exception when calling "
                f"CoreV1Api->read_node_status: {e}\n"
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


def monitor_namespace(namespace: str) -> (bool, list[str]):
    """
    Monitor the status of the pods in the specified namespace
    and set the status to true or false
    :param namespace: namespace
    :return: the list of pods and the status
             (if one or more pods are not running False otherwise True)
    """
    pods = list_pods(namespace)
    notready_pods = []
    for pod in pods:
        try:
            pod_info = cli.read_namespaced_pod_status(
                pod, namespace, pretty=True
            )
        except ApiException as e:
            logging.error(
                f"Exception when calling "
                f"CoreV1Api->read_namespaced_pod_status: {e}\n"
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
    iteration: int, component_namespace: str
) -> (bool, list[str]):
    """
    Monitor component namespace

    :param iteration: iteration number
    :param component_namespace: namespace
    :return: the status of the component namespace
    """

    watch_component_status, failed_component_pods = monitor_namespace(
        component_namespace
    )
    logging.info(
        f"Iteration {iteration}: "
        f"{component_namespace}: {watch_component_status}"
    )
    return watch_component_status, failed_component_pods


def apply_yaml(path, namespace="default") -> list[str]:
    """
    Apply yaml config to create Kubernetes resources

    :param path:  path to the YAML file
    :param namespace: namespace to create
                      the resource (optional default `default`)
    :return: the list of names of created objects
    """

    return utils.create_from_yaml(
        api_client, yaml_file=path, namespace=namespace
    )


def get_pod_info(name: str, namespace: str = "default") -> Pod:
    """
    Retrieve information about a specific pod
    :param name: pod name
    :param namespace: namespace (optional default `default`)
    :return: Data class object of type Pod with the output of the above
             kubectl command in the given format if the pod exists.
             Returns None if the pod doesn't exist
    """

    pod_exists = check_if_pod_exists(name=name, namespace=namespace)
    if pod_exists:
        response = cli.read_namespaced_pod(
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
            f"Pod '{str(name)}' doesn't exist in namespace '{str(namespace)}'"
        )
        return None


def get_litmus_chaos_object(
    kind: str, name: str, namespace: str = "default"
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
        response = custom_object_client.get_namespaced_custom_object(
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
        response = custom_object_client.get_namespaced_custom_object(
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


def check_if_namespace_exists(name: str) -> bool:
    """
    Check if a namespace exists by parsing through
    :param name: namespace name
    :return: boolean value indicating whether
             the namespace exists or not
    """

    v1_projects = dyn_client.resources.get(
        api_version="project.openshift.io/v1", kind="Project"
    )
    project_list = v1_projects.get()
    return True if name in str(project_list) else False


def check_if_pod_exists(name: str, namespace: str = "default") -> bool:
    """
    Check if a pod exists in the given namespace

    :param name: pod name
    :param namespace: namespace (optional default `default`)
    :return:
    """

    namespace_exists = check_if_namespace_exists(namespace)
    if namespace_exists:
        pod_list = list_pods(namespace=namespace)
        if name in pod_list:
            return True
    else:
        logging.error(f"Namespace '{str(namespace)}' doesn't exist")
    return False


def check_if_pvc_exists(name: str, namespace: str = "default") -> bool:
    """
    Check if a PVC exists by parsing through the list of projects.
    :param name: PVC name
    :param namespace: namespace (optional default `default`)
    :return: boolean value indicating whether
             the Persistent Volume Claim exists or not
    """

    namespace_exists = check_if_namespace_exists(namespace)
    if namespace_exists:
        response = cli.list_namespaced_persistent_volume_claim(
            namespace=namespace
        )
        pvc_list = [pvc.metadata.name for pvc in response.items]
        if name in pvc_list:
            return True
    else:
        logging.error(f"Namespace '{str(namespace)}' doesn't exist")
    return False


def get_pvc_info(name: str, namespace: str) -> PVC:
    """
    Retrieve information about a Persistent Volume Claim in a
    given namespace

    :param name: name of the persistent volume claim
    :param namespace: namespace (optional default `default`)
    :return: A PVC data class containing the name, capacity, volume name,
             namespace and associated pod names of the PVC if the PVC exists
             Returns None if the PVC doesn't exist
    """

    pvc_exists = check_if_pvc_exists(name=name, namespace=namespace)
    if pvc_exists:
        pvc_info_response = cli.read_namespaced_persistent_volume_claim(
            name=name, namespace=namespace, pretty=True
        )
        pod_list_response = cli.list_namespaced_pod(namespace=namespace)

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
            f"PVC '{str(name)}' doesn't exist in namespace '{str(namespace)}'"
        )
        return None


def find_kraken_node() -> str:
    """
    Find the node kraken is deployed on
    Set global kraken node to not delete

    :return: node where kraken is running (`None` if not found)
    """
    pods = get_all_pods()
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
            node_name = get_pod_info(kraken_pod_name, kraken_project).nodeName
        except Exception as e:
            logging.info(f"{e}")
            raise e
    return node_name


def watch_node_status(
    node: str, status: str, timeout: int, resource_version: str
):
    """
    Watch for a specific node status

    :param node: node name
    :param status: status of the resource
    :param timeout: timeout
    :param resource_version: version of the resource
    """
    count = timeout
    for event in watch_resource.stream(
        cli.list_node,
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
            watch_resource.stop()
            break
        else:
            count -= 1
            logging.info(f"Status of node {node}: {str(conditions[0].status)}")
        if not count:
            watch_resource.stop()


#
# TODO: Implement this with a watcher instead of polling
def watch_managedcluster_status(
    managedcluster: str, status: str, timeout: int
):
    """
    Watch for a specific managedcluster status
    :param managedcluster: managedcluster name
    :param status: status of the resource
    :param timeout: timeout
    """
    elapsed_time = 0
    while True:
        conditions = custom_object_client.get_cluster_custom_object_status(
            "cluster.open-cluster-management.io",
            "v1",
            "managedclusters",
            managedcluster,
        )["status"]["conditions"]
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
                    f"Status of managedcluster " f"{managedcluster}: Available"
                )
                return True
        else:
            if not available:
                logging.info(
                    f"Status of managedcluster "
                    f"{managedcluster}: Unavailable"
                )
                return True
        time.sleep(2)
        elapsed_time += 2
        if elapsed_time >= timeout:
            logging.info(
                f"Timeout waiting for managedcluster "
                f"{managedcluster}  to become: {status}"
            )
            return False


def get_node_resource_version(node: str) -> str:
    """
    Get the resource version for the specified node
    :param node: node name
    :return: resource version
    """
    return cli.read_node(name=node).metadata.resource_version
