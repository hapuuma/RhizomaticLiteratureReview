"""
Stages 1–2: Entry Layer
Identifies active entry points and dominant framework risk from the user query.
"""
import json
import httpx
from config import settings
from models import EntryLayerOutput
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


ENTRY_SYSTEM = load_prompt("master_system_prompt.txt")

ENTRY_USER_TEMPLATE = """
You are executing Stage 1 (Entry Layer) and Stage 2 (Entry Point Mapping) of the Rhizomatic Research Agent pipeline.

USER QUERY / PHENOMENON ZONE:
{query}

Your task:
1. Identify which of the five entry points into the phenomenon zone are active:
   - Material flows
   - Information governance
   - Organizing forms
   - Imaginaries
   - Assemblage moments

2. Detect which dominant frameworks are already present or implied in this query field:
   (e.g., Multilevel Perspective, diffusion theory, neoclassical economics, positivist science studies, mainstream management theory, innovation systems theory)

3. Assess whether these dominant frameworks pose a rupture risk (i.e., are they likely to overdetermine the analysis?).

4. Write a short present-continuous narrative of what entry points are opening up.

Output ONLY a raw JSON object with these exact keys:
{{
  "active_entry_points": ["..."],
  "dominant_frameworks_detected": ["..."],
  "rupture_risk": true | false,
  "narrative": "[Present continuous narrative of the entry movement]"
}}
"""


async def run_entry_layer(query: str) -> EntryLayerOutput:
    user_msg = ENTRY_USER_TEMPLATE.format(query=query)
    logger.info(f"[*] Calling Ollama (EntryLayer) with model {settings.ollama_model}")

    try:
        raw = await ollama_chat(
            messages=[
                {"role": "system", "content": ENTRY_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            label="EntryLayer",
        )
        record_tokens(raw)
    except httpx.HTTPStatusError as e:
        logger.error(f"[!] HTTP Error: {e}")
        if e.response.status_code == 404:
            raise Exception(
                f"Ollama endpoint not found (404). Check OLLAMA_BASE_URL ({settings.ollama_base_url}) and model."
            )
        raise
    except Exception as e:
        logger.error(f"[!] Request failed: {e}")
        raise

    content = raw["message"]["content"]
    try:
        data = clean_json(content)
        return EntryLayerOutput(**data)
    except Exception as exc:
        logger.error(f"Entry Layer failed to parse JSON: {exc}")
        logger.error(f"Raw content: {content}")
        raise exc
