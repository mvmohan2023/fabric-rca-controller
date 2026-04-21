import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path("/root/fabric-controller")
CAMPAIGNS_DIR = BASE_DIR / "campaigns"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CAMPAIGN_ARTIFACTS_DIR = ARTIFACTS_DIR / "campaigns"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def default_run_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI-DC Stress Campaign Runner"
    )
    parser.add_argument(
        "--campaign-file",
        required=True,
        help="Campaign JSON file name or absolute path",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional campaign run id",
    )
    return parser.parse_args()


def resolve_campaign_file(campaign_file: str) -> Path:
    path = Path(campaign_file)
    if path.is_absolute():
        resolved = path
    else:
        resolved = CAMPAIGNS_DIR / campaign_file

    if not resolved.exists():
        raise FileNotFoundError(f"Campaign file not found: {resolved}")

    return resolved


def load_campaign(path: Path):
    with open(path, "r") as f:
        return json.load(f)


def run_cmd(cmd, step_name, cwd=None):
    print(f"\n[STEP] {step_name}")
    print(f"  CMD: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=cwd or str(BASE_DIR),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    return {
        "step": step_name,
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": "pass" if result.returncode == 0 else "fail",
    }


def summarize_steps(steps):
    failed = [x for x in steps if x["status"] != "pass"]
    return {
        "total_steps": len(steps),
        "failed_steps": len(failed),
        "status": "pass" if not failed else "fail",
        "failed_step_names": [x["step"] for x in failed],
    }


def write_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def build_orchestrator_cmd(
    mode,
    run_id,
    settle_seconds,
    interval_seconds=0,
    iterations=1,
    parallel=1,
    stop_on_failure=False,
    node=None,
    interface=None,
    targets=None,
):
    cmd = [
        "python",
        "-m",
        "controller.stress_orchestrator",
        "--mode", str(mode),
        "--run-id", str(run_id),
        "--settle-seconds", str(settle_seconds),
        "--interval-seconds", str(interval_seconds),
        "--iterations", str(iterations),
        "--parallel", str(parallel),
    ]

    if stop_on_failure:
        cmd.append("--stop-on-failure")

    if node:
        cmd.extend(["--node", str(node)])

    if interface:
        cmd.extend(["--interface", str(interface)])

    if targets:
        cmd.extend(["--targets", str(targets)])

    return cmd


def load_orchestrator_report(run_id: str):
    report_path = ARTIFACTS_DIR / "orchestrator" / run_id / "stress_orchestrator_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Orchestrator report not found: {report_path}")
    with open(report_path, "r") as f:
        return json.load(f)


def build_parallel_targets(events):
    """
    Convert campaign event list to orchestrator --targets format.

    bgp_clear:
      leaf1,leaf2

    interface_bounce:
      leaf1|et-0/0/11:0,leaf2|et-0/0/11:0
    """
    if not events:
        raise ValueError("parallel phase has no events")

    event_types = {e.get("event_type") for e in events}
    if len(event_types) != 1:
        raise ValueError("parallel phase currently supports one event_type per phase")

    event_type = next(iter(event_types))

    if event_type == "bgp_clear":
        return event_type, ",".join(e["node"] for e in events)

    if event_type == "interface_bounce":
        return event_type, ",".join(f"{e['node']}|{e['interface']}" for e in events)

    raise ValueError(f"Unsupported event_type for parallel phase: {event_type}")


def execute_validate_phase(phase_name: str, phase_run_id: str, settle_seconds: int):
    cmd = build_orchestrator_cmd(
        mode="noop",
        run_id=phase_run_id,
        settle_seconds=settle_seconds,
        iterations=1,
        parallel=1,
    )
    step = run_cmd(cmd, f"{phase_name} (validate/noop)")
    phase_report = None
    if step["returncode"] == 0:
        phase_report = load_orchestrator_report(phase_run_id)

    return {
        "phase_name": phase_name,
        "phase_type": "validate",
        "status": "pass" if step["returncode"] == 0 else "fail",
        "orchestrator_run_id": phase_run_id,
        "step": step,
        "report_summary": phase_report.get("verdict") if phase_report else None,
    }


