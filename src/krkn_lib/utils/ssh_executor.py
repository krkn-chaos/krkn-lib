import logging
import os
import shlex
import time

import paramiko


class SSHExecutor:
    """Executes commands on remote hosts via SSH using paramiko.

    Uses ``paramiko.WarningPolicy`` by default so that unknown host keys
    are logged as warnings rather than silently accepted. Set
    ``strict_host_key_checking=True`` to reject unknown keys entirely.
    """

    def __init__(
        self,
        ssh_user: str = "root",
        ssh_private_key: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
        connect_timeout: int = 30,
        strict_host_key_checking: bool = False,
    ):
        self.ssh_user = ssh_user
        self.ssh_private_key = os.path.expanduser(ssh_private_key)
        self.ssh_port = ssh_port
        self.connect_timeout = connect_timeout
        self.strict_host_key_checking = strict_host_key_checking

    def _get_host_key_policy(self):
        if self.strict_host_key_checking:
            return paramiko.RejectPolicy()
        return paramiko.WarningPolicy()

    def execute(
        self, host: str, command: str, timeout: int = 120
    ) -> tuple[int, str, str]:
        """Execute a command on a remote host via SSH.

        :param host: the hostname or IP address of the remote host
        :param command: the command string to execute
        :param timeout: maximum seconds to wait for the command to
            complete
        :return: a tuple of (exit_code, stdout, stderr)
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(self._get_host_key_policy())
        try:
            ssh.connect(
                host,
                port=self.ssh_port,
                username=self.ssh_user,
                key_filename=self.ssh_private_key,
                timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
            )
            stdin, stdout, stderr = ssh.exec_command(
                command, timeout=timeout
            )
            exit_code = stdout.channel.recv_exit_status()
            return (
                exit_code,
                stdout.read().decode("utf-8", errors="replace"),
                stderr.read().decode("utf-8", errors="replace"),
            )
        except paramiko.AuthenticationException as e:
            logging.error(
                "SSH authentication failed for %s: %s" % (host, e)
            )
            raise
        except paramiko.SSHException as e:
            logging.error(
                "SSH connection error to %s: %s" % (host, e)
            )
            raise
        except Exception as e:
            logging.error(
                "Failed to execute command on %s: %s" % (host, e)
            )
            raise
        finally:
            ssh.close()

    def is_host_reachable(self, host: str, timeout: int = 10) -> bool:
        """Check if a host is reachable via SSH.

        :param host: the hostname or IP address to check
        :param timeout: connection timeout in seconds
        :return: True if the host is reachable, False otherwise
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(self._get_host_key_policy())
        try:
            ssh.connect(
                host,
                port=self.ssh_port,
                username=self.ssh_user,
                key_filename=self.ssh_private_key,
                timeout=timeout,
                banner_timeout=timeout,
            )
            return True
        except Exception:
            return False
        finally:
            ssh.close()

    def wait_for_host(
        self,
        host: str,
        timeout: int = 600,
        poll_interval: int = 15,
        reachable: bool = True,
    ) -> bool:
        """Wait until a host becomes reachable or unreachable via SSH.

        :param host: the hostname or IP address to monitor
        :param timeout: maximum seconds to wait
        :param poll_interval: seconds between reachability checks
        :param reachable: if True wait for the host to become reachable,
            if False wait for it to become unreachable
        :return: True if the desired state was reached within timeout,
            False otherwise
        """
        deadline = time.time() + timeout
        state = "reachable" if reachable else "unreachable"
        logging.info(
            "Waiting for %s to become %s (timeout: %ds)"
            % (host, state, timeout)
        )
        while time.time() < deadline:
            if self.is_host_reachable(host) == reachable:
                logging.info("Host %s is now %s" % (host, state))
                return True
            time.sleep(poll_interval)
        logging.error(
            "Timed out waiting for %s to become %s" % (host, state)
        )
        return False
