import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path("/root/fabric-controller")
ARTIFACTS_DIR = BASE_DIR / "artifacts"
RUN_MANAGER_DIR = ARTIFACTS_DIR / "run_manager"
RUNS_INDEX_FILE = RUN_MANAGER_DIR / "runs_index.json"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_runs_index():
    ensure_dir(RUN_MANAGER_DIR)

    if not RUNS_INDEX_FILE.exists():
        return {"runs": []}

    with open(RUNS_INDEX_FILE, "r") as f:
        return json.load(f)


def save_runs_index(index_data):
    ensure_dir(RUN_MANAGER_DIR)
    with open(RUNS_INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)


def add_run_record(record):
    index_data = load_runs_index()
    index_data["runs"].append(record)
    save_runs_index(index_data)


def update_run_record(run_id, updates):
    index_data = load_runs_index()

    for run in index_data["runs"]:
        if run.get("run_id") == run_id:
            run.update(updates)
            break

    save_runs_index(index_data)


def get_run_record(run_id):
    index_data = load_runs_index()
    for run in index_data["runs"]:
        if run.get("run_id") == run_id:
            return run
    return None


def list_runs():
    index_data = load_runs_index()
    return index_data.get("runs", [])


def build_orchestrator_command(
    mode,
    settle_seconds=10,
    interval_seconds=0,
    iterations=1,
    parallel=1,
    stop_on_failure=False,
    run_id=None,
    node=None,
    interface=None,
    targets=None,
):
    cmd = [
        "python",
        "-m",
        "controller.stress_orchestrator",
        "--mode", str(mode),
        "--settle-seconds", str(settle_seconds),
        "--interval-seconds", str(interval_seconds),
        "--iterations", str(iterations),
        "--parallel", str(parallel),
    ]

    if stop_on_failure:
        cmd.append("--stop-on-failure")

    if run_id:
        cmd.extend(["--run-id", str(run_id)])

    if node:
        cmd.extend(["--node", str(node)])

    if interface:
        cmd.extend(["--interface", str(interface)])

    if targets:
        cmd.extend(["--targets", str(targets)])

    return cmd


def start_run(
    mode,
    settle_seconds=10,
    interval_seconds=0,
    iterations=1,
    parallel=1,
    stop_on_failure=False,
    run_id=None,
    node=None,
    interface=None,
    targets=None,
):
    ensure_dir(RUN_MANAGER_DIR)

    cmd = build_orchestrator_command(
        mode=mode,
        settle_seconds=settle_seconds,
        interval_seconds=interval_seconds,
        iterations=iterations,
        parallel=parallel,
        stop_on_failure=stop_on_failure,
        run_id=run_id,
        node=node,
        interface=interface,
        targets=targets,
    )

    log_file = RUN_MANAGER_DIR / f"{run_id}.log"

    with open(log_file, "w") as logf:
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=logf,
            stderr=logf,
            text=True,
        )

    record = {
        "run_id": run_id,
        "mode": mode,
        "status": "running",
        "pid": process.pid,
        "command": cmd,
        "targets": targets,
        "node": node,
        "interface": interface,
        "parallel": parallel,
        "iterations": iterations,
        "interval_seconds": interval_seconds,
        "settle_seconds": settle_seconds,
        "stop_on_failure": stop_on_failure,
        "started_at": utc_now(),
        "ended_at": None,
        "log_file": str(log_file),
        "archive_root": f"/root/fabric-controller/artifacts/orchestrator/{run_id}",
    }

    add_run_record(record)
    return record


def is_pid_running(pid):
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def refresh_run_status(run_id):
    run = get_run_record(run_id)
    if not run:
        return None

    if run.get("status") != "running":
        return run

    pid = run.get("pid")
    archive_root = Path(run.get("archive_root", ""))
    report_file = archive_root / "stress_orchestrator_report.json"

    if pid and is_pid_running(pid):
        return run

    if report_file.exists():
        try:
            with open(report_file, "r") as f:
                report = json.load(f)
            final_status = report.get("overall_status", "unknown")
        except Exception:
            final_status = "unknown"
    else:
        final_status = "unknown"

    updated = {
        "status": final_status,
        "ended_at": utc_now(),
    }
    update_run_record(run_id, updated)

    run = get_run_record(run_id)
    return run
