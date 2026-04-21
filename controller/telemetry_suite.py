# controller/telemetry_suite.py

import argparse
import os
import subprocess
import sys
import time
from typing import List, Tuple


DEFAULT_CATALOG = os.path.join(os.path.dirname(__file__), "path_catalog.json")
DEFAULT_INVENTORY = os.path.join(os.path.dirname(__file__), "inventory.json")
DEFAULT_TELEMETRY_SERVER = os.environ.get("TELEMETRY_SERVER", "10.83.6.46")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def telemetry_output_dir(run_id: str) -> str:
    out_dir = os.path.join("artifacts", "campaigns", run_id, "telemetry")
    ensure_dir(out_dir)
    return out_dir


def snapshot_paths(run_id: str, snapshot_name: str, profile: str) -> Tuple[str, str]:
    out_dir = telemetry_output_dir(run_id)
    json_path = os.path.join(out_dir, f"{snapshot_name}_{profile}.json")
    txt_path = os.path.join(out_dir, f"{snapshot_name}_{profile}.txt")
    return json_path, txt_path


def diff_paths(run_id: str, profile: str) -> Tuple[str, str]:
    out_dir = telemetry_output_dir(run_id)
    json_path = os.path.join(out_dir, f"diff_{profile}.json")
    txt_path = os.path.join(out_dir, f"diff_{profile}.txt")
    return json_path, txt_path


def anomaly_paths(run_id: str, profile: str) -> Tuple[str, str]:
    out_dir = telemetry_output_dir(run_id)
    json_path = os.path.join(out_dir, f"anomaly_{profile}.json")
    txt_path = os.path.join(out_dir, f"anomaly_{profile}.txt")
    return json_path, txt_path


def run_command(cmd: List[str], step_name: str) -> None:
    print("")
    print(f"[SUITE] {step_name}")
    print("[SUITE] command:")
    print("  " + " ".join(cmd))

    proc = subprocess.run(cmd)

    if proc.returncode != 0:
        raise RuntimeError(f"{step_name} failed with rc={proc.returncode}")


def build_monitor_cmd(
    run_id: str,
    snapshot_name: str,
    profile: str,
    nodes: str,
    timeout: int,
    source_type: str,
    catalog: str,
    inventory: str,
    telemetry_server: str,
    ssh_user: str,
    default_gnmi_port: int,
) -> List[str]:
    return [
        sys.executable,
        "-m",
        "controller.telemetry_monitor",
        "--source-type", source_type,
        "--run-id", run_id,
        "--snapshot-name", snapshot_name,
        "--profile", profile,
        "--nodes", nodes,
        "--timeout", str(timeout),
        "--catalog", catalog,
        "--inventory", inventory,
        "--telemetry-server", telemetry_server,
        "--ssh-user", ssh_user,
        "--default-gnmi-port", str(default_gnmi_port),
    ]


def build_diff_cmd(
    run_id: str,
    profile: str,
    source_type: str,
    pre_snapshot: str,
    post_snapshot: str,
) -> List[str]:
    return [
        sys.executable,
        "-m",
        "controller.telemetry_diff",
        "--source-type", source_type,
        "--run-id", run_id,
        "--profile", profile,
        "--pre-snapshot", pre_snapshot,
        "--post-snapshot", post_snapshot,
    ]


def build_analyzer_cmd(
    pre_json: str,
    post_json: str,
    out_json: str,
    out_txt: str,
    spike_ratio: float,
    gauge_delta_threshold: float,
) -> List[str]:
    return [
        sys.executable,
        "-m",
        "controller.telemetry_analyzer",
        "--pre", pre_json,
        "--post", post_json,
        "--out-json", out_json,
        "--out-txt", out_txt,
        "--spike-ratio", str(spike_ratio),
        "--gauge-delta-threshold", str(gauge_delta_threshold),
    ]


