from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts" / "campaigns"
WEBUI_DIR = BASE_DIR / "webui"

app = FastAPI(title="Fabric RCA UI")

if WEBUI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEBUI_DIR)), name="static")
    app.mount("/artifacts", StaticFiles(directory=str(BASE_DIR / "artifacts")), name="artifacts")


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/")
def root() -> FileResponse:
    index_file = WEBUI_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="webui/index.html not found")
    return FileResponse(index_file)


@app.get("/api/rca/cases")
def list_cases() -> dict[str, Any]:
    if not ARTIFACTS_DIR.exists():
        return {"cases": []}

    cases: list[dict[str, Any]] = []

    for case_dir in ARTIFACTS_DIR.iterdir():
        if not case_dir.is_dir():
            continue

        ui_report = case_dir / "rca_ui_report.json"
        case_summary = case_dir / "rca_case_summary.json"

        if ui_report.exists():
            try:
                data = load_json_file(ui_report)
                run_metadata = data.get("run_metadata", {}) or {}
                summary = data.get("summary", {}) or {}
                events = data.get("events", []) or []
                top_event = events[0] if events else {}

                cases.append(
                    {
                        "run_id": run_metadata.get("run_id", case_dir.name),
                        "intent_name": run_metadata.get("intent_name", ""),
                        "profile": run_metadata.get("profile", ""),
                        "generated_at": run_metadata.get("generated_at", ""),
                        "primary_cause": summary.get("primary_cause", ""),
                        "severity": summary.get("severity", "normal"),
                        "confidence": summary.get("confidence", 0),
                        "event_count": len(events),
                        "top_event_name": top_event.get("event_name", ""),
                    }
                )
            except Exception:
                cases.append(
                    {
                        "run_id": case_dir.name,
                        "intent_name": "",
                        "profile": "",
                        "generated_at": "",
                        "primary_cause": "failed-to-read-rca-ui-report",
                        "severity": "low",
                        "confidence": 0,
                        "event_count": 0,
                        "top_event_name": "",
                    }
                )

        elif case_summary.exists():
            try:
                data = load_json_file(case_summary)
                cases.append(
                    {
                        "run_id": data.get("run_id", case_dir.name),
                        "intent_name": data.get("intent_name", ""),
                        "profile": data.get("profile", ""),
                        "generated_at": data.get("generated_at", ""),
                        "primary_cause": "rca-ui-report-not-generated",
                        "severity": "low",
                        "confidence": 0,
                        "event_count": 0,
                        "top_event_name": "",
                    }
                )
            except Exception:
                cases.append(
                    {
                        "run_id": case_dir.name,
                        "intent_name": "",
                        "profile": "",
                        "generated_at": "",
                        "primary_cause": "failed-to-read-case-summary",
                        "severity": "low",
                        "confidence": 0,
                        "event_count": 0,
                        "top_event_name": "",
                    }
                )

    cases.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    return {"cases": cases}


@app.get("/api/rca/cases/{run_id}")
def get_case(run_id: str) -> dict[str, Any]:
    case_dir = ARTIFACTS_DIR / run_id
    ui_report = case_dir / "rca_ui_report.json"

    if not ui_report.exists():
        raise HTTPException(
            status_code=404,
            detail=f"rca_ui_report.json not found for run_id={run_id}",
        )

    try:
        return load_json_file(ui_report)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
