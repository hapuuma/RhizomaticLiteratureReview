"""
Stage 7: Cartographic Output Layer
Formats the final JSON payload mapped to the UI tabs.
No LLM call — pure data shaping.
"""
from models import (
    EntryLayerOutput, IngestionOutput, ResonanceOutput,
    RuptureOutput, AssemblageOutput, CartographicOutput,
    RelationshipGraph, ABSCheckResult, TraversalSuggestions,
)


def build_cartographic_output(
    query: str,
    entry: EntryLayerOutput,
    modules: dict[str, IngestionOutput],
    resonance: ResonanceOutput,
    rupture: RuptureOutput,
    assemblage: AssemblageOutput,
    graph: RelationshipGraph,
    abs_result: ABSCheckResult | None = None,
    traversal_suggestions: TraversalSuggestions | None = None,
    centralization_ratio: float = 0.0,
    central_node_ids: list[str] | None = None,
) -> CartographicOutput:
    """
    Maps all pipeline stage outputs to the six UI tabs.

    Tab 1 — ENTRY:      Entry layer active points + narrative
    Tab 2 — MODULES:    All three ingestion module outputs
    Tab 3 — RESONANCE:  Convergent anomalies + cross-module tensions
    Tab 4 — ASSEMBLAGE: Provisional assemblages + dominant narrative
    Tab 5 — CARTOGRAPHY: Movement map — sources, directions, open questions
    Tab 6 — GRAPH:       Interactive relationship network graph
    """
    # --- Tab 1-5 ... (same code)
    # --- Tab 1: Entry ---
    # Include quarantined papers as "epistemically contested sources" so users
    # can see what was screened out and decide whether to re-examine it.
    contested_sources = []
    if abs_result:
        contested_sources = [
            {"title": p.title, "verdict": p.verdict, "rationale": p.rationale,
             "confidence": p.confidence, "signals_detected": p.signals_detected}
            for p in abs_result.papers
            if p.verdict == "quarantine"
        ]

    tab_entry = {
        "query": query,
        "active_entry_points": entry.active_entry_points,
        "dominant_frameworks_detected": entry.dominant_frameworks_detected,
        "rupture_risk": entry.rupture_risk,
        "narrative": entry.narrative,
        "contested_sources": contested_sources,
        "contested_sources_note": (
            "These sources were flagged by ABS screening but are preserved here. "
            "Marginality within quality metrics may itself be a rupture signal."
        ) if contested_sources else "",
    }

    # --- Tab 2: Modules ---
    tab_modules = {
        key: val.model_dump() for key, val in modules.items()
    }

    # --- Tab 3: Resonance ---
    tab_resonance = {
        "convergent_anomalies": [a.model_dump() for a in resonance.convergent_anomalies],
        "cross_module_tensions": resonance.cross_module_tensions,
        "rupture_triggered": resonance.rupture_trigger,
        "rupture_rationale": resonance.rupture_rationale,
        "synthesis_note": resonance.synthesis_note,
        "rupture_protocol": {
            "triggered": rupture.triggered,
            "dominant_frameworks_ruptured": rupture.dominant_frameworks_ruptured,
            "outside_view_entry_points": rupture.outside_view_entry_points,
            "rupture_narrative": rupture.rupture_narrative,
        },
    }

    # --- Tab 4: Assemblage ---
    tab_assemblage = {
        "provisional_assemblages": [a.model_dump() for a in assemblage.provisional_assemblages],
        "deterritorializing_forces": assemblage.deterritorializing_forces,
        "reterritorializing_forces": assemblage.reterritorializing_forces,
        "dominant_narrative": assemblage.dominant_narrative,
    }

    # --- Tab 5: Cartography ---
    # Construct a movement map: sources × modules → connections × directions
    all_sources = []
    module_directions = {}
    for mod_key, mod_data in modules.items():
        module_directions[mod_key] = {
            "becomings": mod_data.extracted_becomings,
            "tensions": mod_data.identified_tensions,
            "nexus": mod_data.conceptual_entanglement_nexus,
        }
        for src in mod_data.analyzed_sources:
            all_sources.append({
                "title": src.title,
                "authors": src.authors,
                "module": mod_key,
                "signal": src.relevance_signal,
            })

    # Deduplicate sources by title
    seen = set()
    unique_sources = []
    for s in all_sources:
        if s["title"] not in seen:
            seen.add(s["title"])
            unique_sources.append(s)

    open_questions = [
        anomaly.phenomenon
        for anomaly in resonance.convergent_anomalies
    ]

    tab_cartography = {
        "research_trajectory": assemblage.dominant_narrative,
        "source_map": unique_sources,
        "module_directions": module_directions,
        "convergence_nodes": open_questions,
        "lines_of_flight": assemblage.deterritorializing_forces,
        "enclosures": assemblage.reterritorializing_forces,
        # V4: suggested next traversals
        "suggested_traversals": (
            [t.model_dump() for t in traversal_suggestions.suggested_traversals]
            if traversal_suggestions else []
        ),
        "cartographic_note": (
            traversal_suggestions.cartographic_note if traversal_suggestions else ""
        ),
        # V4: graph centralization warning
        "graph_centralization": {
            "detected": centralization_ratio >= 0.40,
            "ratio": centralization_ratio,
            "central_node_ids": central_node_ids or [],
            "warning": (
                "The rhizome is showing signs of arborification — "
                f"{centralization_ratio:.0%} of connections are concentrating "
                "in a small number of nodes. A rupture traversal is recommended."
            ) if centralization_ratio >= 0.40 else "",
        },
    }

    tab_graph = graph.model_dump()

    return CartographicOutput(
        tab_entry=tab_entry,
        tab_modules=tab_modules,
        tab_resonance=tab_resonance,
        tab_assemblage=tab_assemblage,
        tab_cartography=tab_cartography,
        tab_graph=tab_graph,
    )
