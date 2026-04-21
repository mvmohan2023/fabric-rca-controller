import argparse
import subprocess
import time
import sys


def run(cmd):
    print("\n[RUN]")
    print(" ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        raise RuntimeError(f"Command failed rc={rc}")


def main():

    parser = argparse.ArgumentParser(description="Full Ixia stress + RCA runner")

    parser.add_argument("--run-id", required=True)
    parser.add_argument("--api-server", required=True)

    parser.add_argument("--monitor-iterations", type=int, default=12)
    parser.add_argument("--monitor-interval", type=int, default=5)

    parser.add_argument("--inventory",
                        default="controller/ixia_inventory.json")

    args = parser.parse_args()

    run_id = args.run_id

    print("\n========== STRESS LIVE RUNNER ==========\n")

    # ---------------------------------------------------------
    # 1 Traffic start
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.ixia_event_engine",
        "--api-server", args.api_server
    ])

    # ---------------------------------------------------------
    # 2 Live monitor
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.ixia_live_monitor",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--iterations", str(args.monitor_iterations),
        "--poll-interval-sec", str(args.monitor_interval)
    ])

    # ---------------------------------------------------------
    # 3 Collect POST stats
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.ixia_rocev2_stats",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--snapshot-name", "rocev2_post"
    ])

    # ---------------------------------------------------------
    # 4 Verifier
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.rocev2_verifier",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--pre", f"artifacts/campaigns/{run_id}/traffic/rocev2_pre_ixia_rocev2_flow_stats.json",
        "--post", f"artifacts/campaigns/{run_id}/traffic/rocev2_post_ixia_rocev2_flow_stats.json"
    ])

    # ---------------------------------------------------------
    # 5 Deep inspection
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.rocev2_deep_inspector",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--pre", f"artifacts/campaigns/{run_id}/traffic/rocev2_pre_ixia_rocev2_flow_stats.json",
        "--post", f"artifacts/campaigns/{run_id}/traffic/rocev2_post_ixia_rocev2_flow_stats.json",
        "--verdict", f"artifacts/campaigns/{run_id}/traffic/rocev2_verdict.json"
    ])

    # ---------------------------------------------------------
    # 6 Hotspot report
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.rocev2_hotspot_report",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--deep", f"artifacts/campaigns/{run_id}/traffic/rocev2_deep_inspection.json"
    ])

    # ---------------------------------------------------------
    # 7 Congestion inspection
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.congestion_inspector",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--verdict", f"artifacts/campaigns/{run_id}/traffic/rocev2_verdict.json",
        "--deep", f"artifacts/campaigns/{run_id}/traffic/rocev2_deep_inspection.json",
        "--hotspot", f"artifacts/campaigns/{run_id}/traffic/rocev2_hotspot_report.json"
    ])

    # ---------------------------------------------------------
    # 8 Root cause correlation
    # ---------------------------------------------------------

    run([
        "python", "-m", "controller.root_cause_correlator",
        "--source-type", "campaign",
        "--run-id", run_id,
        "--congestion", f"artifacts/campaigns/{run_id}/traffic/congestion_inspection.json",
        "--inventory", args.inventory
    ])

    print("\n========================================")
    print(" STRESS RUN COMPLETE")
    print("========================================\n")

    print("Final RCA file:")
    print(f"artifacts/campaigns/{run_id}/traffic/root_cause_correlation.json")


if __name__ == "__main__":
    main()
