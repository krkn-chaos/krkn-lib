# krkn_lib_kubernetes.client module


### _class_ krkn_lib_kubernetes.client.KrknLibKubernetes(kubeconfig_path: str | None = None, \*, kubeconfig_string: str | None = None)
Bases: `object`


#### \__init__(kubeconfig_path: str | None = None, \*, kubeconfig_string: str | None = None)
KrknLibKubernetes Constructor. Can be invoked with kubeconfig_path
or, optionally, with a kubeconfig in string
format using the keyword argument
:param kubeconfig_path: kubeconfig path
:param kubeconfig_string: (keyword argument)

> kubeconfig in string format

Initialization with kubeconfig path:

```python
>>> KrknLibKubernetes(log_writer, "/home/test/.kube/config")
```

Initialization with kubeconfig string:

```python
>>> kubeconfig_string="apiVersion: v1 ....."
>>> KrknLibKubernetes(log_writer, kubeconfig_string=kubeconfig_string)
```


#### api_client_: ApiClien_ _ = Non_ 

#### apply_yaml(path, namespace='default') -> list[str]
Apply yaml config to create Kubernetes resources


* **Parameters**

    
    * **path** – path to the YAML file
    * **namespace** – namespace to create
    the resource (optional default default)



* **Returns**

    the list of names of created objects



#### archive_and_get_path_from_pod(pod_name: str, container_name: str, namespace: str, remote_archive_path: str, target_path: str, archive_files_prefix: str, download_path: str = '/tmp', archive_part_size: int = 30000, max_threads: int = 5, safe_logger: [SafeLogger](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.SafeLogger) | None = None) -> list[int, str]
archives and downloads a folder content
from container in a base64 tarball.
The function is designed to leverage multi-threading
in order to maximize the download speed.
a max_threads number of download_archive_part_from_pod
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
:param archive_part_size: the archive will splitted in multiple
files of the specified archive_part_size
:param max_threads: maximum number of threads that will be launched
:param safe_logger: SafeLogger, if omitted a default SafeLogger will
be instantiated that will simply use the logging package to print logs
to stdout.
:return: the list of the archive number and filenames downloaded


#### batch_cli_: BatchV1Ap_ _ = Non_ 

#### check_if_namespace_exists(name: str) -> bool
Check if a namespace exists by parsing through
:param name: namespace name
:return: boolean value indicating whether

> the namespace exists or not


#### check_if_pod_exists(name: str, namespace: str = 'default') -> bool
Check if a pod exists in the given namespace


* **Parameters**

    
    * **name** – pod name
    * **namespace** – namespace (optional default default)



* **Returns**

    


#### check_if_pvc_exists(name: str, namespace: str = 'default') -> bool
Check if a PVC exists by parsing through the list of projects.
:param name: PVC name
:param namespace: namespace (optional default default)
:return: boolean value indicating whether

> the Persistent Volume Claim exists or not


#### check_namespaces(namespaces: list[str], label_selector: str | None = None) -> list[str]
Check if all the watch_namespaces are valid


* **Parameters**

    
    * **namespaces** – list of namespaces to check
    * **label_selector** – filter by label_selector
    (optional default None)



* **Returns**

    a list of matching namespaces



#### cli_: CoreV1Ap_ _ = Non_ 

#### create_job(body: any, namespace: str = 'default') -> V1Job
Create a job in a namespace
:param body: an object representation of a valid job yaml manifest
:param namespace: namespace (optional default default),

> Note: if namespace is specified in the body won’t
> overridden


* **Returns**

    V1Job API object



#### create_manifestwork(body: any, namespace: str = 'default') -> object
Create an open cluster management manifestwork in a namespace.
ManifestWork is used to define a group of Kubernetes resources
on the hub to be applied to the managed cluster.


* **Parameters**

    
    * **body** – an object representation of
    a valid manifestwork yaml manifest
    * **namespace** – namespace (optional default default)



* **Returns**

    a custom object representing the newly created manifestwork



#### create_pod(body: any, namespace: str, timeout: int = 120)
Create a pod in a namespace


* **Parameters**

    
    * **body** – an object representation of a valid pod yaml manifest
    * **namespace** – namespace where the pod is created
    * **timeout** – request timeout



#### custom_object_client_: CustomObjectsAp_ _ = Non_ 

#### delete_file_from_pod(pod_name: str, container_name: str, namespace: str, filename: str)
Deletes a file from a pod
:param pod_name: pod name
:param container_name: container name
:param namespace: namespace of the pod
:param filename: full-path of the file that
will be removed from the pod
:return:


#### delete_job(name: str, namespace: str = 'default') -> V1Status
Delete a job from a namespace


* **Parameters**

    
    * **name** – job name
    * **namespace** – namespace (optional default default)



* **Returns**

    V1Status API object



#### delete_manifestwork(namespace: str)
Delete a manifestwork from a namespace


* **Parameters**

    **namespace** – namespace from where the manifestwork must be deleted



* **Returns**

    a custom object representing the deleted resource



#### delete_namespace(namespace: str) -> V1Status
Delete a given namespace
using kubernetes python client