def execute_sleep_phase(phase: dict):
    seconds = int(phase.get("seconds", 0))
    print(f"\n[PHASE] sleep for {seconds} seconds")
    time.sleep(seconds)
    return {
        "phase_name": phase.get("name", "sleep"),
        "phase_type": "sleep",
        "status": "pass",
        "sleep_seconds": seconds,
    }


def execute_parallel_phase(phase: dict, phase_run_id: str, defaults: dict, campaign: dict):
    phase_name = phase.get("name", "parallel")
    events = phase.get("events", [])
    settle_seconds = int(phase.get("settle_seconds", defaults.get("settle_seconds", 10)))
    parallel = int(phase.get("parallel", defaults.get("parallel", max(1, len(events)))))
    stop_on_failure = bool(campaign.get("stop_on_failure", False))

    mode, targets = build_parallel_targets(events)

    cmd = build_orchestrator_cmd(
        mode=mode,
        run_id=phase_run_id,
        settle_seconds=settle_seconds,
        interval_seconds=0,
        iterations=1,
        parallel=parallel,
        stop_on_failure=stop_on_failure,
        targets=targets,
    )

    step = run_cmd(cmd, f"{phase_name} ({mode})")
    phase_report = None
    if step["returncode"] == 0:
        phase_report = load_orchestrator_report(phase_run_id)
    else:
        try:
            phase_report = load_orchestrator_report(phase_run_id)
        except Exception:
            phase_report = None

    return {
        "phase_name": phase_name,
        "phase_type": "parallel",
        "status": "pass" if step["returncode"] == 0 else "fail",
        "mode": mode,
        "targets": targets,
        "orchestrator_run_id": phase_run_id,
        "step": step,
        "report_summary": phase_report.get("verdict") if phase_report else None,
    }


def execute_sequential_phase(phase: dict, phase_run_id_prefix: str, defaults: dict, campaign: dict):
    phase_name = phase.get("name", "sequential")
    events = phase.get("events", [])
    settle_seconds_default = int(defaults.get("settle_seconds", 10))
    stop_on_failure = bool(campaign.get("stop_on_failure", False))

    event_results = []
    overall_fail = False

    for idx, event in enumerate(events, start=1):
        event_type = event.get("event_type")
        event_run_id = f"{phase_run_id_prefix}_event{idx:02d}"

        if event_type == "sleep":
            seconds = int(event.get("seconds", 0))
            print(f"\n[EVENT] sequential sleep {seconds} seconds")
            time.sleep(seconds)
            event_results.append({
                "event_index": idx,
                "event_type": "sleep",
                "status": "pass",
                "sleep_seconds": seconds,
            })
            continue

        settle_seconds = int(event.get("settle_seconds", settle_seconds_default))
        cmd = None

        if event_type == "bgp_clear":
            cmd = build_orchestrator_cmd(
                mode="bgp_clear",
                run_id=event_run_id,
                settle_seconds=settle_seconds,
                iterations=1,
                parallel=1,
                stop_on_failure=stop_on_failure,
                node=event["node"],
            )
        elif event_type == "interface_bounce":
            cmd = build_orchestrator_cmd(
                mode="interface_bounce",
                run_id=event_run_id,
                settle_seconds=settle_seconds,
                iterations=1,
                parallel=1,
                stop_on_failure=stop_on_failure,
                node=event["node"],
                interface=event["interface"],
            )
        else:
            event_results.append({
                "event_index": idx,
                "event_type": event_type,
                "status": "fail",
                "details": f"Unsupported sequential event_type: {event_type}",
            })
            overall_fail = True
            if stop_on_failure:
                break
            continue

        step = run_cmd(cmd, f"{phase_name} event{idx:02d} ({event_type})")
        event_report = None
        if step["returncode"] == 0:
            event_report = load_orchestrator_report(event_run_id)
        else:
            try:
                event_report = load_orchestrator_report(event_run_id)
            except Exception:
                event_report = None

        event_status = "pass" if step["returncode"] == 0 else "fail"
        if event_status == "fail":
            overall_fail = True

        event_results.append({
            "event_index": idx,
            "event_type": event_type,
            "status": event_status,
            "orchestrator_run_id": event_run_id,
            "step": step,
            "report_summary": event_report.get("verdict") if event_report else None,
        })

        if event_status == "fail" and stop_on_failure:
            break

    return {
        "phase_name": phase_name,
        "phase_type": "sequential",
        "status": "fail" if overall_fail else "pass",
        "event_results": event_results,
    }


