from datetime import datetime
from pathlib import Path
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from service.run_manager import (
    start_run,
    list_runs,
    get_run_record,
    refresh_run_status,
)

import subprocess


BASE_DIR = Path("/root/fabric-controller")
CAMPAIGNS_DIR = BASE_DIR / "campaigns"
CAMPAIGN_ARTIFACTS_DIR = BASE_DIR / "artifacts" / "campaigns"


app = FastAPI(title="AI-DC Stress Controller API")


class StartRunRequest(BaseModel):
    mode: str
    settle_seconds: int = 10
    interval_seconds: int = 0
    iterations: int = 1
    parallel: int = 1
    stop_on_failure: bool = False
    run_id: str | None = None
    node: str | None = None
    interface: str | None = None
    targets: str | None = None


class StartCampaignRequest(BaseModel):
    campaign_file: str
    run_id: str | None = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ai-dc-stress-controller-api",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/runs")
def api_list_runs():
    runs = list_runs()
    return {"runs": runs}


@app.get("/runs/{run_id}")
def api_get_run(run_id: str):
    run = refresh_run_status(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return run


@app.post("/runs/start")
def api_start_run(req: StartRunRequest):
    run_id = req.run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    existing = get_run_record(run_id)
    if existing:
        raise HTTPException(status_code=400, detail=f"run_id already exists: {run_id}")

    record = start_run(
        mode=req.mode,
        settle_seconds=req.settle_seconds,
        interval_seconds=req.interval_seconds,
        iterations=req.iterations,
        parallel=req.parallel,
        stop_on_failure=req.stop_on_failure,
        run_id=run_id,
        node=req.node,
        interface=req.interface,
        targets=req.targets,
    )
    return record


@app.get("/runs/{run_id}/report")
def api_get_run_report(run_id: str):
    run = get_run_record(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")

    report_path = Path(run["archive_root"]) / "stress_orchestrator_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="report not available yet")

    with open(report_path, "r") as f:
        return json.load(f)


@app.get("/campaigns")
def api_list_campaigns():
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted([p.name for p in CAMPAIGNS_DIR.glob("*.json")])
    return {"campaigns": files}


@app.post("/campaigns/start")
def api_start_campaign(req: StartCampaignRequest):
    campaign_path = Path(req.campaign_file)
    if not campaign_path.is_absolute():
        campaign_path = CAMPAIGNS_DIR / req.campaign_file

    if not campaign_path.exists():
        raise HTTPException(status_code=404, detail=f"campaign file not found: {campaign_path}")

    run_id = req.run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    archive_root = CAMPAIGN_ARTIFACTS_DIR / run_id

    cmd = [
        "python",
        "-m",
        "controller.campaign_runner",
        "--campaign-file", str(campaign_path),
        "--run-id", run_id,
    ]

    log_dir = BASE_DIR / "artifacts" / "run_manager"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"campaign_{run_id}.log"

    with open(log_file, "w") as logf:
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=logf,
            stderr=logf,
            text=True,
        )

    return {
        "run_id": run_id,
        "status": "running",
        "pid": process.pid,
        "campaign_file": str(campaign_path),
        "log_file": str(log_file),
        "archive_root": str(archive_root),
    }


@app.get("/campaigns/{run_id}/report")
def api_get_campaign_report(run_id: str):
    report_path = CAMPAIGN_ARTIFACTS_DIR / run_id / "campaign_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="campaign report not available yet")

    with open(report_path, "r") as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI-DC Stress Controller</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body { font-family: Arial, sans-serif; margin: 24px; background: #f7f9fc; color: #1f2937; }
            h1, h2 { margin-bottom: 10px; }
            .card { background: white; border-radius: 10px; padding: 18px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
            label { display: block; margin-top: 10px; font-weight: 600; }
            input, select, textarea { width: 100%; padding: 8px; margin-top: 6px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; }
            button { margin-top: 14px; padding: 10px 16px; border: none; border-radius: 6px; background: #2563eb; color: white; cursor: pointer; font-weight: 600; }
            button:hover { background: #1d4ed8; }
            .secondary { background: #475569; }
            .secondary:hover { background: #334155; }
            .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
            pre { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 6px; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; background: white; }
            th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; font-size: 14px; }
            th { background: #e2e8f0; }
            .small { font-size: 13px; color: #475569; }
            a { color: #2563eb; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>AI-DC Stress Controller</h1>
        <p class="small">Runs, campaigns, and reports.</p>

        <div class="card">
            <h2>Service Health</h2>
            <button onclick="loadHealth()">Refresh Health</button>
            <pre id="healthBox">Loading...</pre>
        </div>

        <div class="card">
            <h2>Start Campaign</h2>
            <label>Campaign File</label>
            <input id="campaign_file" value="pfe_parallel_bughunt.json" />
            <label>Campaign Run ID (optional)</label>
            <input id="campaign_run_id" placeholder="auto-generated if empty" />
            <button onclick="startCampaign()">Start Campaign</button>
            <pre id="campaignResult">No campaign started yet.</pre>
        </div>

        <div class="card">
            <h2>Available Campaigns</h2>
            <button class="secondary" onclick="loadCampaigns()">Refresh Campaigns</button>
            <pre id="campaignList">Loading...</pre>
        </div>

        <div class="card">
            <h2>Run History</h2>
            <button class="secondary" onclick="loadRuns()">Refresh Runs</button>
            <div id="runsTable">Loading...</div>
        </div>

        <script>
            async function loadHealth() {
                const res = await fetch('/health');
                const data = await res.json();
                document.getElementById('healthBox').textContent = JSON.stringify(data, null, 2);
            }

            async function loadCampaigns() {
                const res = await fetch('/campaigns');
                const data = await res.json();
                document.getElementById('campaignList').textContent = JSON.stringify(data, null, 2);
            }

            async function loadRuns() {
                const res = await fetch('/runs');
                const data = await res.json();
                const runs = data.runs || [];

                if (!runs.length) {
                    document.getElementById('runsTable').innerHTML = '<p>No runs found.</p>';
                    return;
                }

                let html = '<table><thead><tr>' +
                    '<th>Run ID</th><th>Mode</th><th>Status</th><th>PID</th><th>Iterations</th><th>Parallel</th><th>Started</th><th>Report</th>' +
                    '</tr></thead><tbody>';

                for (const run of runs.slice().reverse()) {
                    const runId = run.run_id || '';
                    html += '<tr>' +
                        `<td><a href="/runs/${runId}" target="_blank">${runId}</a></td>` +
                        `<td>${run.mode || ''}</td>` +
                        `<td>${run.status || ''}</td>` +
                        `<td>${run.pid || ''}</td>` +
                        `<td>${run.iterations || ''}</td>` +
                        `<td>${run.parallel || ''}</td>` +
                        `<td>${run.started_at || ''}</td>` +
                        `<td><a href="/runs/${runId}/report" target="_blank">report</a></td>` +
                        '</tr>';
                }

                html += '</tbody></table>';
                document.getElementById('runsTable').innerHTML = html;
            }

            async function startCampaign() {
                const payload = {
                    campaign_file: document.getElementById('campaign_file').value,
                    run_id: document.getElementById('campaign_run_id').value || null
                };

                const res = await fetch('/campaigns/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });

                const data = await res.json();
                document.getElementById('campaignResult').textContent = JSON.stringify(data, null, 2);
            }

            loadHealth();
            loadCampaigns();
            loadRuns();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
