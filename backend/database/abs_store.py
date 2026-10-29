"""
V3: ABS Journal Store — Local Quality Database
Manages a local JSON database of journal quality ratings.
Users can upload ABS list files via /api/abs/upload to update the database.

JSON schema:
{
  "version": "2024",
  "updated_at": "ISO8601",
  "journals": [
    {
      "journal_name": "Journal of ...",
      "issn": "XXXX-XXXX",
      "abs_rating": 4,  // 1-4* = legitimate, 0 = unlisted, -1 = known predatory
      "field": "Management",
      "source": "ABS2024"
    }
  ]
}
"""
import json
import csv
import io
from pathlib import Path
from datetime import datetime
from config import settings
from pipeline import logger


def get_abs_database() -> dict:
    """Load the ABS database from disk. Returns empty structure if not found."""
    path = Path(settings.abs_database_path)
    if not path.exists():
        return {"version": "empty", "updated_at": "", "journals": []}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error(f"ABS database load error: {exc}")
        return {"version": "error", "updated_at": "", "journals": []}


def save_abs_database(data: dict) -> bool:
    """Persist the ABS database to disk."""
    path = Path(settings.abs_database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        logger.error(f"ABS database save error: {exc}")
        return False


def parse_abs_csv(content: str) -> list[dict]:
    """
    Parse an ABS list CSV file.
    Supports common column formats:
      - "Journal Title" / "Title" → journal_name
      - "ABS Rating" / "Rating" / "AJG Rating" → abs_rating
      - "ISSN" → issn
      - "Field" / "Subject Area" → field
    """
    journals = []
    reader = csv.DictReader(io.StringIO(content))

    # Normalize header names
    def _find_col(headers: list[str], candidates: list[str]) -> str | None:
        for c in candidates:
            for h in headers:
                if c.lower() in h.lower():
                    return h
        return None

    headers = reader.fieldnames or []
    title_col = _find_col(headers, ["journal title", "title", "journal name"])
    rating_col = _find_col(headers, ["abs rating", "ajg rating", "rating"])
    issn_col = _find_col(headers, ["issn"])
    field_col = _find_col(headers, ["field", "subject area", "category"])

    for row in reader:
        name = (row.get(title_col) or "").strip() if title_col else ""
        if not name:
            continue

        rating_raw = (row.get(rating_col) or "").strip() if rating_col else ""
        try:
            # Handle "4*" format
            rating_clean = rating_raw.replace("*", "").replace("†", "").strip()
            rating = int(float(rating_clean)) if rating_clean else 0
            if "4*" in rating_raw:
                rating = 5  # Use 5 to distinguish 4* from 4
        except ValueError:
            rating = 0

        journals.append({
            "journal_name": name,
            "issn": (row.get(issn_col) or "").strip() if issn_col else None,
            "abs_rating": rating,
            "field": (row.get(field_col) or "").strip() if field_col else None,
            "source": "uploaded",
        })

    return journals


def add_journals(new_journals: list[dict], source_label: str = "uploaded") -> dict:
    """
    Merge new journals into the ABS database.
    Returns summary stats.
    """
    db = get_abs_database()
    existing = {j["journal_name"].lower(): j for j in db.get("journals", [])}

    added = updated = 0
    for journal in new_journals:
        key = journal["journal_name"].lower()
        journal["source"] = source_label
        if key in existing:
            existing[key].update(journal)
            updated += 1
        else:
            existing[key] = journal
            added += 1

    db["journals"] = list(existing.values())
    db["updated_at"] = datetime.utcnow().isoformat()
    save_abs_database(db)

    return {"added": added, "updated": updated, "total": len(db["journals"])}
