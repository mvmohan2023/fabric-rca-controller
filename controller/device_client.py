import time
import paramiko


class DeviceClient:
    def __init__(self, host, username, password, port=22, timeout=30):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.client = None

    def connect(self):
        if self.client:
            return

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )

    def run_command(self, command):
        """
        Run Junos operational command through cli -c with hard timeout.
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")

        safe_cmd = command.replace('"', '\\"')
        full_cmd = f'cli -c "{safe_cmd}"'

        stdin, stdout, stderr = self.client.exec_command(
            full_cmd,
            timeout=self.timeout,
            get_pty=False,
        )

        channel = stdout.channel
        channel.settimeout(self.timeout)

        start = time.time()
        out_chunks = []
        err_chunks = []

        while True:
            if channel.recv_ready():
                out_chunks.append(channel.recv(65535).decode(errors="ignore"))

            if channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(65535).decode(errors="ignore"))

            if channel.exit_status_ready():
                break

            if time.time() - start > self.timeout:
                channel.close()
                raise TimeoutError(
                    f"command timed out after {self.timeout}s on {self.host}: {command}"
                )

            time.sleep(0.2)

        while channel.recv_ready():
            out_chunks.append(channel.recv(65535).decode(errors="ignore"))

        while channel.recv_stderr_ready():
            err_chunks.append(channel.recv_stderr(65535).decode(errors="ignore"))

        out = "".join(out_chunks).strip()
        err = "".join(err_chunks).strip()

        if err and not out:
            return err
        if err:
            return f"{out}\n{err}".strip()

        return out

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