def render_suite_summary(
    run_id: str,
    profile: str,
    pre_json: str,
    post_json: str,
    diff_json: str,
    anomaly_json: str,
) -> str:
    lines = []
    lines.append("")
    lines.append("TELEMETRY SUITE SUMMARY")
    lines.append(f"  Run ID          : {run_id}")
    lines.append(f"  Profile         : {profile}")
    lines.append(f"  Pre snapshot    : {pre_json}")
    lines.append(f"  Post snapshot   : {post_json}")
    lines.append(f"  Diff report     : {diff_json}")
    lines.append(f"  Anomaly report  : {anomaly_json}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run telemetry pre/post collection, diff, and anomaly analysis."
    )

    parser.add_argument("--source-type", default="campaign")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--nodes", required=True, help="comma-separated node names")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--post-delay",
        type=int,
        default=0,
        help="seconds to wait between pre and post snapshot collection",
    )

    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--inventory", default=DEFAULT_INVENTORY)
    parser.add_argument("--telemetry-server", default=DEFAULT_TELEMETRY_SERVER)
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--default-gnmi-port", type=int, default=60061)

    parser.add_argument("--skip-pre", action="store_true", help="skip pre collection")
    parser.add_argument("--skip-post", action="store_true", help="skip post collection")
    parser.add_argument("--skip-diff", action="store_true", help="skip diff step")
    parser.add_argument("--skip-analyzer", action="store_true", help="skip analyzer step")

    parser.add_argument(
        "--spike-ratio",
        type=float,
        default=5.0,
        help="counter spike ratio threshold for analyzer",
    )
    parser.add_argument(
        "--gauge-delta-threshold",
        type=float,
        default=3.0,
        help="gauge delta threshold for analyzer",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        pre_json, _ = snapshot_paths(args.run_id, "pre", args.profile)
        post_json, _ = snapshot_paths(args.run_id, "post", args.profile)
        diff_json, diff_txt = diff_paths(args.run_id, args.profile)
        anomaly_json, anomaly_txt = anomaly_paths(args.run_id, args.profile)

        if not args.skip_pre:
            pre_cmd = build_monitor_cmd(
                run_id=args.run_id,
                snapshot_name="pre",
                profile=args.profile,
                nodes=args.nodes,
                timeout=args.timeout,
                source_type=args.source_type,
                catalog=args.catalog,
                inventory=args.inventory,
                telemetry_server=args.telemetry_server,
                ssh_user=args.ssh_user,
                default_gnmi_port=args.default_gnmi_port,
            )
            run_command(pre_cmd, "Collect PRE snapshot")

        if not args.skip_pre and not args.skip_post and args.post_delay > 0:
            print("")
            print(f"[SUITE] Waiting {args.post_delay} seconds before POST snapshot...")
            time.sleep(args.post_delay)

        if not args.skip_post:
            post_cmd = build_monitor_cmd(
                run_id=args.run_id,
                snapshot_name="post",
                profile=args.profile,
                nodes=args.nodes,
                timeout=args.timeout,
                source_type=args.source_type,
                catalog=args.catalog,
                inventory=args.inventory,
                telemetry_server=args.telemetry_server,
                ssh_user=args.ssh_user,
                default_gnmi_port=args.default_gnmi_port,
            )
            run_command(post_cmd, "Collect POST snapshot")

        if not args.skip_diff:
            diff_cmd = build_diff_cmd(
                run_id=args.run_id,
                profile=args.profile,
                source_type=args.source_type,
                pre_snapshot="pre",
                post_snapshot="post",
            )
            run_command(diff_cmd, "Run telemetry diff")

        if not args.skip_analyzer:
            analyzer_cmd = build_analyzer_cmd(
                pre_json=pre_json,
                post_json=post_json,
                out_json=anomaly_json,
                out_txt=anomaly_txt,
                spike_ratio=args.spike_ratio,
                gauge_delta_threshold=args.gauge_delta_threshold,
            )
            run_command(analyzer_cmd, "Run telemetry analyzer")

        print(render_suite_summary(
            run_id=args.run_id,
            profile=args.profile,
            pre_json=pre_json,
            post_json=post_json,
            diff_json=diff_json,
            anomaly_json=anomaly_json,
        ))

        return 0

    except Exception as exc:  # noqa
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
