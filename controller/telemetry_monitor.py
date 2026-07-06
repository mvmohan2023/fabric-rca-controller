# controller/telemetry_monitor.py

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Optional
from controller.progress_logger import ProgressLogger
from concurrent.futures import ThreadPoolExecutor, as_completed

from controller.telemetry_normalizers import normalize_telemetry_payload
from controller.telemetry_targets import (
    DEFAULT_TOPOLOGY_PATH,
    resolve_interfaces_for_nodes,
)


DEFAULT_CATALOG = os.path.join(os.path.dirname(__file__), "path_catalog.json")
DEFAULT_INVENTORY = os.path.join(os.path.dirname(__file__), "inventory.json")
DEFAULT_TELEMETRY_SERVER = os.environ.get("TELEMETRY_SERVER", "10.83.6.46")
DEFAULT_GNMI_PORT = 60061
DEFAULT_TOPOLOGY = DEFAULT_TOPOLOGY_PATH

def _load_topology_node_interfaces(topology_path):
    import json

    node_ifaces = {}

    if not topology_path:
        return node_ifaces

    try:
        with open(topology_path) as f:
            data = json.load(f)
    except Exception:
        return node_ifaces

    def walk(obj):
        if isinstance(obj, dict):
            node = obj.get("node") or obj.get("local_node") or obj.get("device")
            iface = obj.get("interface") or obj.get("local_interface") or obj.get("ifname")

            if node and iface:
                node_ifaces.setdefault(str(node), set()).add(str(iface))

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return node_ifaces


def _extract_interface_from_path(path):
    marker = "interface[name="
    if marker not in str(path):
        return None

    try:
        start = str(path).index(marker) + len(marker)
        end = str(path).index("]", start)
        return str(path)[start:end].strip("'\"")
    except Exception:
        return None


def progress_log_path_for_run(run_id: str) -> str:
    return os.path.join("artifacts", "campaigns", run_id, "run_progress.log")


def normalize_stderr_text(stderr_text: str) -> str:
    return (stderr_text or "").strip()


def is_benign_gnmic_stderr(stderr_text: str) -> bool:
    text = normalize_stderr_text(stderr_text).lower()
    if not text:
        return False

    benign_patterns = [
        "rpc error: code = canceled desc = cancelled on the server side",
        "rpc error: code = canceled desc = canceled on the server side",
    ]

    return any(p in text for p in benign_patterns)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json_file(path: str) -> Any:
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def parse_nodes(nodes_arg: str) -> List[str]:
    if not nodes_arg:
        return []
    return [item.strip() for item in nodes_arg.split(",") if item.strip()]


def load_catalog(catalog_path: str) -> Dict[str, Any]:
    return load_json_file(catalog_path)

def get_profile_paths(catalog: Dict[str, Any], profile: str) -> List[str]:
    profiles = catalog.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"profile '{profile}' not found in path catalog")

    profile_data = profiles[profile]
    paths = profile_data.get("paths", [])

    resolved_paths: List[str] = []
    for entry in paths:
        if isinstance(entry, str):
            resolved_paths.append(entry)
        elif isinstance(entry, dict) and entry.get("path"):
            resolved_paths.append(entry["path"])
        else:
            raise ValueError(f"invalid path entry under profile '{profile}': {entry}")

    return resolved_paths


def normalize_name(value: str) -> str:
    """
    Case-insensitive, trims spaces, and normalizes common formatting variants.
    Examples:
      Leaf1   -> leaf1
      leaf1   -> leaf1
      leaf-1  -> leaf1
      leaf_1  -> leaf1
      spine1  -> spine1
    """
    text = (value or "").strip().lower()
    text = text.replace("_", "")
    text = text.replace("-", "")
    text = text.replace(" ", "")
    return text


def is_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(part.isdigit() for part in parts)


