# krkn_lib_kubernetes.client module


### _class_ krkn_lib_kubernetes.client.KrknLibKubernetes(kubeconfig_path: str | None = None, \*, kubeconfig_string: str | None = None)
Bases: `object`


#### \__init__(kubeconfig_path: str | None = None, \*, kubeconfig_string: str | None = None)
KrknLibKubernetes Constructor. Can be invoked with kubeconfig_path
or, optionally, with a kubeconfig in string
format using the keyword argument


* **Parameters**

    
    * **kubeconfig_path** – kubeconfig path
    * **kubeconfig_string** – (keyword argument)
    kubeconfig in string format


Initialization with kubeconfig path:

```python
>>> KrknLibKubernetes("/home/test/.kube/config")
```

Initialization with kubeconfig string:

```python
>>> kubeconfig_string="apiVersion: v1 ....."
>>> KrknLibKubernetes(kubeconfig_string=kubeconfig_string)
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

#### exec_cmd_in_pod(command: list[str], pod_name: str, namespace: str, container: str | None = None, base_command: str | None = None) -> str
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



#### get_all_pods(label_selector: str | None = None) -> list[[<class 'str'>, <class 'str'>]]
Return a list of tuples containing pod name [0] and namespace [1]
:param label_selector: filter by label_selector

> (optional default None)


* **Returns**

    list of tuples pod,namespace



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
