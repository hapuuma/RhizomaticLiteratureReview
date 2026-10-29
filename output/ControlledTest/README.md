# Controlled Test Runs (V4)

The four controlled runs reported in the Stage 1 proposal ("Mapping, Not Funneling"). Each folder holds the `run_report.json` written automatically by `backend/pipeline/run_reporter.py` at the end of a pipeline run. `index.csv` lists the four runs.

| Topic | Run ID | Date | Lenses | Rupture | Sources added | Edge provenance | Clusters |
|---|---|---|---|---|---|---|---|
| Information systems AI workforce | `cc13ea96` | 2026-05-18 | 4 | fired | 10 | 100% | 2 |
| Circular Economy | `1a37ef68` | 2026-05-18 | 4 | fired | 10 | 100% | 2 |
| AI management | `6ccf1885` | 2026-05-18 | 4 | fired | 10 | 100% | 2 |
| Consulting service development with modularity | `8638f74a` | 2026-05-14 | 4 | fired | 9 | 100% | 2 |

New runs are written locally to `output/runs/<run_id>/`, which is not part of this repository. The practitioner trial reports are not included here.

## Reading the verdicts

Every report ends with a `verdict` block that scores the run against six design requirements (DR1–DR6; Serrano et al., 2026). The thresholds are deliberately strict and are defined in `THRESHOLDS` in `run_reporter.py`. All four runs have `"overall": "FAIL"`. This does **not** mean the pipeline failed to run. It means at least one scored requirement missed its threshold; the other requirements can still pass, as the table shows:

| Requirement | What is measured | Result in these runs |
|---|---|---|
| DR1: Lens diversity | Lens count 3–5, mean pairwise SciBERT cosine ≤ 0.60, max ≤ 0.75 | **FAIL**: 4 lenses with zero term overlap (Jaccard = 0), but mean cosine is 0.86–0.90 |
| DR2: Typed opposition | Critical and rhizomatic edges present, full provenance, edge-type entropy ≥ 0.50 | PASS: entropy 1.33–1.44 |
| DR3: Convergence detection | Rupture trigger matches the expected value | OBSERVATIONAL: no expected value was set, so the result is recorded only |
| DR4: Deterministic fallback | Scored only for the `llm_suppressed` corpus profile | OBSERVATIONAL: the LLM recruitment path ran in all four runs |
| DR5: Cartographic output | All seven tabs populated, ≥ 1 cluster, voids and isolations detected | DEGRADED (3 runs) / FAIL (modularity): no semantic voids at the fixed cluster setting |
| DR6: Auditable provenance | Edge provenance completeness = 1.0 | PASS as recorded, but not independently measured (see below) |

The overall verdict is FAIL whenever any scored requirement is FAIL. The DR1 and DR5 shortfalls are the open problems the proposal takes into Stage 2: whether embedding similarity is the right measure of paradigmatic distance, and adaptive cluster resolution.

Token usage was recorded separately from these reports (`tokens_*` fields are `null`).

## Known reporting errors in these four reports

These reports were generated before the following fixes to `run_reporter.py`. They are left unedited as the original outputs. Read these fields as follows:

- **`dr5.umap_params` / `dr5.hdbscan_params`** list `n_components: 2` and `min_cluster_size: 5`. The pipeline actually clustered on a 10-component UMAP embedding (2D and 3D projections are for display only), with `min_cluster_size = max(2, corpus_size // 5)`. The reporter now records the parameters actually used.
- **`run_level.agents_invoked`** holds the phase count, not the number of agents. It is now `null` (not measured).
- **Provenance**: `provenance_completeness` (DR2, DR6) was set to 1.0 whenever the graph had any edges, and `every_added_source_has_recruitment_path_provenance` (DR4) was always `true`. Edges do not yet carry a per-edge provenance record, so these values were not measured. The DR6 PASS above therefore reflects that assumption, not a check. The reporter now writes `null` for these fields and DR6 is reported as `NOT_MEASURED`, which does not count towards the overall verdict.

