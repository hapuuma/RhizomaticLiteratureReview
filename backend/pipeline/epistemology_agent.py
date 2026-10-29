"""
V3: Epistemology Agent — Phase 1: Dynamic Ontological Setup
Generates 3–5 custom orthogonal theoretical lenses tailored to the specific
project topic. These lenses replace (or augment) the static MODULES config
for the duration of a pipeline run.
"""
from config import settings, MODULES
from models import EpistemologyOutput, LensDefinition, IngestionOutput
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


EPISTEMOLOGY_PROMPT = load_prompt("epistemology_agent.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")


async def run_epistemology_agent(query: str) -> tuple[EpistemologyOutput, bool]:
    """
    Calls the LLM to generate dynamic theoretical lenses for this query.
    Falls back to static MODULES if LLM call fails.
    Returns (EpistemologyOutput, fallback_executed).
    """
    user_prompt = (
        f"Research Query (Phenomenon Zone): {query}\n\n"
        f"Number of lenses to generate: {settings.num_dynamic_lenses}\n\n"
        "Generate orthogonal theoretical lenses for this corpus."
    )

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": EPISTEMOLOGY_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            label="EpistemologyAgent",
        )
        record_tokens(raw)
        content = raw["message"]["content"]
        data = clean_json(content)
        return EpistemologyOutput(**data), False

    except Exception as exc:
        logger.warning(f"Epistemology Agent failed ({exc}), falling back to static MODULES.")
        return _static_fallback(), True


def _static_fallback() -> EpistemologyOutput:
    """Convert static MODULES config into EpistemologyOutput format."""
    lenses = [
        LensDefinition(
            name=m["name"],
            tradition="Process-Relational Ontology",
            core_question=f"How does this paper illuminate {m['name'].lower()} dynamics?",
            signal_vocabulary=[],
            axiom_it_dismantles=None,
            is_rupture_lens=False,
        )
        for m in MODULES.values()
    ]
    return EpistemologyOutput(
        lenses=lenses,
        dominant_paradigm_risk="Unknown — static fallback in use",
        epistemological_rationale="Static module configuration is being applied as fallback lenses.",
    )


def lenses_to_modules(epistemology: EpistemologyOutput) -> dict:
    """
    Convert EpistemologyOutput lenses into the MODULES dict format
    expected by run_ingestion_nodes.
    """
    return {
        lens.name: {
            "name": lens.name,
            "target": (
                f"{lens.core_question} "
                f"Theoretical tradition: {lens.tradition}. "
                f"Signal vocabulary to look for: {', '.join(lens.signal_vocabulary)}. "
                + (
                    f"This lens specifically dismantles the assumption that: {lens.axiom_it_dismantles}."
                    if lens.axiom_it_dismantles
                    else ""
                )
            ),
        }
        for lens in epistemology.lenses
    }
