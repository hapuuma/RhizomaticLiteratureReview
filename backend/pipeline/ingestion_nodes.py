"""
Stage 3: Parallel Potentiality Modules (Ingestion Nodes)
Each module/lens processes the same raw literature batch through a different perspective.
All lenses run concurrently via asyncio.gather.

V3: Accepts dynamic_modules dict from Epistemology Agent.
    Falls back to static MODULES from config if not provided.
"""
import json
import asyncio
from config import settings, MODULES
from models import IngestionOutput
from pipeline import load_prompt, clean_json, logger, ollama_chat, record_tokens


INGESTION_TEMPLATE = load_prompt("ingestion_template.txt")
MASTER_SYSTEM = load_prompt("master_system_prompt.txt")


def _build_raw_payload(sources: list) -> str:
    """Convert list of RawSource-like dicts into a compact JSON string."""
    return json.dumps(sources, ensure_ascii=False, indent=2)


async def _run_single_module(
    module_key: str,
    sources: list,
    active_modules: dict | None = None,
) -> IngestionOutput:
    module = (active_modules or MODULES)[module_key]
    raw_payload = _build_raw_payload(sources)

    prompt = (
        INGESTION_TEMPLATE
        .replace("{{MODULE_NAME}}", module["name"])
        .replace("{{MODULE_TARGET}}", module["target"])
        .replace("{{RAW_PAYLOAD}}", raw_payload)
    )

    raw = await ollama_chat(
        messages=[
            {"role": "system", "content": MASTER_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        label=f"Ingestion:{module_key}",
    )
    record_tokens(raw)

    content = raw["message"]["content"]
    try:
        data = clean_json(content)
        return IngestionOutput(**data)
    except Exception as exc:
        logger.error(f"Module {module_key} failed to parse JSON: {exc}")
        logger.error(f"Raw content: {content}")
        raise exc


async def run_ingestion_nodes(
    sources: list,
    dynamic_modules: dict | None = None,
) -> dict[str, IngestionOutput]:
    """
    Fire all lens modules in parallel.
    Falls back to sequential if parallel fails (Ollama overload).

    Args:
        sources: List of RawSource dicts to process.
        dynamic_modules: V3 — dict from Epistemology Agent (lens name → {name, target}).
                         If None, falls back to static MODULES from config.

    Returns a dict keyed by module/lens name → IngestionOutput.
    """
    active_modules = dynamic_modules if dynamic_modules is not None else MODULES

    module_factories = [
        lambda k=key: _run_single_module(k, sources, active_modules)
        for key in active_modules
    ]

    # 1. Try parallel
    try:
        tasks = [f() for f in module_factories]
        results = await asyncio.gather(*tasks)
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "503" in err_msg or "too many requests" in err_msg:
            logger.warning("Ingestion Modules parallel call failed. Falling back to sequential...")
            results = []
            for f_func in module_factories:
                results.append(await f_func())
        else:
            raise

    return dict(zip(active_modules.keys(), results))
