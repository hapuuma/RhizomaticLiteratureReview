"""
V3: Deduplication Agent — Data Integrity (Immune System)
Blocks duplicate papers using two-tier strategy:
  1. DOI normalization (exact match)
  2. Trigram title similarity (fuzzy match for same paper from different APIs)
No LLM call required — purely deterministic.
"""
import re
from models import RawSource, DeduplicationResult
from pipeline import logger


def _normalize_doi(doi: str | None) -> str | None:
    """Normalize DOI to lowercase, strip URL prefixes."""
    if not doi:
        return None
    doi = doi.lower().strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)
    doi = doi.strip('/')
    return doi if doi else None


def _trigrams(text: str) -> set[str]:
    """Generate character trigrams from a string."""
    text = re.sub(r'[^a-z0-9 ]', '', text.lower())
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) < 3:
        return set()
    return {text[i:i+3] for i in range(len(text) - 2)}


def _trigram_similarity(title_a: str, title_b: str) -> float:
    """Dice coefficient on trigrams."""
    tg_a = _trigrams(title_a)
    tg_b = _trigrams(title_b)
    if not tg_a or not tg_b:
        return 0.0
    intersection = tg_a & tg_b
    return 2 * len(intersection) / (len(tg_a) + len(tg_b))


SIMILARITY_THRESHOLD = 0.85  # Papers above this are considered duplicates


def run_deduplication(sources: list[RawSource]) -> DeduplicationResult:
    """
    Deduplicate a list of RawSource objects.
    Strategy:
      1. DOI normalization exact match
      2. Trigram title similarity fallback
    Returns DeduplicationResult with unique sources and removed count.
    """
    seen_dois: dict[str, str] = {}       # normalized_doi → kept title
    kept: list[RawSource] = []
    duplicates_removed = 0
    duplicate_pairs: list[dict[str, str]] = []

    for source in sources:
        norm_doi = _normalize_doi(source.doi)

        # ── Tier 1: DOI exact match ─────────────────────────────────────────
        if norm_doi:
            if norm_doi in seen_dois:
                duplicates_removed += 1
                duplicate_pairs.append({"kept": seen_dois[norm_doi], "removed": source.title})
                logger.debug(f"Dedup DOI: '{source.title}' duplicates '{seen_dois[norm_doi]}'")
                continue
            seen_dois[norm_doi] = source.title

        # ── Tier 2: Trigram title similarity ───────────────────────────────
        is_duplicate = False
        for existing in kept:
            sim = _trigram_similarity(source.title, existing.title)
            if sim >= SIMILARITY_THRESHOLD:
                duplicates_removed += 1
                duplicate_pairs.append({"kept": existing.title, "removed": source.title})
                logger.debug(
                    f"Dedup trigram ({sim:.2f}): '{source.title}' ≈ '{existing.title}'"
                )
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(source)

    logger.info(
        f"Deduplication: {len(sources)} in → {duplicates_removed} removed → "
        f"{len(kept)} unique"
    )

    return DeduplicationResult(
        unique_sources=kept,
        duplicates_removed=duplicates_removed,
        duplicate_pairs=duplicate_pairs,
    )