def load_inventory(inventory_path: str) -> Dict[str, Any]:
    """
    Preferred format:
    {
      "nodes": [
        {
          "device": "san-q5700-03",
          "serial": "XXX",
          "mgt_ip": "10.83.6.9",
          "role": "Leaf6",
          "grpc": 60068
        }
      ]
    }

    Backward-compatible format:
    {
      "leaf1": { "target": "10.83.6.28:60061" },
      "leaf2": { "ip": "10.83.6.29", "port": 60061 }
    }
    """
    if not os.path.exists(inventory_path):
        return {"nodes": []}

    data = load_json_file(inventory_path)

    if isinstance(data, dict):
        if "nodes" in data and isinstance(data["nodes"], list):
            return data

        # backward compatibility for older flat-key inventory
        converted_nodes: List[Dict[str, Any]] = []
        for key, value in data.items():
            if not isinstance(value, dict):
                continue

            target = value.get("target")
            ip = (
                value.get("mgt_ip")
                or value.get("mgmt_ip")
                or value.get("ip")
                or value.get("host")
            )
            grpc = value.get("grpc") or value.get("port")

            if target and ":" in target:
                target_ip, target_port = target.rsplit(":", 1)
                if not ip:
                    ip = target_ip
                if not grpc:
                    try:
                        grpc = int(target_port)
                    except ValueError:
                        pass

            converted_nodes.append(
                {
                    "device": key,
                    "serial": value.get("serial"),
                    "mgt_ip": ip,
                    "role": value.get("role"),
                    "grpc": grpc,
                }
            )

        return {"nodes": converted_nodes}

    raise ValueError(f"unsupported inventory format in {inventory_path}")


def validate_inventory(inventory: Dict[str, Any]) -> None:
    nodes = inventory.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("inventory.json must contain a top-level 'nodes' list")

    seen_devices = set()
    seen_ips = set()
    seen_serials = set()

    for idx, item in enumerate(nodes):
        if not isinstance(item, dict):
            raise ValueError(f"inventory entry at index {idx} must be an object")

        device = item.get("device")
        mgt_ip = item.get("mgt_ip")
        grpc = item.get("grpc")
        serial = item.get("serial")

        if not device:
            raise ValueError(f"inventory entry at index {idx} missing 'device'")
        if not mgt_ip:
            raise ValueError(f"inventory entry '{device}' missing 'mgt_ip'")
        if grpc in (None, ""):
            raise ValueError(f"inventory entry '{device}' missing 'grpc'")

        try:
            int(grpc)
        except Exception as exc:
            raise ValueError(f"inventory entry '{device}' has invalid grpc '{grpc}'") from exc

        device_n = normalize_name(device)
        serial_n = normalize_name(serial)

        if device_n in seen_devices:
            raise ValueError(f"duplicate device in inventory: {device}")
        seen_devices.add(device_n)

        if mgt_ip in seen_ips:
            raise ValueError(f"duplicate mgt_ip in inventory: {mgt_ip}")
        seen_ips.add(mgt_ip)

        if serial_n:
            if serial_n in seen_serials:
                raise ValueError(f"duplicate serial in inventory: {serial}")
            seen_serials.add(serial_n)


