"""
V4: Metadata Enricher
Fills missing fields (abstract, journal_name, authors) for papers that have a DOI,
using CrossRef (primary) and OpenAlex DOI lookup (fallback).
Runs between Deduplication and ABS Evaluation so the ABS screener has the best
possible data to work with.
"""
import re
import asyncio
import httpx
from models import RawSource
from pipeline import logger


async def _enrich_via_crossref(doi: str) -> dict:
    """Fetch paper metadata from CrossRef using DOI."""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "rhizomatic-agent/1.0 (mailto:rhizomatic-agent@research.dev)"},
            )
            if resp.status_code != 200:
                return {}
            data = resp.json().get("message", {})

            authors = []
            for author in data.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if family:
                    authors.append(f"{given} {family}".strip())

            journal = None
            container = data.get("container-title", [])
            if container:
                journal = container[0]

            abstract = data.get("abstract")
            if abstract:
                abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            return {"authors": authors or None, "journal_name": journal, "abstract": abstract}
    except Exception:
        return {}


async def _enrich_via_openalex_doi(doi: str) -> dict:
    """Fetch metadata from OpenAlex using a DOI filter."""
    url = f"https://api.openalex.org/works/doi:{doi}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url, params={"mailto": "rhizomatic-agent@research.dev"}
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()

            abstract = None
            aii = data.get("abstract_inverted_index")
            if aii:
                word_pos = [(w, p) for w, positions in aii.items() for p in positions]
                word_pos.sort(key=lambda x: x[1])
                abstract = " ".join(w for w, _ in word_pos)

            journal = None
            primary = data.get("primary_location") or {}
            source_info = primary.get("source") or {}
            journal = source_info.get("display_name")

            return {"abstract": abstract, "journal_name": journal}
    except Exception:
        return {}


async def _enrich_source(source: RawSource) -> RawSource:
    """Attempt to fill missing fields for a single source. Requires a DOI."""
    if not source.doi:
        return source

    needs = not source.abstract or not source.journal_name or not source.authors
    if not needs:
        return source

    # CrossRef first — best for authors + abstract
    cr = await _enrich_via_crossref(source.doi)

    abstract = source.abstract or cr.get("abstract")
    journal = source.journal_name or cr.get("journal_name")
    authors = source.authors or cr.get("authors") or []

    # Fallback to OpenAlex DOI lookup for still-missing fields
    if not abstract or not journal:
        oa = await _enrich_via_openalex_doi(source.doi)
        abstract = abstract or oa.get("abstract")
        journal = journal or oa.get("journal_name")

    if abstract == source.abstract and journal == source.journal_name and authors == source.authors:
        return source  # nothing changed

    return RawSource(
        title=source.title,
        authors=authors,
        year=source.year,
        abstract=abstract,
        doi=source.doi,
        url=source.url,
        source_api=source.source_api,
        journal_name=journal,
    )


async def run_metadata_enricher(sources: list[RawSource]) -> list[RawSource]:
    """
    Enrich all sources missing metadata in parallel (max 5 concurrent DOI calls).
    Sources without DOI or already complete are returned unchanged.
    """
    candidates = [
        s for s in sources
        if s.doi and (not s.abstract or not s.journal_name or not s.authors)
    ]

    if not candidates:
        logger.info("Metadata Enricher: all sources complete — skipping.")
        return sources

    logger.info(
        f"Metadata Enricher: enriching {len(candidates)}/{len(sources)} sources."
    )

    sem = asyncio.Semaphore(5)

    async def _bounded(s: RawSource) -> RawSource:
        async with sem:
            return await _enrich_source(s)

    enriched_map: dict[str, RawSource] = {}
    results = await asyncio.gather(*[_bounded(s) for s in candidates], return_exceptions=True)
    for orig, result in zip(candidates, results):
        enriched_map[orig.title] = result if isinstance(result, RawSource) else orig

    final = [enriched_map.get(s.title, s) for s in sources]

    changed = sum(
        1 for orig, new in zip(sources, final)
        if orig.abstract != new.abstract or orig.journal_name != new.journal_name
    )
    logger.info(f"Metadata Enricher: {changed} sources enriched.")
    return final