def execute_phase(phase: dict, iteration: int, phase_index: int, campaign_run_id: str, defaults: dict, campaign: dict):
    phase_type = phase.get("type")
    phase_name = phase.get("name", f"phase_{phase_index}")
    phase_run_id = f"{campaign_run_id}_iter{iteration:03d}_phase{phase_index:02d}"

    print("\n" + "-" * 72)
    print(f"[PHASE] iteration={iteration} phase={phase_index} name={phase_name} type={phase_type}")
    print("-" * 72)

    if phase_type == "parallel":
        return execute_parallel_phase(phase, phase_run_id, defaults, campaign)

    if phase_type == "sequential":
        return execute_sequential_phase(phase, phase_run_id, defaults, campaign)

    if phase_type == "validate":
        settle_seconds = int(phase.get("settle_seconds", defaults.get("settle_seconds", 10)))
        return execute_validate_phase(phase_name, phase_run_id, settle_seconds)

    if phase_type == "sleep":
        return execute_sleep_phase(phase)

    if phase_type == "traffic":
        return {
            "phase_name": phase_name,
            "phase_type": "traffic",
            "status": "pass",
            "details": "traffic phase placeholder - not implemented yet",
            "phase": phase,
        }

    return {
        "phase_name": phase_name,
        "phase_type": phase_type,
        "status": "fail",
        "details": f"Unsupported phase type: {phase_type}",
    }


def build_iteration_result(iteration: int, phase_results: list):
    failed = [x for x in phase_results if x.get("status") != "pass"]
    return {
        "iteration": iteration,
        "timestamp": utc_now(),
        "status": "pass" if not failed else "fail",
        "phase_results": phase_results,
        "failed_phase_names": [x.get("phase_name") for x in failed],
    }


def build_campaign_report(campaign, campaign_file: Path, campaign_run_id: str, baseline_step: dict, baseline_report: dict, iteration_results: list):
    failed_iterations = [x for x in iteration_results if x["status"] != "pass"]
    overall_status = "pass" if baseline_step["status"] == "pass" and not failed_iterations else "fail"

    return {
        "campaign_name": campaign.get("campaign_name"),
        "description": campaign.get("description"),
        "campaign_file": str(campaign_file),
        "run_id": campaign_run_id,
        "timestamp": utc_now(),
        "overall_status": overall_status,
        "baseline": {
            "step": baseline_step,
            "report_summary": baseline_report.get("verdict") if baseline_report else None,
        },
        "iterations_requested": int(campaign.get("iterations", 1)),
        "iterations_completed": len(iteration_results),
        "iterations_failed": len(failed_iterations),
        "iteration_results": iteration_results,
    }


