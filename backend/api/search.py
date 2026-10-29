"""
Literature Search — Multi-Source (V3)
Sources: OpenAlex (primary) + arXiv (secondary)
Features:
  - Query expansion: adds epistemological trigger terms when rupture_mode=True
  - Deduplication-ready: sets source_api field on each RawSource
  - arXiv: parses Atom feed XML (no auth required)
"""
import re
import httpx
from xml.etree import ElementTree as ET
from config import settings
from models import RawSource


# ─── Shared Helpers ───────────────────────────────────────────────────────────

def _expand_query(query: str, rupture_mode: bool = False) -> list[str]:
    """
    V3: Generate expanded query variants.
    rupture_mode=True adds epistemological trigger terms per Rupture Protocol.
    """
    queries = [query]
    if rupture_mode:
        trigger_terms = [
            "pluriverse", "heterodox", "decolonial", "commons",
            "degrowth", "post-colonial", "indigenous ontology",
        ]
        for term in trigger_terms[:3]:
            queries.append(f"{query} {term}")
    return queries


# ─── OpenAlex ────────────────────────────────────────────────────────────────

def _parse_author(authorship: dict) -> str:
    author = authorship.get("author", {})
    return author.get("display_name", "Unknown")


def _parse_abstract(abstract_inverted_index: dict | None) -> str | None:
    """Reconstruct abstract from OpenAlex's inverted index format."""
    if not abstract_inverted_index:
        return None
    word_positions: list[tuple[str, int]] = []
    for word, positions in abstract_inverted_index.items():
        for pos in positions:
            word_positions.append((word, pos))
    word_positions.sort(key=lambda x: x[1])
    return " ".join(w for w, _ in word_positions)


async def _fetch_openalex(query: str, max_results: int) -> list[RawSource]:
    """Fetch papers from OpenAlex API."""
    params = {
        "search": query,
        "per-page": max_results,
        "select": "title,authorships,publication_year,abstract_inverted_index,doi,primary_location",
        "mailto": settings.openalex_email,
        "filter": "has_abstract:true",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(settings.openalex_api_url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = data.get("results", [])
    sources = []

    for item in results:
        title = item.get("title") or "Untitled"
        authors = [_parse_author(a) for a in (item.get("authorships") or [])]
        year = item.get("publication_year")
        abstract = _parse_abstract(item.get("abstract_inverted_index"))
        doi = item.get("doi")

        primary = item.get("primary_location") or {}
        source_info = primary.get("source") or {}
        url = primary.get("landing_page_url") or doi
        journal_name = source_info.get("display_name")

        sources.append(
            RawSource(
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                doi=doi,
                url=url,
                source_api="openalex",
                journal_name=journal_name,
            )
        )

    return sources


# ─── Semantic Scholar ────────────────────────────────────────────────────────

async def _fetch_semantic_scholar(query: str, max_results: int) -> list[RawSource]:
    """Fetch papers from Semantic Scholar Graph API (no auth required for basic use)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": min(max_results, 20),
        "fields": "title,authors,year,abstract,externalIds,publicationVenue",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    sources = []
    for item in data.get("data", []):
        title = item.get("title") or "Untitled"
        authors = [a.get("name", "Unknown") for a in (item.get("authors") or [])]
        year = item.get("year")
        abstract = item.get("abstract")

        external_ids = item.get("externalIds") or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")
        url_out = f"https://doi.org/{doi}" if doi else (
            f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None
        )

        venue = item.get("publicationVenue") or {}
        journal_name = venue.get("name")

        sources.append(
            RawSource(
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                doi=doi,
                url=url_out,
                source_api="semantic_scholar",
                journal_name=journal_name,
            )
        )

    return sources


# ─── arXiv ───────────────────────────────────────────────────────────────────

_ARXIV_NS = "http://www.w3.org/2005/Atom"


def _text(element, tag: str, ns: str = _ARXIV_NS) -> str | None:
    el = element.find(f"{{{ns}}}{tag}")
    return el.text.strip() if el is not None and el.text else None


async def _fetch_arxiv(query: str, max_results: int) -> list[RawSource]:
    """Fetch papers from arXiv Atom API."""
    # arXiv search: replace spaces with + for URL
    search_query = f"all:{query.replace(' ', '+')}"
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(settings.arxiv_api_url, params=params)
            resp.raise_for_status()
            xml_text = resp.text
    except Exception:
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    sources = []
    for entry in root.findall(f"{{{_ARXIV_NS}}}entry"):
        title = _text(entry, "title") or "Untitled"
        title = re.sub(r'\s+', ' ', title)  # arXiv titles can have newlines

        abstract = _text(entry, "summary") or None
        year = None
        published = _text(entry, "published")
        if published and len(published) >= 4:
            try:
                year = int(published[:4])
            except ValueError:
                pass

        # Authors
        authors = []
        for author_el in entry.findall(f"{{{_ARXIV_NS}}}author"):
            name = _text(author_el, "name")
            if name:
                authors.append(name)

        # DOI and URL
        doi = None
        url = None
        for link in entry.findall(f"{{{_ARXIV_NS}}}link"):
            rel = link.get("rel", "")
            href = link.get("href", "")
            if rel == "alternate" or link.get("type") == "text/html":
                url = href
            doi_el = entry.find(f"{{{_ARXIV_NS}}}doi")
            if doi_el is not None and doi_el.text:
                doi = doi_el.text.strip()

        if not url:
            arxiv_id = _text(entry, "id")
            if arxiv_id:
                url = arxiv_id

        sources.append(
            RawSource(
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                doi=doi,
                url=url,
                source_api="arxiv",
                journal_name="arXiv preprint",
            )
        )

    return sources


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def fetch_literature(
    query: str,
    max_results: int = None,
    rupture_mode: bool = False,
) -> list[RawSource]:
    """
    Search multiple sources for papers matching the query.
    V3: Adds arXiv as secondary source. Supports rupture_mode query expansion.
    Returns a combined list of RawSource objects (deduplication happens downstream).
    """
    if max_results is None:
        max_results = settings.openalex_results_per_page

    # V4: run all three sources in parallel
    import asyncio
    openalex_task = _fetch_openalex(query, max_results)
    arxiv_task = _fetch_arxiv(query, settings.arxiv_results_per_source)
    semantic_scholar_task = _fetch_semantic_scholar(query, max_results // 2 or 8)

    openalex_results, arxiv_results, ss_results = await asyncio.gather(
        openalex_task, arxiv_task, semantic_scholar_task, return_exceptions=True
    )

    combined: list[RawSource] = []
    if isinstance(openalex_results, list):
        combined.extend(openalex_results)
    if isinstance(arxiv_results, list):
        combined.extend(arxiv_results)
    if isinstance(ss_results, list):
        combined.extend(ss_results)

    # V3: rupture mode — fetch additional sources with expanded queries
    if rupture_mode:
        expanded_queries = _expand_query(query, rupture_mode=True)[1:]  # skip original
        for eq in expanded_queries[:2]:  # limit to 2 expansions
            try:
                extra = await _fetch_openalex(eq, max_results=5)
                combined.extend(extra)
            except Exception:
                pass

    return combined
