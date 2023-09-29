import ast
import logging

from kubernetes import client

from krkn_lib.k8s import KrknKubernetes


class KrknOpenshift(KrknKubernetes):
    def __init__(
        self,
        kubeconfig_path: str = None,
        *,
        kubeconfig_string: str = None,
    ):
        super().__init__(
            kubeconfig_path=kubeconfig_path,
            kubeconfig_string=kubeconfig_string,
        )

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

    def get_cluster_infrastructure(self) -> str:
        """
        Get the cluster Cloud infrastructure name when available

        :return: the cluster infrastructure name or `Unknown` when unavailable
        """
        api_client = self.api_client
        if api_client:
            try:
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
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
                path_params: dict[str, str] = {}
                query_params: list[str] = []
                header_params: dict[str, str] = {}
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
                logging.warning(
                    "Impossible to retrieve cluster Network plugins  -> %s",
                    str(e),
                )
                network_plugins.append("Unknown")
        return network_plugins
