import json

from fastapi import APIRouter, HTTPException

from ingestion.config import ROOT_DIR

router = APIRouter()
REPORT = ROOT_DIR / "evaluation" / "report.json"


@router.get("/evaluation/report", tags=["Evaluation"])
def evaluation_report():
    """The latest report written by `python -m evaluation.runner` (404 until one exists)."""
    if not REPORT.exists():
        raise HTTPException(404, "No evaluation report yet. Run: python -m evaluation.runner")
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    data.pop("per_question_raw", None)
    return data
