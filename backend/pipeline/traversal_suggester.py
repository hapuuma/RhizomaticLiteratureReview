"""
V4: Traversal Suggester
Reads the completed traversal outputs and generates 3-5 "lines of flight" —
specific research queries the user can pursue next to deepen, rupture, or
extend the current cartography. Placed after the Assemblage Builder.
"""
from models import AssemblageOutput, ResonanceOutput, RuptureOutput, TraversalSuggestions
from config import settings
from pipeline import clean_json, logger, ollama_chat, record_tokens


_TRAVERSAL_SYSTEM = """You are the Cartographic Navigator for the Rhizomatic Research Agent.
You receive the outputs of a completed traversal — assemblage forces, convergent anomalies,
cross-module tensions, and rupture information.

Your task: generate 3-5 "lines of flight" — specific phenomenon-zone queries the researcher
could traverse next. Each must:
- Open a direction not already enclosed by the current traversal
- Follow a genuine deterritorializing force identified in the corpus
- Be specific enough to serve as a direct research query

trajectory values:
- "deepening": pursue an unresolved tension inside the same field
- "rupturing": enter from an epistemologically alien frame (outside-view)
- "extending": follow a connection to an adjacent phenomenon zone
- "transversal": cut across multiple fields simultaneously

OUTPUT FORMAT — Return ONLY valid JSON, no prose, no markdown:
{
  "suggested_traversals": [
    {
      "query": "The next phenomenon zone to traverse (usable as a search query)",
      "rationale": "1 sentence in present-continuous tense explaining why this line is opening",
      "trajectory": "deepening | rupturing | extending | transversal",
      "tension_source": "Which anomaly or tension is generating this opening"
    }
  ],
  "cartographic_note": "1-2 sentences in present-continuous tense: where the map as a whole is pointing"
}
"""


async def run_traversal_suggester(
    query: str,
    assemblage: AssemblageOutput,
    resonance: ResonanceOutput,
    rupture: RuptureOutput,
) -> TraversalSuggestions:
    """
    Generate suggested next traversal directions from current pipeline outputs.
    Falls back to an empty TraversalSuggestions on failure.
    """
    anomaly_lines = "\n".join(
        f"- {a.phenomenon} [{', '.join(a.fields_involved)}]"
        for a in resonance.convergent_anomalies
    )
    tension_lines = "\n".join(f"- {t}" for t in resonance.cross_module_tensions)
    deterr_lines = "\n".join(f"- {f}" for f in assemblage.deterritorializing_forces)
    rupture_info = (
        f"RUPTURE TRIGGERED — outside views: {', '.join(rupture.outside_view_entry_points)}"
        if rupture.triggered
        else "No rupture triggered."
    )

    user_prompt = f"""ORIGINAL QUERY: {query}

DETERRITORIALIZING FORCES:
{deterr_lines or '(none identified)'}

CONVERGENT ANOMALIES:
{anomaly_lines or '(none identified)'}

CROSS-MODULE TENSIONS:
{tension_lines or '(none identified)'}

RUPTURE STATUS: {rupture_info}

CARTOGRAPHIC DIRECTION (excerpt):
{assemblage.dominant_narrative[:600]}

Generate 3-5 suggested next traversal queries from these openings."""

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": _TRAVERSAL_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            label="TraversalSuggester",
        )
        record_tokens(raw)
        data = clean_json(raw["message"]["content"])
        return TraversalSuggestions(**data)

    except Exception as exc:
        logger.warning(f"Traversal Suggester failed ({exc}), returning empty suggestions.")
        return TraversalSuggestions()