def build_inventory_indexes(inventory: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    by_name: Dict[str, Dict[str, Any]] = {}
    by_ip: Dict[str, Dict[str, Any]] = {}
    by_serial: Dict[str, Dict[str, Any]] = {}

    for item in inventory.get("nodes", []):
        device = normalize_name(item.get("device"))
        alias = normalize_name(item.get("alias"))
        role = normalize_name(item.get("role"))
        ip = (item.get("mgt_ip") or "").strip()
        serial = normalize_name(item.get("serial"))

        if device:
            by_name[device] = item
        if alias:
            by_name[alias] = item
        if role:
            by_name[role] = item

        if ip:
            by_ip[ip] = item

        if serial:
            by_serial[serial] = item

    print("[INVENTORY-INDEX] by_name keys =", sorted(by_name.keys()))
    print("[INVENTORY-INDEX] by_ip keys =", sorted(by_ip.keys()))
    print("[INVENTORY-INDEX] by_serial keys =", sorted(by_serial.keys()))

    return {
        "by_name": by_name,
        "by_ip": by_ip,
        "by_serial": by_serial,
    }




def resolve_inventory_record(
    node: str,
    inventory_indexes: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    node_n = normalize_name(node)

    print(f"[INVENTORY-RESOLVE] input_node={node} normalized_node={node_n}")

    if node_n in inventory_indexes["by_name"]:
        record = inventory_indexes["by_name"][node_n]
        print(f"[INVENTORY-RESOLVE] matched by_name -> {record.get('device')}")
        return record

    if node in inventory_indexes["by_ip"]:
        record = inventory_indexes["by_ip"][node]
        print(f"[INVENTORY-RESOLVE] matched by_ip -> {record.get('device')}")
        return record

    if node_n in inventory_indexes["by_serial"]:
        record = inventory_indexes["by_serial"][node_n]
        print(f"[INVENTORY-RESOLVE] matched by_serial -> {record.get('device')}")
        return record

    raise ValueError(
        f"unable to resolve inventory record for node '{node}'. "
        f"normalized='{node_n}'. "
        f"Available names={sorted(inventory_indexes['by_name'].keys())}"
    )


def resolve_node_target(
    node: str,
    inventory_indexes: Dict[str, Dict[str, Dict[str, Any]]],
    default_port: int,
) -> Tuple[str, Dict[str, Any]]:
    """
    Supported inputs in --nodes:
      --nodes san-q5700-03
      --nodes 10.83.6.9
      --nodes 10.83.6.9:60068
    """
    if ":" in node:
        host, port = node.rsplit(":", 1)
        if is_ipv4(host) and port.isdigit():
            return node, {
                "device": node,
                "mgt_ip": host,
                "grpc": int(port),
                "role": None,
                "serial": None,
            }

    if is_ipv4(node):
        if node in inventory_indexes["by_ip"]:
            record = inventory_indexes["by_ip"][node]
            return f"{record['mgt_ip']}:{int(record['grpc'])}", record

        return f"{node}:{default_port}", {
            "device": node,
            "mgt_ip": node,
            "grpc": int(default_port),
            "role": None,
            "serial": None,
        }

    record = resolve_inventory_record(node=node, inventory_indexes=inventory_indexes)
    target = f"{record['mgt_ip']}:{int(record['grpc'])}"
    return target, record


def path_requires_interface_expansion(path: str) -> bool:
    return "{interface}" in path


def expand_profile_paths_for_nodes(
    paths: List[str],
    nodes: List[str],
    topology_path: str,
) -> Dict[str, List[str]]:
    """
    Expands path templates using topology-derived interfaces.

    Example input path:
      /state/interfaces/interface[name={interface}]/

    Example output:
      {
        "leaf1": [
          "/state/interfaces/interface[name=et-0/0/4:1]/",
          "/qos/interfaces/interface/output/queues/queue/state/"
        ]
      }
    """
    interface_map = resolve_interfaces_for_nodes(
        topology_path=topology_path,
        selected_nodes=nodes,
    )

    expanded: Dict[str, List[str]] = {}

    for node in nodes:
        node_paths: List[str] = []
        interfaces = interface_map.get(node.lower(), [])

        for path in paths:
            if path_requires_interface_expansion(path):
                if not interfaces:
                    print(
                        f"[TELEMETRY-PATH-RESOLVE] node={node} no topology-resolved interfaces "
                        f"for template path={path}"
                    )
                    continue

                for interface_name in interfaces:
                    node_paths.append(path.replace("{interface}", interface_name))
            else:
                node_paths.append(path)

        expanded[node] = node_paths

    return expanded


def expand_profile_paths_for_recovery_interfaces(
    paths: List[str],
    nodes: List[str],
    topology_path: str,
    bounced_node: str,
    bounced_interface: str,
    node_host_map: Optional[Dict[str, Dict[str, str]]] = None,
    device_facts_dir: str = os.path.join("artifacts", "device_facts"),
) -> Dict[str, List[str]]:
    from controller.telemetry_targets import resolve_recovery_interfaces_for_bounce

    interface_map = resolve_recovery_interfaces_for_bounce(
        topology_path=topology_path,
        selected_nodes=nodes,
        bounced_node=bounced_node,
        bounced_interface=bounced_interface,
        node_host_map=node_host_map,
        device_facts_dir=device_facts_dir,
    )

    expanded: Dict[str, List[str]] = {}

    for node in nodes:
        node_paths: List[str] = []
        interfaces = interface_map.get(node, []) or interface_map.get(node.lower(), [])

        for path in paths:
            if path_requires_interface_expansion(path):
                if not interfaces:
                    print(
                        f"[TELEMETRY-RECOVERY-RESOLVE] node={node} no recovery interfaces "
                        f"for template path={path}"
                    )
                    continue

                for interface_name in interfaces:
                    node_paths.append(path.replace("{interface}", interface_name))
            else:
                node_paths.append(path)

        deduped_paths: List[str] = []
        seen = set()
        for item in node_paths:
            if item not in seen:
                deduped_paths.append(item)
                seen.add(item)

        expanded[node] = deduped_paths

    return expanded

def build_gnmic_command(
    telemetry_server: str,
    target: str,
    sub_path: str,
    timeout: int,
    ssh_user: str,
) -> str:
    """
    Runs gnmic on the telemetry server via ssh.
    """
    inner_cmd = (
        f"gnmic -a {shlex.quote(target)} "
        f"sub --path {shlex.quote(sub_path)} "
        f"--mode once --insecure --format json"
    )
    ssh_cmd = (
        f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout={timeout} "
        f"{shlex.quote(ssh_user)}@{shlex.quote(telemetry_server)} "
        f"{shlex.quote(inner_cmd)}"
    )
    return ssh_cmd


def extract_json_objects_from_stdout(stdout_text: str) -> List[Dict[str, Any]]:
    text = stdout_text.strip()
    if not text:
        raise ValueError("empty stdout from gnmic")

    objects: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)

    while idx < length:
        while idx < length and text[idx] not in "{[":
            idx += 1

        if idx >= length:
            break

        try:
            obj, end = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                objects.append(obj)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        objects.append(item)
            idx = end
        except json.JSONDecodeError:
            idx += 1

    if not objects:
        raise ValueError("unable to extract valid JSON objects from gnmic stdout")

    return objects


def build_paths_summary(paths: List[str]) -> str:
    lines = []
    for path in paths:
        lines.append(f"  - {path}")
    return "\n".join(lines)


def summarize_record_groups(records: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in records:
        group = record.get("labels", {}).get("group", "unknown")
        counts[group] = counts.get(group, 0) + 1
    return counts


def render_text_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("TELEMETRY SNAPSHOT SUMMARY")
    lines.append(f"  Telemetry server : {report.get('telemetry_server')}")
    lines.append(f"  Profile          : {report.get('profile')}")
    lines.append(f"  Snapshot         : {report.get('snapshot_name')}")
    lines.append(f"  Nodes            : {report.get('total_nodes')}")
    lines.append(f"  OK nodes         : {report.get('ok_nodes')}")
    lines.append(f"  Failed nodes     : {report.get('failed_nodes')}")
    lines.append("")

    lines.append("PROFILE PATH TEMPLATES")
    lines.append(build_paths_summary(report.get("path_templates", [])))
    lines.append("")

    lines.append("NODE DETAILS")
    for node_entry in report.get("nodes", []):
        lines.append(f"  Node    : {node_entry.get('node')}")
        lines.append(f"  Target  : {node_entry.get('target')}")
        lines.append(f"  Status  : {node_entry.get('status')}")
        lines.append(f"  Records : {len(node_entry.get('normalized_records', []))}")

        if node_entry.get("resolved_device"):
            lines.append(f"  Device  : {node_entry.get('resolved_device')}")
        if node_entry.get("resolved_mgt_ip"):
            lines.append(f"  Mgt IP  : {node_entry.get('resolved_mgt_ip')}")
        if node_entry.get("resolved_grpc"):
            lines.append(f"  gRPC    : {node_entry.get('resolved_grpc')}")

        resolved_paths = node_entry.get("resolved_paths", [])
        if resolved_paths:
            lines.append("  Paths   :")
            for path in resolved_paths:
                lines.append(f"    - {path}")

        group_counts = summarize_record_groups(node_entry.get("normalized_records", []))
        if group_counts:
            lines.append(f"  Groups  : {group_counts}")


        if node_entry.get("warnings"):
            for warn in node_entry["warnings"]:
                lines.append(f"  Warning : {warn}")
        if node_entry.get("errors"):
            for err in node_entry["errors"]:
                lines.append(f"  Error   : {err}")

        lines.append("")

    return "\n".join(lines) + "\n"


def run_gnmic_once(
    telemetry_server: str,
    target: str,
    sub_path: str,
    timeout: int,
    ssh_user: str,
) -> Tuple[List[Dict[str, Any]], str, str]:
    cmd = build_gnmic_command(
        telemetry_server=telemetry_server,
        target=target,
        sub_path=sub_path,
        timeout=timeout,
        ssh_user=ssh_user,
    )

    proc = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(timeout + 15, 30),
    )

    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()

    benign_cancel = (
        "rpc error: code = Canceled desc = Cancelled on the server side" in stderr_text
        and "Error: one or more requests failed" in stderr_text
    )

    payloads: List[Dict[str, Any]] = []

    if stdout_text:
        try:
            payloads = extract_json_objects_from_stdout(stdout_text)
        except Exception as exc:
            raise RuntimeError(
                f"failed to parse gnmic output for target={target}, path={sub_path}: {exc}\n"
                f"STDOUT preview:\n{stdout_text[:2000]}\n"
                f"STDERR preview:\n{stderr_text[:1200]}"
            ) from exc

    if proc.returncode != 0:
        # Common Junos/gNMI behavior:
        # gnmic returns useful JSON, but exits with server-side cancel text.
        if benign_cancel and payloads:
            return payloads, cmd, stderr_text

        # Also tolerate benign cancel with empty stdout for unsupported/quiet paths
        # so the caller can treat it as warning-only and continue.
        if benign_cancel and not payloads:
            return [], cmd, stderr_text

        raise RuntimeError(
            f"gnmic failed for target={target}, path={sub_path}, "
            f"rc={proc.returncode}, stderr={stderr_text}\n"
            f"STDOUT preview:\n{stdout_text[:2000]}"
        )

    # rc == 0 cases
    if payloads:
        return payloads, cmd, stderr_text

    if benign_cancel:
        return [], cmd, stderr_text

    # No payload and no real error text: let caller decide whether to skip
    return [], cmd, stderr_text



from concurrent.futures import ThreadPoolExecutor, as_completed


def _collect_single_node(
    *,
    node: str,
    telemetry_server: str,
    ssh_user: str,
    paths: List[str],
    per_node_paths: Dict[str, List[str]],
    inventory_indexes: Dict[str, Any],
    timeout: int,
    default_gnmi_port: int,
    topology_node_interfaces: Dict[str, set],
) -> Dict[str, Any]:


    node_result: Dict[str, Any] = {
        "node": node,
        "target": None,
        "status": "ok",
        "errors": [],
        "subscriptions": [],
        "normalized_records": [],
        "resolved_device": None,
        "resolved_mgt_ip": None,
        "resolved_grpc": None,
        "resolved_role": None,
        "resolved_serial": None,
        "resolved_paths": [],
    }

    node_paths: List[str] = []

    try:
        target, record = resolve_node_target(
            node=node,
            inventory_indexes=inventory_indexes,
            default_port=default_gnmi_port,
        )

        node_result["target"] = target
        node_result["resolved_device"] = record.get("device")
        node_result["resolved_mgt_ip"] = record.get("mgt_ip")
        node_result["resolved_grpc"] = record.get("grpc")
        node_result["resolved_role"] = record.get("role")
        node_result["resolved_serial"] = record.get("serial")

        node_paths = per_node_paths.get(node, paths)
        node_result["resolved_paths"] = list(node_paths)

        if not node_paths:
            raise ValueError(f"No telemetry paths resolved for node {node}")

        print(f"[TELEMETRY-RESOLVE] node={node} target={target}")

        for sub_path in node_paths:
            iface = _extract_interface_from_path(sub_path)
            if iface:
                valid_ifaces = topology_node_interfaces.get(str(node), set())
                if valid_ifaces and iface not in valid_ifaces:
                    print(
                        f"[TELEMETRY-SKIP] node={node} interface={iface} "
                        f"reason=interface_not_present_on_node"
                    )
                    continue

            print(f"[TELEMETRY] node={node} sub_path={sub_path}")

            payloads, command_used, stderr_text = run_gnmic_once(
                telemetry_server=telemetry_server,
                target=target,
                sub_path=sub_path,
                timeout=timeout,
                ssh_user=ssh_user,
            )

            all_normalized_records: List[Dict[str, Any]] = []

            for payload in payloads:
                normalized_records = normalize_telemetry_payload(
                    payload=payload,
                    node=node,
                    sub_path=sub_path,
                )
                all_normalized_records.extend(normalized_records)

            if stderr_text:
                benign_cancel = (
                    "rpc error: code = Canceled desc = Cancelled on the server side" in stderr_text
                    and "Error: one or more requests failed" in stderr_text
                )
                if benign_cancel:
                    node_result["errors"].append(f"warning for path {sub_path}: {stderr_text}")

            node_result["subscriptions"].append(
                {
                    "path": sub_path,
                    "command": command_used,
                    "stderr": stderr_text,
                    "raw": payloads,
                    "normalized_records": all_normalized_records,
                }
            )

            node_result["normalized_records"].extend(all_normalized_records)

    except Exception as exc:
        node_result["status"] = "failed"
        node_result["errors"].append(str(exc))
        node_result["resolved_paths"] = list(node_paths)

    return node_result


def collect_snapshot(
    telemetry_server: str,
    ssh_user: str,
    nodes: List[str],
    paths: List[str],
    inventory: Dict[str, Any],
    timeout: int,
    snapshot_name: str,
    profile: str,
    source_type: str,
    run_id: str,
    default_gnmi_port: int,
    topology_path: str,
    per_node_paths_override: Optional[Dict[str, List[str]]] = None,
    topology_node_interfaces: Dict[str, set] = None,
) -> Dict[str, Any]:

    progress = ProgressLogger(progress_log_path_for_run(run_id))
    progress.stage(f"TELEMETRY_SNAPSHOT_{snapshot_name.upper()}")
    progress.info(f"profile={profile}")
    progress.info(f"node_count={len(nodes)}")

    inventory_indexes = build_inventory_indexes(inventory)

    per_node_paths = (
        per_node_paths_override
        if per_node_paths_override is not None
        else expand_profile_paths_for_nodes(
            paths=paths,
            nodes=nodes,
            topology_path=topology_path,
        )
    )

    report: Dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source_type": source_type,
        "run_id": run_id,
        "snapshot_name": snapshot_name,
        "telemetry_server": telemetry_server,
        "profile": profile,
        "path_templates": paths,
        "nodes": [],
    }

    ok_nodes = 0
    failed_nodes = 0

    # 🔥 Parallel execution
    max_workers = min(6, len(nodes))  # SAFE LIMIT

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _collect_single_node,
                node=node,
                telemetry_server=telemetry_server,
                ssh_user=ssh_user,
                paths=paths,
                per_node_paths=per_node_paths,
                inventory_indexes=inventory_indexes,
                timeout=timeout,
                default_gnmi_port=default_gnmi_port,
                topology_node_interfaces=topology_node_interfaces or {},
            ): node
            for node in nodes
        }

        for future in as_completed(futures):
            node = futures[future]
            try:
                result = future.result()
                report["nodes"].append(result)

                if result["status"] == "ok":
                    ok_nodes += 1
                else:
                    failed_nodes += 1

            except Exception as exc:
                failed_nodes += 1
                report["nodes"].append({
                    "node": node,
                    "status": "failed",
                    "errors": [str(exc)],
                })

    report["total_nodes"] = len(nodes)
    report["ok_nodes"] = ok_nodes
    report["failed_nodes"] = failed_nodes

    progress.stage(f"TELEMETRY_SNAPSHOT_{snapshot_name.upper()}_DONE")
    progress.info(f"ok_nodes={ok_nodes}")
    progress.info(f"failed_nodes={failed_nodes}")

    return report

