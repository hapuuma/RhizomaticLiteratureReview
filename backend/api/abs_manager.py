"""
V3: ABS List Manager Agent — API Endpoints
Processes user-uploaded ABS journal list files to update the local
journal quality metrics database.

POST /api/abs/upload   — upload CSV file to update journal database
GET  /api/abs/stats    — get current database stats
POST /api/abs/flag     — manually flag a journal as predatory
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from database.abs_store import get_abs_database, parse_abs_csv, add_journals
from pipeline import logger


router = APIRouter()


@router.post("/abs/upload")
async def upload_abs_list(file: UploadFile = File(...)):
    """
    Upload a CSV file containing ABS journal ratings.
    Merges into the local database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")  # handle BOM
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    try:
        journals = parse_abs_csv(text)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}")

    if not journals:
        raise HTTPException(status_code=422, detail="No valid journal entries found in file.")

    stats = add_journals(journals, source_label=file.filename)
    logger.info(f"ABS upload: {stats}")

    return {
        "message": f"Successfully processed {file.filename}",
        "journals_parsed": len(journals),
        **stats,
    }


@router.get("/abs/stats")
async def abs_stats():
    """Return current ABS database statistics."""
    db = get_abs_database()
    journals = db.get("journals", [])

    rating_dist = {}
    for j in journals:
        r = str(j.get("abs_rating", 0))
        rating_dist[r] = rating_dist.get(r, 0) + 1

    return {
        "total_journals": len(journals),
        "version": db.get("version", "unknown"),
        "updated_at": db.get("updated_at", "never"),
        "rating_distribution": rating_dist,
        "predatory_flagged": rating_dist.get("-1", 0),
    }


@router.post("/abs/flag")
async def flag_journal(body: dict):
    """
    Manually flag a journal as predatory (abs_rating = -1) or clear a flag.
    Body: {"journal_name": "...", "rating": -1, "reason": "..."}
    """
    name = (body.get("journal_name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="journal_name is required.")

    rating = body.get("rating", -1)
    reason = body.get("reason", "manually flagged")

    stats = add_journals(
        [{"journal_name": name, "abs_rating": rating, "field": None, "issn": None, "source": reason}],
        source_label="manual_flag",
    )
    return {"flagged": name, "rating": rating, **stats}
