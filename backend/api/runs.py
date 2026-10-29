"""
Runs API — Past Pipeline Run History
GET  /api/runs           — list all run summaries (newest first)
GET  /api/runs/{run_id}  — get full run data (all tabs)
"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from models import RunRecord, RunSummary
from config import settings
from pipeline import logger

router = APIRouter()


def _load_runs() -> dict:
    path = Path(settings.runs_data_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error(f"Runs load error: {exc}")
        return {}


def _save_runs(runs: dict) -> None:
    path = Path(settings.runs_data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(runs, f, ensure_ascii=False, indent=2)


def save_run(record: RunRecord) -> None:
    """Called from traverse.py after pipeline completes."""
    runs = _load_runs()
    runs[record.run_id] = record.model_dump()
    _save_runs(runs)
    logger.info(f"Run saved: {record.run_id} — '{record.query[:60]}'")


@router.get("/runs")
async def list_runs():
    data = _load_runs()
    summaries = []
    for raw in data.values():
        try:
            summaries.append(RunSummary(
                run_id=raw["run_id"],
                query=raw["query"],
                timestamp=raw["timestamp"],
                model=raw["model"],
                token_usage=raw.get("token_usage", {}),
                paper_count=raw.get("paper_count", 0),
                lens_names=raw.get("lens_names", []),
                rupture_triggered=raw.get("rupture_triggered", False),
            ))
        except Exception as exc:
            logger.warning(f"Skipping malformed run record: {exc}")
    summaries.sort(key=lambda s: s.timestamp, reverse=True)
    return {"runs": [s.model_dump() for s in summaries]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    data = _load_runs()
    raw = data.get(run_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Run not found.")
    return raw
