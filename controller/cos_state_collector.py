import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
import paramiko
from controller.utils import atomic_write_json

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_for_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


@dataclass
class CoSCommandSet:
    scheduler_map: str
    forwarding_class: str
    cos_interface: str
    interface_queue: str


def build_cos_commands(interface_name: str, scheduler_map: str = "sm1") -> CoSCommandSet:
    return CoSCommandSet(
        scheduler_map=f"show class-of-service scheduler-map {scheduler_map} | no-more",
        forwarding_class="show class-of-service forwarding-class | no-more",
        cos_interface=f"show class-of-service interface {interface_name} | no-more",
        interface_queue=f"show interfaces queue {interface_name} | no-more",
    )

def _run_cli_command_paramiko(
    host: str,
    cli_command: str,
    ssh_user: str = "root",
    ssh_password: str | None = None,
    connect_timeout: int = 20,
) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            username=ssh_user,
            password=ssh_password,
            timeout=connect_timeout,
            look_for_keys=True,
            allow_agent=True,
        )
        remote_cmd = f"cli -c {shlex.quote(cli_command)}"
        stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=max(connect_timeout + 60, 90))

        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")

        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise RuntimeError(
                f"cli command failed host={host}, cmd={cli_command}, rc={exit_status}, stderr={err.strip()}"
            )
        return out.strip()
    finally:
        client.close()

def _run_ssh_cli_command(
    host: str,
    cli_command: str,
    ssh_user: str = "root",
    connect_timeout: int = 20,
) -> str:
    # Use Junos CLI explicitly so this works even when shell is not CLI by default.
    remote_cmd = f"cli -c {shlex.quote(cli_command)}"
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        f"{ssh_user}@{host}",
        remote_cmd,
    ]

    proc = subprocess.run(
        ssh_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(connect_timeout + 60, 90),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ssh command failed host={host}, cmd={cli_command}, rc={proc.returncode}, "
            f"stderr={(proc.stderr or '').strip()}"
        )
    return (proc.stdout or "").strip()


def collect_cos_state(
    *,
    host: str,
    node: str,
    interface_name: str,
    scheduler_map: str = "sm1",
    ssh_user: str = "root",
    ssh_password: str = "Embe1mpls",
) -> Dict[str, Any]:
    cmds = build_cos_commands(interface_name=interface_name, scheduler_map=scheduler_map)

    scheduler_map_text = _run_cli_command_paramiko(
        host=host, cli_command=cmds.scheduler_map, ssh_user=ssh_user, ssh_password=ssh_password
    )
    forwarding_class_text = _run_cli_command_paramiko(
        host=host, cli_command=cmds.forwarding_class, ssh_user=ssh_user, ssh_password=ssh_password
    )
    cos_interface_text = _run_cli_command_paramiko(
        host=host, cli_command=cmds.cos_interface, ssh_user=ssh_user, ssh_password=ssh_password
    )
    interface_queue_text = _run_cli_command_paramiko(
        host=host, cli_command=cmds.interface_queue, ssh_user=ssh_user, ssh_password=ssh_password
    )

    return {
        "generated_at": utc_now_iso(),
        "node": node,
        "host": host,
        "interface": interface_name,
        "scheduler_map_name": scheduler_map,
        "commands": {
            "scheduler_map": cmds.scheduler_map,
            "forwarding_class": cmds.forwarding_class,
            "cos_interface": cmds.cos_interface,
            "interface_queue": cmds.interface_queue,
        },
        "raw": {
            "scheduler_map": scheduler_map_text,
            "forwarding_class": forwarding_class_text,
            "cos_interface": cos_interface_text,
            "interface_queue": interface_queue_text,
        },
    }


def output_paths(run_id: str, node: str, interface_name: str) -> Dict[str, str]:
    safe_node = sanitize_for_filename(node)
    safe_ifd = sanitize_for_filename(interface_name)
    base_dir = Path("artifacts") / "campaigns" / run_id / "cos"
    base_dir.mkdir(parents=True, exist_ok=True)

    json_path = base_dir / f"{safe_node}__{safe_ifd}.json"
    txt_path = base_dir / f"{safe_node}__{safe_ifd}.txt"
    return {"json": str(json_path), "txt": str(txt_path)}


def render_text(report: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"Generated At : {report.get('generated_at')}")
    lines.append(f"Node         : {report.get('node')}")
    lines.append(f"Host         : {report.get('host')}")
    lines.append(f"Interface    : {report.get('interface')}")
    lines.append(f"SchedulerMap : {report.get('scheduler_map_name')}")
    lines.append("")

    for key in ("scheduler_map", "forwarding_class", "cos_interface", "interface_queue"):
        lines.append("=" * 88)
        lines.append(f"RAW SECTION: {key}")
        lines.append("=" * 88)
        lines.append(report.get("raw", {}).get(key, ""))
        lines.append("")

    return "\n".join(lines)


def write_outputs(run_id: str, report: Dict[str, Any]) -> str:
    paths = output_paths(run_id=run_id, node=report["node"], interface_name=report["interface"])
    #with open(paths["json"], "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(paths["json"], report, indent=2)
    with open(paths["txt"], "w") as f:
        f.write(render_text(report))
    return paths["json"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect CoS state for a node/interface.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--scheduler-map", default="sm1")
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-password", default="Embe1mpls")
    args = parser.parse_args()

    result = collect_cos_state(
        host=args.host,
        node=args.node,
        interface_name=args.interface,
        scheduler_map=args.scheduler_map,
        ssh_user=args.ssh_user,
        ssh_password=args.ssh_password,
    )
    out = write_outputs(args.run_id, result)
    print(out)
