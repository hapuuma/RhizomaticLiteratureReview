"""
SSE Traverse Endpoint — V4 Rhizomatic Pipeline
POST /api/traverse — streams one JSON event per pipeline stage.

V4 Pipeline Phases:
  Phase 1: Dynamic Ontological Setup (Epistemology Agent) — skipped if custom_lenses provided
  Phase 2a: Literature Search (OpenAlex + arXiv + Semantic Scholar) + Entry Layer (parallel)
  Phase 2b: Deduplication
  Phase 2c: Metadata Enrichment (CrossRef + OpenAlex DOI)
  Phase 2d: ABS Evaluation + Citation Mapping (parallel)
  Phase 3: Parallel Ingestion through dynamic lenses
  Phase 4a: Resonance Detection
  Phase 4b: Rupture Protocol (+ optional rupture-mode search)
  Phase 5a: Assemblage + Relationship Mapping (parallel)
  Phase 5b: Rhizome Builder (edge classification + centralization detection + optional Neo4j)
  Phase 5c: Traversal Suggester
  Phase 6: Cartographic Output
  Phase 7: Semantic Topography (BERT — computes lens cosine matrix here too)
  Phase 8: Run Report saved to output/runs/<run_id>/

Each event: {"stage": "...", "status": "running"|"complete"|"error", "data": {...}}
"""
import json
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models import QueryRequest, EpistemologyOutput, LensDefinition, RunRecord
from api.search import fetch_literature
from pipeline.entry_layer import run_entry_layer
from pipeline.ingestion_nodes import run_ingestion_nodes
from pipeline.resonance_detector import run_resonance_detector
from pipeline.rupture_protocol import run_rupture_protocol
from pipeline.assemblage_builder import run_assemblage_builder
from pipeline.relationship_mapper import run_relationship_mapper
from pipeline.cartographic_output import build_cartographic_output
from pipeline.epistemology_agent import run_epistemology_agent, lenses_to_modules
from pipeline.abs_evaluator import run_abs_evaluator
from pipeline.deduplication_agent import run_deduplication
from pipeline.metadata_enricher import run_metadata_enricher
from pipeline.citation_mapper import run_citation_mapper
from pipeline.rhizome_builder import run_rhizome_builder
from pipeline.traversal_suggester import run_traversal_suggester
from pipeline.semantic_topography import run_semantic_topography
from pipeline.run_reporter import build_and_save_run_report
from pipeline import logger, reset_token_tracking, get_token_totals
from api.runs import save_run
from config import settings


router = APIRouter()


def _event(stage: str, status: str, data: dict = None, error: str = None) -> str:
    payload = {"stage": stage, "status": status}
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _run_tasks_with_fallback(tasks_funcs: list):
    """Execute tasks in parallel; fall back to sequential on Ollama overload."""
    try:
        tasks = [f() for f in tasks_funcs]
        return await asyncio.gather(*tasks)
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "503" in err_msg or "too many requests" in err_msg:
            logger.warning("Ollama overloaded. Switching to sequential processing.")
            results = []
            for f_func in tasks_funcs:
                results.append(await f_func())
            return results
        raise e


def _lenses_from_custom(custom_lenses: list[dict]) -> EpistemologyOutput:
    """Reconstruct EpistemologyOutput from user-edited lens dicts."""
    lenses = []
    for ld in custom_lenses:
        lenses.append(LensDefinition(
            name=ld.get("name", "Unnamed Lens"),
            tradition=ld.get("tradition", ""),
            core_question=ld.get("core_question", ""),
            signal_vocabulary=ld.get("signal_vocabulary", []),
            axiom_it_dismantles=ld.get("axiom_it_dismantles"),
            is_rupture_lens=ld.get("is_rupture_lens", False),
        ))
    return EpistemologyOutput(
        lenses=lenses,
        dominant_paradigm_risk=custom_lenses[0].get("dominant_paradigm_risk", "") if custom_lenses else "",
        epistemological_rationale="User-defined lenses applied (Phase 1 skipped).",
    )


