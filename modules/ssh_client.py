from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Optional, Tuple

import paramiko


@dataclass
class CommandResult:
    host: str
    command: str
    return_code: int
    stdout: str
    stderr: str
    error: str = ""


class SSHClientWrapper:
    def __init__(
        self,
        host: str,
        username: str,
        password: str = "",
        port: int = 22,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.client: Optional[paramiko.SSHClient] = None

    def connect(self) -> Tuple[bool, str]:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host,
                username=self.username,
                password=self.password if self.password else None,
                port=self.port,
                timeout=self.timeout,
                look_for_keys=True,
                allow_agent=True,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
            )
            self.client = client
            return True, "connected"
        except paramiko.AuthenticationException as exc:
            return False, f"authentication failed: {exc}"
        except paramiko.SSHException as exc:
            return False, f"ssh error: {exc}"
        except socket.timeout as exc:
            return False, f"timeout: {exc}"
        except Exception as exc:
            return False, f"connection failed: {exc}"

    def run_command(self, command: str) -> CommandResult:
        if not self.client:
            return CommandResult(
                host=self.host,
                command=command,
                return_code=1,
                stdout="",
                stderr="",
                error="not connected",
            )

        try:
            stdin, stdout, stderr = self.client.exec_command(
                command, timeout=self.timeout
            )
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")

            return CommandResult(
                host=self.host,
                command=command,
                return_code=exit_code,
                stdout=out,
                stderr=err,
                error="",
            )
        except Exception as exc:
            return CommandResult(
                host=self.host,
                command=command,
                return_code=1,
                stdout="",
                stderr="",
                error=str(exc),
            )

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