* **Parameters**

    **namespace** – namespace name



* **Returns**

    V1Status API object



#### delete_pod(name: str, namespace: str = 'default')
Delete a pod in a namespace


* **Parameters**

    
    * **name** – pod name
    * **namespace** – namespace (optional default default)



#### dyn_client_: DynamicClien_ _ = Non_ 

#### exec_cmd_in_pod(command: list[str], pod_name: str, namespace: str, container: str | None = None, base_command: str | None = None, std_err: bool = True) -> str
Execute a base command and its parameters
in a pod or a container


* **Parameters**

    
    * **command** – command parameters list or full command string
    if the command must be piped to bash -c
    (in that case base_command parameter
    must is omitted\`)
    * **pod_name** – pod where the command must be executed
    * **namespace** – namespace of the pod
    * **container** – container where the command
    must be executed (optional default None)
    * **base_command** – base command that must be executed
    along the parameters (optional, default bash -c)



* **Returns**

    the command stdout



#### find_kraken_node() -> str
Find the node kraken is deployed on
Set global kraken node to not delete


* **Returns**

    node where kraken is running (None if not found)



#### get_all_kubernetes_object_count(objects: list[str]) -> dict[str, int]

#### get_all_pods(label_selector: str | None = None) -> list[[<class 'str'>, <class 'str'>]]
Return a list of tuples containing pod name [0] and namespace [1]
:param label_selector: filter by label_selector

> (optional default None)


* **Returns**

    list of tuples pod,namespace



#### get_api_resources_by_group(group, version)

#### get_archive_volume_from_pod_worker(pod_name: str, container_name: str, namespace: str, remote_archive_path: str, remote_archive_prefix: str, local_download_path: str, local_file_prefix: str, queue: Queue, queue_size: int, downloaded_file_list: list[int, str], delete_remote_after_download: bool, thread_number: int, safe_logger: [SafeLogger](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.SafeLogger))
Download worker for the create_download_multipart_archive
method. The method will dequeue from the thread-safe queue
parameter until the queue will be empty and will download
the i-th tar volume popped from the queue itself.
the file will be downloaded in base64 string format in order
to avoid archive corruptions caused by the Kubernetes WebSocket
API.


* **Parameters**

    **pod_name** – pod name from which the tar volume


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
(ex for a prefix like 

```
`
```

prefix-

```
`
```

the remote filename

> will become prefix-00.tar)


* **Parameters**

    
    * **local_download_path** – local path where the tar volume
    will be download
    * **local_file_prefix** – local prefix to apply to the


local file downloaded.To the prefix will be appended the
sequential number of the archive assigned to the worker
and the extension tar.b64
:param queue: the queue from which the sequential

> number wil be popped


* **Parameters**

    
    * **queue_size** – total size of the queue
    * **downloaded_file_list** – the list of
    archive number and local filename  downloaded


file will be appended once the download terminates
shared between the threads
:param delete_remote_after_download: if set True once

> the download will terminate

the remote file will be deleted.
:param thread_number: the assigned thread number
:param safe_logger: SafeLogger class, will allow thread-safe
logging
:return:


#### get_cluster_infrastructure() -> str
Get the cluster Cloud infrastructure name when available
:return: the cluster infrastructure name or Unknown when unavailable


#### get_cluster_network_plugins() -> list[str]
Get the cluster Cloud network plugins list
:return: the cluster infrastructure name or Unknown when unavailable


#### get_clusterversion_string() -> str
Return clusterversion status text on OpenShift, empty string
on other distributions


* **Returns**

    clusterversion status



#### get_containers_in_pod(pod_name: str, namespace: str = 'default') -> list[str]
Get container names of a pod


* **Parameters**

    
    * **pod_name** – pod name
    * **namespace** – namespace (optional default default)



* **Returns**

    a list of container names



#### get_host() -> str
Returns the Kubernetes server URL
:return: kubernetes server URL


#### get_job_status(name: str, namespace: str = 'default') -> V1Job
Get a job status


* **Parameters**

    
    * **name** – job name
    * **namespace** – namespace (optional default default)



* **Returns**

    V1Job API object



#### get_kubernetes_core_objects_count(api_version: str, objects: list[str]) -> dict[str, int]
Counts all the occurrences of Kinds contained in
the object parameter in the CoreV1 Api


* **Parameters**

    
    * **api_version** – api version
    * **objects** – list of the kinds that must be counted



* **Returns**

    a dictionary of Kinds and the number of objects counted



#### get_kubernetes_custom_objects_count(objects: list[str]) -> dict[str, int]
Counts all the occurrences of Kinds contained in
the object parameter in the CustomObject Api


* **Parameters**

    **objects** – list of Kinds that must be counted



* **Returns**

    a dictionary of Kinds and number of objects counted



#### get_litmus_chaos_object(kind: str, name: str, namespace: str = 'default') -> [LitmusChaosObject](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.LitmusChaosObject)

* **Parameters**

    
    * **kind** – the custom resource type
    * **name** – the object name
    * **namespace** – the namespace (optional default default)



* **Returns**

    data class object of a subclass of LitmusChaosObject



#### get_namespace_status(namespace_name: str) -> str
Get status of a given namespace


* **Parameters**

    **namespace_name** – namespace name



* **Returns**

    namespace status



#### get_node(node_name: str, label_selector: str, instance_kill_count: int) -> list[str]
Returns active node(s)


* **Parameters**

    
    * **node_name** – node name
    * **label_selector** – filter by label
    * **instance_kill_count** – 



* **Returns**

    


#### get_node_resource_version(node: str) -> str
Get the resource version for the specified node
:param node: node name
:return: resource version


#### get_nodes_infos() -> list[[krkn_lib_kubernetes.resources.NodeInfo](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.NodeInfo)]
Returns a list of NodeInfo objects
:return:


#### get_pod_info(name: str, namespace: str = 'default') -> [Pod](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.Pod)
Retrieve information about a specific pod
:param name: pod name
:param namespace: namespace (optional default default)
:return: Data class object of type Pod with the output of the above

> kubectl command in the given format if the pod exists.
> Returns None if the pod doesn’t exist


#### get_pod_log(name: str, namespace: str = 'default') -> HTTPResponse
Read the logs from a pod


* **Parameters**

    
    * **name** – pod name
    * **namespace** – namespace (optional default default)



* **Returns**

    pod logs



#### get_pvc_info(name: str, namespace: str) -> [PVC](krkn_lib_kubernetes.resources.md#krkn_lib_kubernetes.resources.PVC)
Retrieve information about a Persistent Volume Claim in a
given namespace


* **Parameters**

    
    * **name** – name of the persistent volume claim
    * **namespace** – namespace (optional default default)



* **Returns**

    A PVC data class containing the name, capacity, volume name,
    namespace and associated pod names
    of the PVC if the PVC exists
    Returns None if the PVC doesn’t exist



#### is_pod_running(pod_name: str, namespace: str) -> bool
Checks if a pod and all its containers are running


* **Parameters**

    
    * **pod_name:str** – the name of the pod to check
    * **namespace:str** – the namespace of the pod to check



* **Returns**

    True if is running or False if not



#### list_killable_managedclusters(label_selector: str | None = None) -> list[str]
List managed clusters attached to the hub that can be killed


* **Parameters**

    **label_selector** – filter by label selector
    (optional default None)



* **Returns**

    a list of managed clusters names



#### list_killable_nodes(label_selector: str | None = None) -> list[str]
List nodes in the cluster that can be killed (OpenShift only)


* **Parameters**

    **label_selector** – filter by label
    selector (optional default None)



* **Returns**

    a list of node names that can be killed



#### list_namespaces(label_selector: str | None = None) -> list[str]
List all namespaces


* **Parameters**

    **label_selector** – filter by label
    selector (optional default None)



* **Returns**

    list of namespaces names



#### list_nodes(label_selector: str | None = None) -> list[str]
List nodes in the cluster


* **Parameters**

    **label_selector** – filter by label
    selector (optional default None)



* **Returns**

    a list of node names



#### list_pods(namespace: str, label_selector: str | None = None) -> list[str]
List pods in the given namespace


* **Parameters**

    
    * **namespace** – namespace to search for pods
    * **label_selector** – filter by label selector
    (optional default None)



* **Returns**

    a list of pod names



#### list_ready_nodes(label_selector: str | None = None) -> list[str]
Returns a list of ready nodes


* **Parameters**

    **label_selector** – filter by label
    selector (optional default None)



* **Returns**

    a list of node names



#### monitor_component(iteration: int, component_namespace: str) -> (<class 'bool'>, list[str])
Monitor component namespace


* **Parameters**

    
    * **iteration** – iteration number
    * **component_namespace** – namespace



* **Returns**

    the status of the component namespace



#### monitor_namespace(namespace: str) -> (<class 'bool'>, list[str])
Monitor the status of the pods in the specified namespace
and set the status to true or false
:param namespace: namespace
:return: the list of pods and the status

> (if one or more pods are not running False otherwise True)


#### monitor_nodes() -> (<class 'bool'>, list[str])
Monitor the status of the cluster nodes
and set the status to true or false


* **Returns**

    cluster status and a list of node names



#### path_exists_in_pod(pod_name: str, container_name: str, namespace: str, path: str) -> bool

#### read_pod(name: str, namespace: str = 'default') -> V1Pod
Read a pod definition


* **Parameters**

    
    * **name** – pod name
    * **namespace** – namespace (optional default default)



* **Returns**

    V1Pod definition of the pod



#### watch_managedcluster_status(managedcluster: str, status: str, timeout: int)
Watch for a specific managedcluster status
:param managedcluster: managedcluster name
:param status: status of the resource
:param timeout: timeout


#### watch_node_status(node: str, status: str, timeout: int, resource_version: str)
Watch for a specific node status


* **Parameters**

    
    * **node** – node name
    * **status** – status of the resource
    * **timeout** – timeout
    * **resource_version** – version of the resource



#### watch_resource_: Watc_ _ = Non_
