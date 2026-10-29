"""
V3: ABS Evaluator Agent — Data Integrity (Immune System)
Quarantines predatory papers by:
1. Cross-referencing a local ABS journal quality database (JSON)
2. Running an LLM signal check on paper metadata if needed

Papers are flagged but never deleted — the pipeline passes through all verdicts
so the user can see what was filtered.
"""
import json
from pathlib import Path
from config import settings
from models import ABSCheckResult, ABSPaperVerdict, RawSource
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


ABS_PROMPT = load_prompt("abs_evaluator.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")

# ─── Local ABS Database ───────────────────────────────────────────────────────

def _load_abs_db() -> dict:
    """Load the local ABS journal database. Returns {} if not found."""
    path = Path(settings.abs_database_path)
    if not path.exists():
        logger.info("ABS database not found at configured path — LLM-only screening active.")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {entry["journal_name"].lower(): entry for entry in data.get("journals", [])}
    except Exception as exc:
        logger.warning(f"ABS database load failed: {exc}")
        return {}


def _check_against_local_db(source: RawSource, abs_db: dict) -> str | None:
    """
    Returns 'quarantine' if journal is known predatory, 'pass' if known good,
    None if unknown (LLM check needed).
    """
    if not source.journal_name:
        return None
    key = source.journal_name.lower()
    entry = abs_db.get(key)
    if not entry:
        return None
    rating = entry.get("abs_rating", 0)
    if rating == -1:
        return "quarantine"
    if rating >= 1:
        return "pass"
    return None


# ─── LLM Screening ───────────────────────────────────────────────────────────

async def _llm_screen_batch(sources: list[RawSource]) -> ABSCheckResult:
    """Run the LLM ABS evaluator on a batch of papers."""
    batch_payload = json.dumps(
        [
            {
                "title": s.title,
                "journal": s.journal_name or "Unknown",
                "year": s.year,
                "abstract_snippet": (s.abstract or "")[:400],
                "doi": s.doi or "missing",
                "source_api": s.source_api or "unknown",
            }
            for s in sources
        ],
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"Evaluate the following papers for academic quality and predatory signals:\n\n{batch_payload}"

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": ABS_PROMPT},
                {"role": "user", "content": prompt},
            ],
            label="ABSEvaluator",
        )
        record_tokens(raw)
        content = raw["message"]["content"]
        data = clean_json(content)
        result = ABSCheckResult(**data)
        return result
    except Exception as exc:
        logger.warning(f"ABS LLM screen failed ({exc}), passing all papers.")
        verdicts = [
            ABSPaperVerdict(
                title=s.title,
                verdict="pass",
                confidence=0.5,
                signals_detected=[],
                rationale="ABS LLM screening unavailable — default pass.",
            )
            for s in sources
        ]
        return ABSCheckResult(papers=verdicts, quarantine_count=0, pass_count=len(sources))


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def run_abs_evaluator(sources: list[RawSource]) -> tuple[list[RawSource], ABSCheckResult]:
    """
    Run the full ABS evaluation pipeline.
    Returns (approved_sources, full_check_result).
    Quarantined papers are excluded from approved_sources but preserved in check_result.
    """
    abs_db = _load_abs_db()

    # 1. Quick local DB check
    db_verdicts: dict[str, str] = {}
    needs_llm: list[RawSource] = []

    for source in sources:
        local = _check_against_local_db(source, abs_db)
        if local is not None:
            db_verdicts[source.title] = local
        else:
            needs_llm.append(source)

    # 2. LLM check for unknowns (batch)
    llm_result = ABSCheckResult(papers=[], quarantine_count=0, pass_count=0)
    if needs_llm:
        llm_result = await _llm_screen_batch(needs_llm)

    # 3. Merge results
    all_papers: list[ABSPaperVerdict] = []
    for source in sources:
        db_v = db_verdicts.get(source.title)
        if db_v is not None:
            all_papers.append(
                ABSPaperVerdict(
                    title=source.title,
                    verdict=db_v,
                    confidence=0.95,
                    signals_detected=["local_abs_db"],
                    rationale="Matched in local ABS journal database.",
                )
            )
        else:
            # Find in LLM result
            llm_verdict = next(
                (p for p in llm_result.papers if p.title == source.title), None
            )
            if llm_verdict:
                all_papers.append(llm_verdict)
            else:
                all_papers.append(
                    ABSPaperVerdict(
                        title=source.title,
                        verdict="pass",
                        confidence=0.4,
                        signals_detected=[],
                        rationale="No screening result found — default pass.",
                    )
                )

    quarantine_count = sum(1 for p in all_papers if p.verdict == "quarantine")
    pass_count = sum(1 for p in all_papers if p.verdict != "quarantine")
    full_result = ABSCheckResult(
        papers=all_papers,
        quarantine_count=quarantine_count,
        pass_count=pass_count,
    )

    # 4. Filter to approved sources only
    quarantined_titles = {p.title for p in all_papers if p.verdict == "quarantine"}
    approved = [s for s in sources if s.title not in quarantined_titles]

    logger.info(
        f"ABS Evaluator: {len(sources)} in → {quarantine_count} quarantined → "
        f"{len(approved)} approved"
    )
    return approved, full_result
