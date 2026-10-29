"""
Evaluation run reporter — writes output/runs/<run_id>/run_report.json
conforming to the evaluation schema described in Serrano et al. (2026), arXiv:2603.28336.
Called at the end of every pipeline run.
"""
import csv
import json
import math
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from pipeline import logger


THRESHOLDS = {
    "dr1_mean_cosine_max":      0.60,
    "dr1_max_cosine_max":       0.75,
    "dr1_lens_count_min":       3,
    "dr1_lens_count_max":       5,
    "dr2_entropy_min":          0.50,
    "dr2_entropy_degraded_min": 0.30,
    "dr4_latency_max_s":        60,
    "dr6_provenance_min":       1.0,
    "dr6_provenance_degraded":  0.95,
    "centralization_threshold": 0.40,
}


def get_output_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(os.environ.get("RHIZOMATIC_EXE_DIR", Path(sys.executable).parent))
    else:
        base = Path(__file__).parent.parent.parent
    return base / "output" / "runs"


# ── Verdict helpers ───────────────────────────────────────────────────────────

def _shannon(counts: dict) -> float:
    total = sum(counts.values())
    if not total:
        return 0.0
    h = 0.0
    for v in counts.values():
        if v > 0:
            p = v / total
            h -= p * math.log2(p)
    return round(h, 4)


def _v_dr1(dr1: dict) -> str:
    lc = dr1.get("lens_count", 0)
    mean_c = dr1.get("mean_pairwise_cosine")
    max_c  = dr1.get("max_pairwise_cosine")
    fail = (
        lc < THRESHOLDS["dr1_lens_count_min"]
        or lc > THRESHOLDS["dr1_lens_count_max"]
        or (mean_c is not None and mean_c > THRESHOLDS["dr1_mean_cosine_max"])
        or (max_c  is not None and max_c  > THRESHOLDS["dr1_max_cosine_max"])
    )
    if fail:
        return "FAIL"
    return "DEGRADED" if dr1.get("fallback_executed") else "PASS"


def _v_dr2(dr2: dict) -> str:
    if not dr2.get("has_critical_edges") or not dr2.get("has_rhizomatic_edges"):
        return "FAIL"
    prov = dr2.get("provenance_completeness")
    if prov is not None and prov < 1.0:
        return "FAIL"
    e = dr2.get("edge_type_entropy", 0)
    if e < THRESHOLDS["dr2_entropy_degraded_min"]:
        return "FAIL"
    return "DEGRADED" if e < THRESHOLDS["dr2_entropy_min"] else "PASS"


def _v_dr3(dr3: dict) -> str:
    expected = dr3.get("rupture_trigger_expected")
    if expected is None:
        return "OBSERVATIONAL"
    return "PASS" if dr3.get("rupture_trigger") == expected else "FAIL"


def _v_dr4(dr4: dict, corpus_profile: str) -> str:
    if corpus_profile != "llm_suppressed":
        return "OBSERVATIONAL"
    if not dr4.get("deterministic_fallback_executed"):
        return "FAIL"
    if dr4.get("every_added_source_has_recruitment_path_provenance") is False:
        return "FAIL"
    latency = dr4.get("fallback_latency_s")
    if latency is not None and latency > THRESHOLDS["dr4_latency_max_s"]:
        return "DEGRADED"
    return "PASS"


def _v_dr5(dr5: dict) -> str:
    if not dr5.get("all_seven_tabs_populated"):
        return "FAIL"
    if dr5.get("clusters_detected", 0) < 1:
        return "FAIL"
    zeros = (
        (1 if dr5.get("semantic_voids_detected", 0) < 1 else 0)
        + (1 if dr5.get("orthogonal_isolations", 0) < 1 else 0)
    )
    if zeros >= 2:
        return "FAIL"
    return "DEGRADED" if zeros == 1 else "PASS"


def _v_dr6(dr6: dict, corpus_profile: str) -> str:
    if corpus_profile == "centralized":
        if dr6.get("centralization_warning_fired") != dr6.get("centralization_warning_expected"):
            return "FAIL"
    prov = dr6.get("provenance_completeness")
    if prov is None:
        return "NOT_MEASURED"
    if prov < THRESHOLDS["dr6_provenance_degraded"]:
        return "FAIL"
    if prov < THRESHOLDS["dr6_provenance_min"]:
        return "DEGRADED"
    return "PASS"


def _overall(verdicts: dict) -> str:
    vals = [v for k, v in verdicts.items() if k not in ("overall", "verdict_basis") and v not in ("OBSERVATIONAL", "NOT_MEASURED")]
    if "FAIL" in vals:
        return "FAIL"
    return "DEGRADED" if "DEGRADED" in vals else "PASS"


