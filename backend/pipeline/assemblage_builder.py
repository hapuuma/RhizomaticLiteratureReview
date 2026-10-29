"""
Stage 6: Assemblage Builder
Synthesizes entry layer, module outputs, resonance, and rupture
into a narrative of provisional assemblages (present continuous throughout).
"""
import json
from config import settings
from models import (
    EntryLayerOutput, IngestionOutput,
    ResonanceOutput, RuptureOutput, AssemblageOutput,
)
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


ASSEMBLAGE_PROMPT = load_prompt("assemblage_builder.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")


async def run_assemblage_builder(
    entry: EntryLayerOutput,
    modules: dict[str, IngestionOutput],
    resonance: ResonanceOutput,
    rupture: RuptureOutput,
) -> AssemblageOutput:
    # Build rupture status block
    if rupture.triggered:
        rupture_status = (
            f"RUPTURE TRIGGERED. Dominant frameworks being ruptured: "
            f"{', '.join(rupture.dominant_frameworks_ruptured)}. "
            f"Re-enter from: {', '.join(rupture.outside_view_entry_points)}."
        )
    else:
        rupture_status = "NO RUPTURE. Proceed from the entry points and module findings directly."

    prompt = (
        ASSEMBLAGE_PROMPT
        .replace("{{RUPTURE_STATUS}}", rupture_status)
        .replace("{{ENTRY_OUTPUT}}", json.dumps(entry.model_dump(), ensure_ascii=False, indent=2))
        .replace(
            "{{MODULE_OUTPUTS}}",
            json.dumps({k: v.model_dump() for k, v in modules.items()}, ensure_ascii=False, indent=2),
        )
        .replace("{{RESONANCE_OUTPUT}}", json.dumps(resonance.model_dump(), ensure_ascii=False, indent=2))
    )

    logger.info(f"[*] Calling Ollama (Assemblage) with model {settings.ollama_model}")

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": MASTER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            label="AssemblageBuilder",
        )
        record_tokens(raw)
    except Exception as e:
        logger.error(f"[!] Assemblage request failed: {e}")
        raise

    content = raw["message"]["content"]
    try:
        data = clean_json(content)
        return AssemblageOutput(**data)
    except Exception as exc:
        logger.error(f"Assemblage Builder failed to parse JSON: {exc}")
        logger.error(f"Raw content: {content}")
        raise exc
