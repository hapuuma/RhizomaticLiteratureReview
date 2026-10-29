"""
/api/lenses — Lens generation endpoints.

GET  /api/lenses/defaults — return static default lenses (no LLM call)
POST /api/lenses          — run Phase 1 (Epistemology Agent) for a query
"""
from fastapi import APIRouter
from models import QueryRequest
from pipeline.epistemology_agent import run_epistemology_agent, _static_fallback

router = APIRouter()


@router.get("/lenses/defaults")
async def get_default_lenses():
    """Return the static fallback lenses — no LLM call, always fast."""
    epistemology = _static_fallback()
    return {
        "lenses": [l.model_dump() for l in epistemology.lenses],
        "dominant_paradigm_risk": epistemology.dominant_paradigm_risk,
        "epistemological_rationale": epistemology.epistemological_rationale,
        "fallback_executed": True,
    }


@router.post("/lenses")
async def generate_lenses(request: QueryRequest):
    """Run the Epistemology Agent for the given query and return AI-proposed lenses."""
    epistemology, fallback_executed = await run_epistemology_agent(request.query)
    return {
        "lenses": [l.model_dump() for l in epistemology.lenses],
        "dominant_paradigm_risk": epistemology.dominant_paradigm_risk,
        "epistemological_rationale": epistemology.epistemological_rationale,
        "fallback_executed": fallback_executed,
    }
