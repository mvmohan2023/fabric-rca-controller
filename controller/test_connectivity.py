from __future__ import annotations

from pathlib import Path
from datetime import datetime

from controller.config_loader import load_inventory
from modules.ssh_client import SSHClientWrapper


LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    inventory = load_inventory("inventory/inventory.yaml")
    defaults = inventory.get("defaults", {})
    nodes = inventory.get("nodes", {})

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"connectivity_{ts}.log"

    success_count = 0
    fail_count = 0

    with log_file.open("w", encoding="utf-8") as log:
        log.write(f"Connectivity test started: {datetime.now()}\n")
        log.write("=" * 80 + "\n")

        for node_name, node in nodes.items():
            host = node.get("mgmt_ip") or node.get("hostname")
            username = node.get("username", defaults.get("username", "root"))
            password = node.get("password", defaults.get("password", ""))
            port = int(node.get("port", defaults.get("port", 22)))
            timeout = int(node.get("timeout", defaults.get("timeout", 30)))

            print(f"\n[{node_name}] connecting to {host} ...")

            ssh = SSHClientWrapper(
                host=host,
                username=username,
                password=password,
                port=port,
                timeout=timeout,
            )

            ok, message = ssh.connect()

            if not ok:
                print(f"  FAIL: {message}")
                log.write(f"{node_name} {host} FAIL: {message}\n")
                fail_count += 1
                continue

            result = ssh.run_command("cli -c 'show version | no-more'")
            ssh.close()

            if result.return_code == 0 and result.stdout.strip():
                first_line = result.stdout.strip().splitlines()[0]
                print(f"  OK: {first_line}")
                log.write(f"{node_name} {host} OK: {first_line}\n")
                success_count += 1
            else:
                err = result.error or result.stderr or "command failed"
                print(f"  FAIL: {err}")
                log.write(f"{node_name} {host} FAIL: {err}\n")
                fail_count += 1

        log.write("=" * 80 + "\n")
        log.write(f"Success: {success_count}\n")
        log.write(f"Fail: {fail_count}\n")
        log.write(f"Finished: {datetime.now()}\n")

    print("\nSummary")
    print(f"  Success: {success_count}")
    print(f"  Fail   : {fail_count}")
    print(f"  Log    : {log_file}")


if __name__ == "__main__":
    main()
