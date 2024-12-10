import os
import time
import unittest
import uuid

from krkn_lib.tests import BaseTest


class KrknKubernetesTestsExec(BaseTest):

    def test_command_in_pod(self):
        namespace = "test-ec-" + self.get_random_string(10)
        alpine_name = "alpine-" + self.get_random_string(10)
        fed_name = "test-fed-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=fed_name)
        count = 0
        max_retries = 20
        while not self.lib_k8s.is_pod_running(fed_name, namespace):
            pod_exists = self.lib_k8s.check_if_pod_exists(
                "fedtools", namespace
            )
            print("pod exists " + str(pod_exists))
            if count > max_retries:
                print(
                    "fedtools pod info "
                    + str(self.lib_k8s.get_pod_info(fed_name, namespace))
                )
                print(
                    "fedtools namesapce " + str(self.lib_k8s.list_namespaces())
                )
                print("find namesapce " + str(namespace))
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue

        try:
            cmd = ["-br", "addr", "show"]
            result = self.lib_k8s.exec_cmd_in_pod(
                cmd,
                fed_name,
                namespace,
                base_command="ip",
            )
            self.assertRegex(result, r"\d+\.\d+\.\d+\.\d+")

            # run command in bash
            cmd = ["ls -al /"]
            result = self.lib_k8s.exec_cmd_in_pod(cmd, fed_name, namespace)
            self.assertRegex(result, r"etc")
            self.assertRegex(result, r"root")
            self.assertRegex(result, r"bin")

        except Exception as exc:
            assert False, f"command execution raised an exception {exc}"

        # deploys an alpine container that DOES NOT
        # contain bash, so executing a command without
        # a base command will make the method fallback
        # on sh and NOT fail
        self.depoy_alpine(alpine_name, namespace)

        while not self.lib_k8s.is_pod_running(alpine_name, namespace):
            if count > max_retries:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue

        try:
            self.lib_k8s.exec_cmd_in_pod(["ls", "-al"], alpine_name, namespace)
        except Exception:
            self.fail()

        self.pod_delete_queue.put([fed_name, namespace])
        self.pod_delete_queue.put([alpine_name, namespace])

    def test_pod_shell(self):
        namespace = "test-ps-" + self.get_random_string(10)
        alpine_name = "alpine-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])

        # test against alpine that runs sh
        self.depoy_alpine(alpine_name, namespace)
        count = 0
        while not self.lib_k8s.is_pod_running(alpine_name, namespace):
            time.sleep(3)
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        shell = self.lib_k8s.get_pod_shell(alpine_name, namespace, "alpine")
        self.assertEqual(shell, "sh")

        # test against fedtools that runs bash
        self.deploy_fedtools(namespace=namespace)
        count = 0
        while not self.lib_k8s.is_pod_running("fedtools", namespace):
            time.sleep(3)
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        shell = self.lib_k8s.get_pod_shell("fedtools", namespace)
        self.assertEqual(shell, "bash")
        self.pod_delete_queue.put([alpine_name, namespace])

    def test_command_on_node(self):
        try:
            response = self.lib_k8s.exec_command_on_node(
                "kind-control-plane",
                ["timedatectl", "status"],
                f"test-pod-{self.get_random_string(6)}",
            )
            self.assertTrue(
                "NTP service: active" or "Network time on: yes" in response
            )
        except Exception as e:
            self.fail(f"exception on node command execution: {e}")

    def test_download_folder_from_pod_as_archive(self):
        workdir_basepath = os.getenv("TEST_WORKDIR")
        workdir = self.get_random_string(10)
        test_workdir = os.path.join(workdir_basepath, workdir)
        os.mkdir(test_workdir)
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        count = 0
        max_retries = 5
        while not self.lib_k8s.is_pod_running("fedtools", namespace):
            if count > max_retries:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue
        self.lib_k8s.exec_cmd_in_pod(
            ["mkdir /test"], "fedtools", namespace, "fedtools"
        )
        # create test file
        self.lib_k8s.exec_cmd_in_pod(
            ["dd if=/dev/urandom of=/test/test.bin bs=1024 count=500"],
            "fedtools",
            namespace,
            "fedtools",
        )
        archive = self.lib_k8s.archive_and_get_path_from_pod(
            "fedtools",
            "fedtools",
            namespace,
            "/tmp",
            "/test",
            str(uuid.uuid1()),
            archive_part_size=10000,
            download_path=test_workdir,
        )
        for file in archive:
            self.assertTrue(os.path.isfile(file[1]))
            self.assertTrue(os.stat(file[1]).st_size > 0)

        self.pod_delete_queue.put(["fedtools", namespace])

    def test_exists_path_in_pod(self):
        namespace = "default"
        pod_name = "alpine-" + self.get_random_string(10)
        # to ensure that the namespace is fully deployed
        time.sleep(5)
        self.depoy_alpine(pod_name, namespace)
        count = 0
        max_retries = 100
        while not self.lib_k8s.is_pod_running(pod_name, namespace):
            if count > max_retries:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(5)
            continue

        self.assertTrue(
            self.lib_k8s.path_exists_in_pod(
                pod_name, "alpine", namespace, "/home"
            )
        )

        self.assertFalse(
            self.lib_k8s.path_exists_in_pod(
                pod_name, "alpine", namespace, "/does_not_exist"
            )
        )
        self.pod_delete_queue.put([pod_name, namespace])


if __name__ == "__main__":
    unittest.main()