def collect_recovery_snapshot(
    *,
    run_id: str,
    snapshot_name: str,
    profile: str,
    nodes: str,
    timeout: int,
    topology_path: str,
    bounced_node: str,
    bounced_interface: str,
) -> None:
    from controller.telemetry_monitor import (
        load_catalog,
        get_profile_paths,
        load_inventory,
        parse_nodes,
        collect_snapshot as telemetry_collect_snapshot,
        build_output_paths,
        write_json,
        write_text,
        render_text_report,
        expand_profile_paths_for_recovery_interfaces,
    )
    from controller.telemetry_monitor import (
        DEFAULT_CATALOG,
        DEFAULT_INVENTORY,
        DEFAULT_TELEMETRY_SERVER,
    )

    if not bounced_node:
        raise ValueError("collect_recovery_snapshot requires bounced_node")
    if not bounced_interface:
        raise ValueError("collect_recovery_snapshot requires bounced_interface")

    catalog = load_catalog(DEFAULT_CATALOG)
    paths = get_profile_paths(catalog, profile)
    inventory = load_inventory(DEFAULT_INVENTORY)
    node_list = parse_nodes(nodes)

    # Build node_host_map so recovery resolver can use live LLDP discovery.
    # Inventory schema observed:
    # {
    #   "nodes": [
    #     {
    #       "device": "san-q5240-01",
    #       "alias": "leaf1",
    #       "serial": "...",
    #       "mgt_ip": "10.83.6.3",
    #       "role": "Leaf1",
    #       "grpc": 60063
    #     }
    #   ]
    # }
    node_host_map: Dict[str, Dict[str, str]] = {}

    inventory_items = []
    if isinstance(inventory, list):
        inventory_items = inventory
    elif isinstance(inventory, dict):
        inventory_items = (
            inventory.get("devices")
            or inventory.get("nodes")
            or inventory.get("inventory")
            or []
        )

    for item in inventory_items:
        if not isinstance(item, dict):
            continue

        node_name = (
            item.get("alias")
            or item.get("node")
            or item.get("name")
            or item.get("hostname")
            or item.get("device")
        )
        if not node_name:
            continue

        host = (
            item.get("mgt_ip")
            or item.get("resolved_mgt_ip")
            or item.get("host")
            or item.get("management_ip")
            or item.get("ip")
            or ""
        )

        device_name = str(item.get("device") or "").strip()

        entry = {
            "host": host,
            "resolved_mgt_ip": host,
            "device": device_name,
        }

        # primary lookup by logical alias, e.g. leaf1
        node_host_map[str(node_name).lower()] = entry

        # secondary lookup by device hostname, e.g. san-q5240-01
        if device_name:
            node_host_map[device_name.lower()] = entry

    print(f"[RECOVERY-SNAPSHOT] node_host_map keys={list(node_host_map.keys())[:20]}")
    print(
        f"[RECOVERY-SNAPSHOT] bounced_node={bounced_node} "
        f"node_host_entry={node_host_map.get(bounced_node.lower())}"
    )

    recovery_paths = expand_profile_paths_for_recovery_interfaces(
        paths=paths,
        nodes=node_list,
        topology_path=topology_path,
        bounced_node=bounced_node,
        bounced_interface=bounced_interface,
        device_facts_dir=os.path.join("artifacts", "device_facts"),
    )

    if not recovery_paths:
        raise RuntimeError(
            f"failed to resolve recovery paths for node={bounced_node} "
            f"interface={bounced_interface}"
        )

    resolved_node_paths = recovery_paths.get(bounced_node, []) or recovery_paths.get(bounced_node.lower(), [])
    if not resolved_node_paths:
        print(
            f"[RECOVERY-SNAPSHOT] warning: no narrowed paths found for "
            f"bounced_node={bounced_node}; falling back to empty narrowed set"
        )

    report = telemetry_collect_snapshot(
        telemetry_server=DEFAULT_TELEMETRY_SERVER,
        ssh_user="root",
        nodes=node_list,
        paths=paths,
        inventory=inventory,
        timeout=timeout,
        snapshot_name=snapshot_name,
        profile=profile,
        source_type="campaign",
        run_id=run_id,
        default_gnmi_port=60061,
        topology_path=topology_path,
        per_node_paths_override=recovery_paths,
    )

    json_path, txt_path = build_output_paths(
        run_id=run_id,
        snapshot_name=snapshot_name,
        profile=profile,
    )

    write_json(json_path, report)
    write_text(txt_path, render_text_report(report))

    print(f"Telemetry JSON report : {json_path}")
    print(f"Telemetry text report : {txt_path}")


