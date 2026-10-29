"""
Stage 8: Relationship Mapping (Graph)
Maps all pipeline findings into a nodes-and-edges topology.
"""
import json
from config import settings
from models import (
    EntryLayerOutput, IngestionOutput, ResonanceOutput,
    RuptureOutput, AssemblageOutput, RelationshipGraph
)
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens

MAPPER_PROMPT = load_prompt("relationship_mapper.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")

async def run_relationship_mapper(
    entry: EntryLayerOutput,
    modules: dict[str, IngestionOutput],
    resonance: ResonanceOutput,
    rupture: RuptureOutput
) -> RelationshipGraph:
    # Prepare comprehensive pipeline data for the mapper (no assemblage needed)
    p_data = {
        "entry": entry.model_dump(),
        "modules": {k: v.model_dump() for k, v in modules.items()},
        "resonance": resonance.model_dump(),
        "rupture": rupture.model_dump()
    }
    
    prompt = MAPPER_PROMPT.replace("{{PIPELINE_DATA}}", json.dumps(p_data, ensure_ascii=False, indent=2))
    logger.info(f"[*] Calling Ollama (Graph) with model {settings.ollama_model}")

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": MASTER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            label="RelationshipMapper",
        )
        record_tokens(raw)
    except Exception as e:
        logger.error(f"[!] Graph request failed: {e}")
        raise

    content = raw["message"]["content"]
    try:
        data = clean_json(content)
        return RelationshipGraph(**data)
    except Exception as exc:
        logger.error(f"Relationship Mapper failed to parse JSON: {exc}")
        logger.error(f"Raw content: {content}")
        raise exc