# ── Main entry point ─────────────────────────────────────────────────────────

def build_and_save_run_report(
    *,
    query: str,
    run_mode: str = "controlled",
    domain: str = "other",
    corpus_profile: str = "natural",
    epistemology,           # EpistemologyOutput | None
    fallback_executed: bool,
    graph,                  # RelationshipGraph | None
    persist_result,         # RhizomePersistResult | None
    rupture,                # RuptureOutput | None
    gap_analysis,           # GapAnalysis | None
    rupture_sources_added: int = 0,
    start_time: datetime,
    end_time: datetime,
    phases_completed: int = 7,
    errors: list | None = None,
    lens_cosine_matrix: list | None = None,
) -> tuple[str, Path | None]:
    """
    Build and write run_report.json.  Returns (run_id, report_path).
    """
    run_id = str(uuid.uuid4())
    errors = errors or []

    # ── DR1 ──────────────────────────────────────────────────────────────────
    lenses = list(epistemology.lenses) if epistemology else []
    lens_titles      = [l.name for l in lenses]
    lens_traditions  = [l.tradition for l in lenses]

    mean_cos = max_cos = min_cos = None
    pairwise = None
    if lens_cosine_matrix and len(lens_cosine_matrix) > 1:
        n = len(lens_cosine_matrix)
        pairs = [lens_cosine_matrix[i][j] for i in range(n) for j in range(i + 1, n)]
        if pairs:
            mean_cos = round(sum(pairs) / len(pairs), 4)
            max_cos  = round(max(pairs), 4)
            min_cos  = round(min(pairs), 4)
        pairwise = lens_cosine_matrix

    # Jaccard term overlap across lens signal vocabularies
    jaccard = None
    if len(lenses) >= 2:
        pj = []
        for i in range(len(lenses)):
            for j in range(i + 1, len(lenses)):
                a = {w.lower() for w in lenses[i].signal_vocabulary}
                b = {w.lower() for w in lenses[j].signal_vocabulary}
                if a | b:
                    pj.append(len(a & b) / len(a | b))
        if pj:
            jaccard = round(sum(pj) / len(pj), 4)

    dr1 = {
        "lens_count":                len(lenses),
        "lens_titles":               lens_titles,
        "lens_embeddings_model":     "scibert-scivocab-uncased" if pairwise else None,
        "pairwise_cosine":           pairwise,
        "mean_pairwise_cosine":      mean_cos,
        "max_pairwise_cosine":       max_cos,
        "min_pairwise_cosine":       min_cos,
        "lens_jaccard_term_overlap": jaccard,
        "lens_traditions_declared":  lens_traditions,
        "fallback_executed":         fallback_executed,
    }

    # ── DR2 ──────────────────────────────────────────────────────────────────
    edge_counts = {"constructive": 0, "critical": 0, "rhizomatic": 0}
    if graph:
        for edge in graph.edges:
            et = getattr(edge, "edge_type", None) or "constructive"
            edge_counts[et] = edge_counts.get(et, 0) + 1

    edges_total = sum(edge_counts.values())
    ratios = {k: round(v / edges_total, 4) if edges_total else 0.0 for k, v in edge_counts.items()}
    # Edges carry no per-edge provenance record yet, so completeness is not measured.
    provenance = None

    dr2 = {
        "edge_type_counts":       edge_counts,
        "edge_type_ratios":       ratios,
        "has_critical_edges":     edge_counts.get("critical", 0) > 0,
        "has_rhizomatic_edges":   edge_counts.get("rhizomatic", 0) > 0,
        "edge_type_entropy":      _shannon(edge_counts),
        "edges_with_provenance":  None,
        "edges_total":            edges_total,
        "provenance_completeness": provenance,
    }

    # ── DR3 ──────────────────────────────────────────────────────────────────
    centralization_ratio = getattr(persist_result, "centralization_ratio", 0.0) if persist_result else 0.0
    rupture_triggered    = getattr(rupture, "triggered", False) if rupture else False
    rupture_expected     = {"convergent": True, "heterodox": False}.get(corpus_profile)

    dr3 = {
        "centralization_metric":      round(centralization_ratio, 4),
        "rupture_trigger":            rupture_triggered,
        "rupture_trigger_expected":   rupture_expected,
        "trigger_latency_s":          None,
        "post_trigger_sources_added": rupture_sources_added,
        "post_trigger_centralization": None,
    }

    # ── DR4 ──────────────────────────────────────────────────────────────────
    dr4 = {
        "llm_recruitment_path_executed":   not fallback_executed,
        "deterministic_fallback_executed": fallback_executed,
        "fallback_trigger_reason":         "llm_failed" if fallback_executed else "none",
        "fallback_latency_s":              None,
        "sources_added_by_path": {
            "llm":           rupture_sources_added if not fallback_executed else 0,
            "deterministic": rupture_sources_added if fallback_executed else 0,
        },
        "every_added_source_has_recruitment_path_provenance": None,
    }

    # ── DR5 ──────────────────────────────────────────────────────────────────
    clusters_n = voids_n = isolations_n = margin_n = 0
    if gap_analysis and getattr(gap_analysis, "bert_enabled", False):
        clusters_n   = len(gap_analysis.semantic_clusters)
        voids_n      = len(gap_analysis.semantic_voids)
        isolations_n = len(gap_analysis.orthogonal_isolations)
        margin_n     = len(gap_analysis.marginalization_index)

    dr5 = {
        "umap_params":             getattr(gap_analysis, "umap_params", None) or None,
        "hdbscan_params":          getattr(gap_analysis, "hdbscan_params", None) or None,
        "clusters_detected":       clusters_n,
        "semantic_voids_detected": voids_n,
        "orthogonal_isolations":   isolations_n,
        "marginalization_index":   margin_n,
        "rendered_ui_tabs":        ["entry", "modules", "resonance", "assemblage",
                                    "cartography", "graph", "topography"],
        "all_seven_tabs_populated": not bool(errors),
    }

    # ── DR6 ──────────────────────────────────────────────────────────────────
    centralization_fired    = getattr(persist_result, "graph_centralized", False) if persist_result else False
    centralization_expected = True if corpus_profile == "centralized" else None

    dr6 = {
        "provenance_completeness":       provenance,
        "centralization_warning_fired":  centralization_fired,
        "centralization_warning_expected": centralization_expected,
        "centralization_threshold":      THRESHOLDS["centralization_threshold"],
        "auditable_metadata_schema_version": "1.0",
        "audit_log_path":                f"output/runs/{run_id}/audit.log",
    }

    # ── Run-level ────────────────────────────────────────────────────────────
    runtime_s = (end_time - start_time).total_seconds()
    neo4j_ok  = bool(
        persist_result
        and getattr(persist_result, "neo4j_enabled", False)
        and getattr(persist_result, "nodes_created", 0) > 0
    )

    run_level = {
        "total_runtime_s":   round(runtime_s, 1),
        "tokens_prompt":     None,
        "tokens_completion": None,
        "tokens_total":      None,
        "neo4j_persistence_ok": neo4j_ok,
        "phases_completed":  phases_completed,
        "agents_invoked":    None,
        "errors":            errors,
    }

    # ── Verdicts ─────────────────────────────────────────────────────────────
    verdicts = {
        "dr1": _v_dr1(dr1),
        "dr2": _v_dr2(dr2),
        "dr3": _v_dr3(dr3),
        "dr4": _v_dr4(dr4, corpus_profile),
        "dr5": _v_dr5(dr5),
        "dr6": _v_dr6(dr6, corpus_profile),
    }
    verdicts["overall"]      = _overall(verdicts)
    verdicts["verdict_basis"] = "DR1–DR6 evaluation thresholds, Serrano et al. (2026)"

    report = {
        "run_id":           run_id,
        "timestamp_iso":    start_time.isoformat(),
        "artifact_version": "V4",
        "run_mode":         run_mode,
        "topic":            query,
        "domain":           domain,
        "corpus_profile":   corpus_profile,
        "dr1":  dr1,
        "dr2":  dr2,
        "dr3":  dr3,
        "dr4":  dr4,
        "dr5":  dr5,
        "dr6":  dr6,
        "run_level": run_level,
        "verdict":   verdicts,
    }

    # ── Persist ──────────────────────────────────────────────────────────────
    output_dir = get_output_dir()
    run_dir    = output_dir / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "run_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        index_path   = output_dir / "index.csv"
        write_header = not index_path.exists()
        with open(index_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "run_id", "artifact_version", "run_mode", "corpus_profile",
                "topic", "domain", "overall_verdict", "timestamp_iso",
            ])
            if write_header:
                writer.writeheader()
            writer.writerow({
                "run_id":           run_id,
                "artifact_version": report["artifact_version"],
                "run_mode":         run_mode,
                "corpus_profile":   corpus_profile,
                "topic":            query[:120],
                "domain":           domain,
                "overall_verdict":  verdicts["overall"],
                "timestamp_iso":    report["timestamp_iso"],
            })

        logger.info(f"Run report saved → {report_path}")
        return run_id, report_path

    except Exception as exc:
        logger.error(f"Failed to save run report: {exc}")
        return run_id, None