def build_output_paths(run_id: str, snapshot_name: str, profile: str) -> Tuple[str, str]:
    base_dir = os.path.join("artifacts", "campaigns", run_id, "telemetry")
    ensure_dir(base_dir)
    json_path = os.path.join(base_dir, f"{snapshot_name}_{profile}.json")
    txt_path = os.path.join(base_dir, f"{snapshot_name}_{profile}.txt")
    return json_path, txt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect telemetry snapshots via gnmic and normalize them."
    )
    parser.add_argument("--source-type", default="campaign")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--nodes", required=True, help="comma-separated node names or IPs")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--inventory", default=DEFAULT_INVENTORY)
    parser.add_argument("--telemetry-server", default=DEFAULT_TELEMETRY_SERVER)
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--default-gnmi-port", type=int, default=DEFAULT_GNMI_PORT)
    parser.add_argument("--topology", default=DEFAULT_TOPOLOGY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    topology_node_interfaces = _load_topology_node_interfaces(
        getattr(args, "topology", None)
    )
    try:
        catalog = load_catalog(args.catalog)
        paths = get_profile_paths(catalog, args.profile)
        inventory = load_inventory(args.inventory)
        validate_inventory(inventory)
        nodes = parse_nodes(args.nodes)

        report = collect_snapshot(
            telemetry_server=args.telemetry_server,
            ssh_user=args.ssh_user,
            nodes=nodes,
            paths=paths,
            inventory=inventory,
            timeout=args.timeout,
            snapshot_name=args.snapshot_name,
            profile=args.profile,
            source_type=args.source_type,
            run_id=args.run_id,
            default_gnmi_port=args.default_gnmi_port,
            topology_path=args.topology,
            topology_node_interfaces=topology_node_interfaces,
        )

        json_path, txt_path = build_output_paths(
            run_id=args.run_id,
            snapshot_name=args.snapshot_name,
            profile=args.profile,
        )

        write_json(json_path, report)
        write_text(txt_path, render_text_report(report))

        print(f"Telemetry JSON report : {json_path}")
        print(f"Telemetry text report : {txt_path}")
        print("")
        print("TELEMETRY SNAPSHOT SUMMARY")
        print(f"  Telemetry server : {report.get('telemetry_server')}")
        print(f"  Profile          : {report.get('profile')}")
        print(f"  Nodes            : {report.get('total_nodes')}")
        print(f"  OK nodes         : {report.get('ok_nodes')}")
        print(f"  Failed nodes     : {report.get('failed_nodes')}")

        return 0

    except Exception as exc:  # noqa
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