async def _pipeline_generator(
    query: str,
    max_sources: int,
    use_dynamic_lenses: bool,
    project_id: str | None,
    custom_lenses: list[dict] | None,
    run_mode: str,
    domain: str,
    corpus_profile: str,
):
    run_id = str(uuid.uuid4())[:12]
    run_start = datetime.now(timezone.utc).isoformat()
    reset_token_tracking()
    start_time = datetime.now(timezone.utc)
    phases_completed = 0
    errors: list[str] = []
    rupture_sources_added = 0
    fallback_executed = False
    epistemology = None
    graph = None
    persist_result = None
    rupture = None
    gap_analysis = None
    lens_cosine_matrix = None

    try:
        # ── Phase 1: Dynamic Ontological Setup ───────────────────────────────
        yield _event("epistemology", "running")

        if custom_lenses:
            epistemology = _lenses_from_custom(custom_lenses)
            fallback_executed = False
        else:
            epistemology, fallback_executed = await run_epistemology_agent(query)

        dynamic_modules = lenses_to_modules(epistemology) if use_dynamic_lenses else None
        phases_completed += 1

        yield _event("epistemology", "complete", {
            "lenses": [l.model_dump() for l in epistemology.lenses],
            "dominant_paradigm_risk": epistemology.dominant_paradigm_risk,
            "epistemological_rationale": epistemology.epistemological_rationale,
        })

        # ── Phase 2a: Search + Entry Layer (Parallel) ─────────────────────────
        yield _event("search", "running")
        yield _event("entry", "running")

        rupture_search = bool(epistemology.dominant_paradigm_risk)
        search_f = lambda: fetch_literature(query, max_sources, rupture_mode=rupture_search)
        entry_f  = lambda: run_entry_layer(query)

        sources_raw, entry = await _run_tasks_with_fallback([search_f, entry_f])
        phases_completed += 1

        yield _event("entry", "complete", entry.model_dump())

        # ── Phase 2b: Deduplication ───────────────────────────────────────────
        dedup_result   = run_deduplication(sources_raw)
        sources_deduped = dedup_result.unique_sources

        yield _event("search", "complete", {
            "source_count":   len(sources_raw),
            "after_dedup":    len(sources_deduped),
            "duplicates_removed": dedup_result.duplicates_removed,
            "sources_by_api": {
                "openalex":         sum(1 for s in sources_raw if s.source_api == "openalex"),
                "arxiv":            sum(1 for s in sources_raw if s.source_api == "arxiv"),
                "semantic_scholar": sum(1 for s in sources_raw if s.source_api == "semantic_scholar"),
            },
        })

        # ── Phase 2c: Metadata Enrichment ─────────────────────────────────────
        yield _event("metadata_enrichment", "running")
        sources_enriched = await run_metadata_enricher(sources_deduped)
        enriched_count = sum(
            1 for o, n in zip(sources_deduped, sources_enriched)
            if o.abstract != n.abstract or o.journal_name != n.journal_name
        )
        phases_completed += 1
        yield _event("metadata_enrichment", "complete", {
            "total":    len(sources_enriched),
            "enriched": enriched_count,
        })

        # ── Phase 2d: ABS Evaluation + Citation Mapping (Parallel) ────────────
        yield _event("abs_check", "running")
        yield _event("citations", "running")

        abs_f      = lambda: run_abs_evaluator(sources_enriched)
        citation_f = lambda: run_citation_mapper(sources_enriched)

        (sources_approved, abs_result), citation_map = await _run_tasks_with_fallback([abs_f, citation_f])
        phases_completed += 1

        yield _event("abs_check", "complete", {
            "total_screened": len(sources_enriched),
            "quarantined":    abs_result.quarantine_count,
            "approved":       abs_result.pass_count,
            "verdicts":       [p.model_dump() for p in abs_result.papers],
        })
        yield _event("citations", "complete", citation_map.model_dump())

        sources_dicts = [s.model_dump() for s in sources_approved]

        # ── Phase 3: Parallel Ingestion through dynamic lenses ────────────────
        yield _event("modules", "running")
        modules = await run_ingestion_nodes(sources_dicts, dynamic_modules=dynamic_modules)
        phases_completed += 1
        yield _event("modules", "complete", {k: v.model_dump() for k, v in modules.items()})

        # ── Phase 4a: Resonance Detector ──────────────────────────────────────
        yield _event("resonance", "running")
        resonance = await run_resonance_detector(modules)
        phases_completed += 1
        yield _event("resonance", "complete", resonance.model_dump())

        # ── Phase 4b: Rupture Protocol ────────────────────────────────────────
        rupture = run_rupture_protocol(resonance)
        yield _event("rupture", "complete", rupture.model_dump())

        if rupture.triggered:
            yield _event("rupture_search", "running")
            try:
                rupture_sources_raw = await fetch_literature(query, max_results=8, rupture_mode=True)
                rupture_dedup = run_deduplication(rupture_sources_raw + sources_approved)
                new_sources = [
                    s for s in rupture_dedup.unique_sources
                    if s.title not in {x.title for x in sources_approved}
                ]
                sources_approved.extend(new_sources)
                sources_dicts = [s.model_dump() for s in sources_approved]
                rupture_sources_added = len(new_sources)
                yield _event("rupture_search", "complete", {"new_sources_added": rupture_sources_added})
            except Exception as exc:
                logger.warning(f"Rupture search failed: {exc}")
                yield _event("rupture_search", "complete", {"new_sources_added": 0})

        # ── Phase 5a: Assemblage + Relationship Mapping (Parallel) ────────────
        yield _event("assemblage", "running")
        yield _event("graph", "running")

        assemblage_f = lambda: run_assemblage_builder(entry, modules, resonance, rupture)
        graph_f      = lambda: run_relationship_mapper(entry, modules, resonance, rupture)

        assemblage, graph = await _run_tasks_with_fallback([assemblage_f, graph_f])
        yield _event("assemblage", "complete", assemblage.model_dump())

        # ── Phase 5b: Rhizome Builder ─────────────────────────────────────────
        updated_graph, persist_result = await run_rhizome_builder(graph, rupture)
        phases_completed += 1

        yield _event("graph", "complete", {
            **updated_graph.model_dump(),
            "persist": persist_result.model_dump(),
            "centralization": {
                "detected":         persist_result.graph_centralized,
                "ratio":            persist_result.centralization_ratio,
                "central_node_ids": persist_result.central_node_ids,
            },
        })

        # ── Phase 5c: Traversal Suggester ─────────────────────────────────────
        yield _event("traversal_suggestions", "running")
        traversal_suggestions = await run_traversal_suggester(query, assemblage, resonance, rupture)
        yield _event("traversal_suggestions", "complete", traversal_suggestions.model_dump())

        # ── Phase 6: Cartographic Output ──────────────────────────────────────
        cartography = build_cartographic_output(
            query, entry, modules, resonance, rupture, assemblage, updated_graph,
            abs_result=abs_result,
            traversal_suggestions=traversal_suggestions,
            centralization_ratio=persist_result.centralization_ratio,
            central_node_ids=persist_result.central_node_ids,
        )
        cartography.pipeline_meta = {
            "abs_quarantined":          abs_result.quarantine_count,
            "abs_approved":             abs_result.pass_count,
            "abs_contested_count":      abs_result.quarantine_count,
            "dedup_removed":            dedup_result.duplicates_removed,
            "metadata_enriched":        enriched_count,
            "anchor_papers":            citation_map.anchor_papers,
            "lens_names":               [l.name for l in epistemology.lenses],
            "rupture_triggered":        rupture.triggered,
            "neo4j_persisted":          persist_result.neo4j_enabled and persist_result.nodes_created > 0,
            "graph_centralized":        persist_result.graph_centralized,
            "centralization_ratio":     persist_result.centralization_ratio,
            "suggested_traversal_count": len(traversal_suggestions.suggested_traversals),
        }
        phases_completed += 1
        yield _event("cartography", "complete", cartography.model_dump())

        # ── Phase 7: Semantic Topography + Lens Cosine Matrix ─────────────────
        yield _event("topography", "running")

        # Build lens texts for cosine computation (reuses the BERT model load)
        lens_texts = [
            f"{l.name}: {l.core_question} ({l.tradition})"
            for l in epistemology.lenses
        ] if epistemology else None

        gap_analysis, lens_cosine_matrix = await run_semantic_topography(
            sources_approved, lens_texts=lens_texts
        )
        cartography.tab_topography = gap_analysis.model_dump()
        phases_completed += 1

        yield _event("topography", "complete", gap_analysis.model_dump())

        # ── Phase 8: Save Evaluation Run Report ───────────────────────────────
        end_time = datetime.now(timezone.utc)
        _, report_path = build_and_save_run_report(
            query=query,
            run_mode=run_mode,
            domain=domain,
            corpus_profile=corpus_profile,
            epistemology=epistemology,
            fallback_executed=fallback_executed,
            graph=updated_graph,
            persist_result=persist_result,
            rupture=rupture,
            gap_analysis=gap_analysis,
            rupture_sources_added=rupture_sources_added,
            start_time=start_time,
            end_time=end_time,
            phases_completed=phases_completed,
            errors=errors,
            lens_cosine_matrix=lens_cosine_matrix,
        )

        # ── Save run record ────────────────────────────────────────────────────
        try:
            run_record = RunRecord(
                run_id=run_id,
                query=query,
                timestamp=run_start,
                model=settings.ollama_model,
                token_usage=get_token_totals(),
                paper_count=abs_result.pass_count,
                lens_names=[l.name for l in epistemology.lenses],
                rupture_triggered=rupture.triggered,
                tab_entry=cartography.tab_entry or {},
                tab_modules=cartography.tab_modules or {},
                tab_resonance=cartography.tab_resonance or {},
                tab_assemblage=cartography.tab_assemblage or {},
                tab_cartography=cartography.tab_cartography or {},
                tab_graph=cartography.tab_graph or {},
                tab_topography=cartography.tab_topography or {},
                pipeline_meta=cartography.pipeline_meta or {},
            )
            save_run(run_record)
        except Exception as exc:
            logger.warning(f"Run save failed (non-fatal): {exc}")

        # ── Final: Full payload ────────────────────────────────────────────────
        yield _event("done", "complete", {
            "tab_entry":       cartography.tab_entry,
            "tab_modules":     cartography.tab_modules,
            "tab_resonance":   cartography.tab_resonance,
            "tab_assemblage":  cartography.tab_assemblage,
            "tab_cartography": cartography.tab_cartography,
            "tab_graph":       cartography.tab_graph,
            "tab_topography":  cartography.tab_topography,
            "pipeline_meta":   cartography.pipeline_meta,
            "run_id":          run_id,
            "report_path":     str(report_path) if report_path else None,
        })

    except Exception as exc:
        logger.error(f"Pipeline error: {exc}", exc_info=True)
        errors.append(str(exc))
        # Save partial report even on error
        try:
            end_time = datetime.now(timezone.utc)
            build_and_save_run_report(
                query=query,
                run_mode=run_mode,
                domain=domain,
                corpus_profile=corpus_profile,
                epistemology=epistemology,
                fallback_executed=fallback_executed,
                graph=graph,
                persist_result=persist_result,
                rupture=rupture,
                gap_analysis=gap_analysis,
                rupture_sources_added=rupture_sources_added,
                start_time=start_time,
                end_time=end_time,
                phases_completed=phases_completed,
                errors=errors,
                lens_cosine_matrix=lens_cosine_matrix,
            )
        except Exception:
            pass
        yield _event("error", "error", error=str(exc))


@router.post("/traverse")
async def traverse(request: QueryRequest):
    return StreamingResponse(
        _pipeline_generator(
            query=request.query,
            max_sources=request.max_sources or 15,
            use_dynamic_lenses=request.use_dynamic_lenses if request.use_dynamic_lenses is not None else True,
            project_id=request.project_id,
            custom_lenses=request.custom_lenses,
            run_mode=request.run_mode or "controlled",
            domain=request.domain or "other",
            corpus_profile=request.corpus_profile or "natural",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