def main():
    args = parse_args()

    campaign_path = resolve_campaign_file(args.campaign_file)
    campaign = load_campaign(campaign_path)

    campaign_run_id = args.run_id or default_run_id()
    archive_root = CAMPAIGN_ARTIFACTS_DIR / campaign_run_id
    ensure_dir(archive_root)

    defaults = campaign.get("defaults", {})
    baseline_precheck = bool(campaign.get("baseline_precheck", True))
    iterations = int(campaign.get("iterations", 1))
    interval_seconds = int(campaign.get("interval_seconds", 0))
    stop_on_failure = bool(campaign.get("stop_on_failure", False))
    phases = campaign.get("phases", [])

    if iterations < 1:
        print("ERROR: campaign iterations must be >= 1", file=sys.stderr)
        sys.exit(1)

    if not phases:
        print("ERROR: campaign has no phases", file=sys.stderr)
        sys.exit(1)

    baseline_step = {
        "step": "baseline_precheck",
        "status": "pass",
        "details": "skipped",
    }
    baseline_report = None

    if baseline_precheck:
        baseline_run_id = f"{campaign_run_id}_baseline"
        baseline_settle = int(defaults.get("settle_seconds", 10))
        cmd = build_orchestrator_cmd(
            mode="noop",
            run_id=baseline_run_id,
            settle_seconds=baseline_settle,
            iterations=1,
            parallel=1,
        )
        baseline_step = run_cmd(cmd, "baseline_precheck")
        if baseline_step["returncode"] == 0:
            baseline_report = load_orchestrator_report(baseline_run_id)
        else:
            try:
                baseline_report = load_orchestrator_report(baseline_run_id)
            except Exception:
                baseline_report = None

        if baseline_step["status"] != "pass":
            report = build_campaign_report(
                campaign, campaign_path, campaign_run_id,
                baseline_step, baseline_report, []
            )
            write_json(archive_root / "campaign_report.json", report)
            print(f"\nCampaign report: {archive_root / 'campaign_report.json'}")
            sys.exit(1)

    iteration_results = []

    for iteration in range(1, iterations + 1):
        print("\n" + "=" * 80)
        print(f"[CAMPAIGN ITERATION] {iteration}/{iterations}")
        print("=" * 80)

        phase_results = []

        for phase_index, phase in enumerate(phases, start=1):
            result = execute_phase(
                phase=phase,
                iteration=iteration,
                phase_index=phase_index,
                campaign_run_id=campaign_run_id,
                defaults=defaults,
                campaign=campaign,
            )
            phase_results.append(result)

            if result["status"] != "pass" and stop_on_failure:
                print(f"\n[STOP] phase '{result.get('phase_name')}' failed and stop_on_failure is set")
                break

        iteration_result = build_iteration_result(iteration, phase_results)
        iteration_results.append(iteration_result)

        iteration_dir = archive_root / f"iteration_{iteration:03d}"
        ensure_dir(iteration_dir)
        write_json(iteration_dir / "iteration_report.json", iteration_result)

        if iteration_result["status"] != "pass" and stop_on_failure:
            print(f"\n[STOP] iteration {iteration} failed and stop_on_failure is set")
            break

        if iteration < iterations and interval_seconds > 0:
            print(f"\n[WAIT] sleeping {interval_seconds} seconds before next iteration")
            time.sleep(interval_seconds)

    final_report = build_campaign_report(
        campaign=campaign,
        campaign_file=campaign_path,
        campaign_run_id=campaign_run_id,
        baseline_step=baseline_step,
        baseline_report=baseline_report,
        iteration_results=iteration_results,
    )

    report_json = archive_root / "campaign_report.json"
    write_json(report_json, final_report)

    print(f"\nCampaign report: {report_json}")
    print("\nCAMPAIGN SUMMARY")
    print(f"  Campaign name        : {final_report.get('campaign_name')}")
    print(f"  Run ID               : {campaign_run_id}")
    print(f"  Overall status       : {final_report.get('overall_status')}")
    print(f"  Iterations requested : {final_report.get('iterations_requested')}")
    print(f"  Iterations completed : {final_report.get('iterations_completed')}")
    print(f"  Iterations failed    : {final_report.get('iterations_failed')}")

    sys.exit(0 if final_report["overall_status"] == "pass" else 1)


if __name__ == "__main__":
    main()
