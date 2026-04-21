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
            look_for_keys=False,
            allow_agent=False,
        )

    def run_command(self, command):
        """
        Run Junos operational command through cli -c
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")

        safe_cmd = command.replace('"', '\\"')
        full_cmd = f'cli -c "{safe_cmd}"'

        stdin, stdout, stderr = self.client.exec_command(full_cmd, timeout=self.timeout)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()

        if err and not out:
            return err
        if err:
            return f"{out}\n{err}".strip()

        return out

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
