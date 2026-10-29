"""
Stage 4: Resonance Detector
Finds convergent anomalies across the three module outputs.
"""
import json
from config import settings
from models import IngestionOutput, ResonanceOutput
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


RESONANCE_PROMPT = load_prompt("resonance_detector.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")


def _serialize_modules(modules: dict[str, IngestionOutput]) -> str:
    return json.dumps(
        {k: v.model_dump() for k, v in modules.items()},
        ensure_ascii=False,
        indent=2,
    )


async def run_resonance_detector(
    modules: dict[str, IngestionOutput],
) -> ResonanceOutput:
    module_json = _serialize_modules(modules)
    prompt = RESONANCE_PROMPT.replace("{{MODULE_OUTPUTS}}", module_json)

    raw = await ollama_chat(
        messages=[
            {"role": "system", "content": MASTER_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        label="ResonanceDetector",
    )
    record_tokens(raw)

    content = raw["message"]["content"]
    try:
        data = clean_json(content)
        return ResonanceOutput(**data)
    except Exception as exc:
        logger.error(f"Resonance Detector failed to parse JSON: {exc}")
        logger.error(f"Raw content: {content}")
        raise exc
