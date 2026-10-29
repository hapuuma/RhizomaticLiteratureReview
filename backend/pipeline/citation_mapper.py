"""
V3: Citation Mapper Agent — Core Pipeline (The Muscle)
Extracts cited works from paper abstracts to:
1. Find anchor papers (structurally central citations)
2. Map the historical intellectual network
3. Identify citation shadows (implicit foundational influences)

Uses LLM to parse abstract text for citation signals.
"""
import json
from models import CitationMapOutput, RawSource
from config import settings
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


CITATION_PROMPT = load_prompt("citation_analyzer.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")


async def run_citation_mapper(sources: list[RawSource]) -> CitationMapOutput:
    """
    Run the Citation Mapper on a batch of literature sources.
    Returns CitationMapOutput with anchor papers, citation shadows, and lineage.
    """
    if not sources:
        return _empty_output()

    # Build compact payload (title + abstract snippet only — save tokens)
    payload = json.dumps(
        [
            {
                "title": s.title,
                "authors": ", ".join(s.authors[:3]) if s.authors else "Unknown",
                "year": s.year,
                "abstract": (s.abstract or "")[:600],
            }
            for s in sources
        ],
        ensure_ascii=False,
        indent=2,
    )

    user_prompt = (
        f"Analyze the following {len(sources)} papers and extract "
        "citation structures, anchor papers, and intellectual lineages:\n\n"
        f"{payload}"
    )

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": CITATION_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            label="CitationMapper",
        )
        record_tokens(raw)
        content = raw["message"]["content"]
        data = clean_json(content)

        result = CitationMapOutput(**data)

        result.anchor_papers = [
            c.cited_work for c in result.explicit_citations if c.is_anchor
        ]

        logger.info(
            f"Citation Mapper: {len(result.explicit_citations)} citations found, "
            f"{len(result.anchor_papers)} anchors, "
            f"{len(result.citation_shadows)} shadows"
        )
        return result

    except Exception as exc:
        logger.warning(f"Citation Mapper failed ({exc}), returning empty map.")
        return _empty_output()


def _empty_output() -> CitationMapOutput:
    return CitationMapOutput(
        explicit_citations=[],
        citation_shadows=[],
        historical_lineage_note="Citation mapping unavailable for this batch.",
        anchor_papers=[],
    )
