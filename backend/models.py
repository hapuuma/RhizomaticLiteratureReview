from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


# ─── Request ─────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., description="The user's phenomenon zone / research query")
    max_sources: Optional[int] = Field(15, description="Max papers to fetch from OpenAlex")
    project_id: Optional[str] = Field(None, description="Project ID for isolated workspaces (V3)")
    use_dynamic_lenses: Optional[bool] = Field(True, description="Use Epistemology Agent for dynamic lenses (V3)")
    # Pre-generated / user-edited lenses from the UI — skips Phase 1 when present
    custom_lenses: Optional[List[dict]] = Field(None, description="Pre-generated lenses to use instead of running the Epistemology Agent")
    # Evaluation metadata (optional — can be filled in run_report.json post-hoc)
    run_mode: Optional[str] = Field("controlled", description="controlled | interview")
    domain: Optional[str] = Field("other", description="IS | management | sustainability | AI_governance | org_learning | other")
    corpus_profile: Optional[str] = Field("natural", description="natural | convergent | heterodox | centralized | llm_suppressed")


# ─── Literature Search ────────────────────────────────────────────────────────

class RawSource(BaseModel):
    title: str
    authors: List[str]
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source_api: Optional[str] = Field("openalex", description="Which API this came from: openalex | arxiv")
    journal_name: Optional[str] = Field(None, description="Journal or venue name for ABS screening")


class SearchResult(BaseModel):
    query: str
    sources: List[RawSource]


# ─── V3: Projects ─────────────────────────────────────────────────────────────

class ProjectConfig(BaseModel):
    use_dynamic_lenses: bool = True
    num_lenses: int = 4
    abs_screening: bool = True
    deduplication: bool = True
    citation_mapping: bool = True
    neo4j_persist: bool = False
    bert_topography: bool = False


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    config: ProjectConfig = Field(default_factory=ProjectConfig)
    query_history: List[str] = Field(default_factory=list)


# ─── V3: Epistemology Agent ───────────────────────────────────────────────────

class LensDefinition(BaseModel):
    name: str = Field(..., description="Short evocative lens name")
    tradition: str = Field(..., description="Theoretical tradition this lens draws from")
    core_question: str = Field(..., description="The single question this lens asks of every paper")
    signal_vocabulary: List[str] = Field(default_factory=list, description="Keywords to look for")
    axiom_it_dismantles: Optional[str] = Field(None, description="Dominant assumption this lens ruptures")
    is_rupture_lens: bool = Field(False, description="True if this lens is specifically an axiomatic rupture lens")


class EpistemologyOutput(BaseModel):
    lenses: List[LensDefinition]
    dominant_paradigm_risk: str
    epistemological_rationale: str


# ─── V3: ABS Evaluator ───────────────────────────────────────────────────────

class ABSPaperVerdict(BaseModel):
    title: str
    verdict: str = Field(..., description="pass | quarantine | grey | preprint | practitioner")
    confidence: float = Field(0.5, description="0–1 confidence in verdict")
    signals_detected: List[str] = Field(default_factory=list)
    rationale: str


class ABSCheckResult(BaseModel):
    papers: List[ABSPaperVerdict]
    quarantine_count: int = 0
    pass_count: int = 0


# ─── V3: Deduplication ───────────────────────────────────────────────────────

class DeduplicationResult(BaseModel):
    unique_sources: List[RawSource]
    duplicates_removed: int = 0
    duplicate_pairs: List[Dict[str, str]] = Field(default_factory=list, description="Pairs of (kept, removed) titles")


# ─── V4: Metadata Enricher ───────────────────────────────────────────────────

class MetadataEnrichResult(BaseModel):
    sources: List[RawSource]
    enriched_count: int = 0
    message: str = ""


# ─── V4: Traversal Suggester ─────────────────────────────────────────────────

class TraversalSuggestion(BaseModel):
    query: str
    rationale: str
    trajectory: str = Field(..., description="deepening | rupturing | extending | transversal")
    tension_source: str = ""


class TraversalSuggestions(BaseModel):
    suggested_traversals: List[TraversalSuggestion] = Field(default_factory=list)
    cartographic_note: str = ""


# ─── V3: Citation Mapper ─────────────────────────────────────────────────────

class ExplicitCitation(BaseModel):
    cited_work: str
    cited_by_papers: List[str]
    is_anchor: bool = False
    anchor_rationale: Optional[str] = None


class CitationShadow(BaseModel):
    inferred_work: str
    vocabulary_signature: List[str]
    likely_tradition: str


class CitationMapOutput(BaseModel):
    explicit_citations: List[ExplicitCitation]
    citation_shadows: List[CitationShadow]
    historical_lineage_note: str
    anchor_papers: List[str] = Field(default_factory=list, description="Names of anchor papers for graph seeding")


# ─── V3: Rhizome Builder (Neo4j edge schema) ─────────────────────────────────

class RhizomeEdgeConstructive(BaseModel):
    source_doi: str
    target_doi: str
    relationship: str = Field(..., description="extends | uses_method_from | builds_on")
    weight: float = Field(0.5)


class RhizomeEdgeCritical(BaseModel):
    source_doi: str
    target_doi: str
    relationship: str = Field(..., description="contradicts | critiques | problematizes")
    weight: float = Field(0.7)


class RhizomeEdgeRhizomatic(BaseModel):
    source_doi: str
    target_doi: str
    relationship: str = Field("ontological_rupture", description="paradigm shift / rupture edge")
    axiom_target: str = Field(..., description="The dominant assumption being challenged")
    counter_axiom: str = Field(..., description="The heterodox perspective introduced")
    rupture_vector: str = Field(..., description="Methodological | Epistemological | Ontological")
    weight: float = Field(1.0)


class RhizomePersistResult(BaseModel):
    nodes_created: int = 0
    constructive_edges: int = 0
    critical_edges: int = 0
    rhizomatic_edges: int = 0
    neo4j_enabled: bool = False
    message: str = "Neo4j persistence skipped (not configured)"
    # V4: graph centralization detection
    graph_centralized: bool = Field(False, description="True if top-3 nodes hold ≥40% of all edges")
    central_node_ids: List[str] = Field(default_factory=list, description="Most dominant node IDs")
    centralization_ratio: float = Field(0.0, description="Fraction of edges concentrated in top-3 nodes")


# ─── V3: Semantic Topography (BERT/UMAP/HDBSCAN) ────────────────────────────

class SemanticCluster(BaseModel):
    cluster_id: int
    label: str = Field(..., description="Evocative label for this semantic cluster")
    paper_titles: List[str]
    centroid_terms: List[str] = Field(default_factory=list)
    size: int = 0


class SemanticVoid(BaseModel):
    void_id: int
    description: str = Field(..., description="What kind of literature is absent here")
    adjacent_cluster_labels: List[str]
    quantified_gap: Optional[float] = Field(None, description="Distance metric between clusters")


class OrthogonalIsolation(BaseModel):
    cluster_a_label: str
    cluster_b_label: str
    shared_vocabulary: List[str]
    semantic_distance: float
    interpretation: str = Field(..., description="Why these clusters fail to cross-pollinate")


class MarginalizationEntry(BaseModel):
    paper_title: str
    semantic_distance_from_center: float
    geographic_region: Optional[str] = None
    marginalization_signal: str


class GapAnalysis(BaseModel):
    semantic_clusters: List[SemanticCluster]
    semantic_voids: List[SemanticVoid]
    orthogonal_isolations: List[OrthogonalIsolation]
    marginalization_index: List[MarginalizationEntry]
    bert_enabled: bool = False
    message: str = "BERT topography skipped (not configured)"
    # Per-paper UMAP coordinates for interactive 2D/3D scatter plots
    # Each entry: {title, x, y, cluster_id, cluster_label, is_marginalized}
    umap_points_2d: List[Dict[str, Any]] = Field(default_factory=list)
    # Each entry: {title, x, y, z, cluster_id, cluster_label, is_marginalized}
    umap_points_3d: List[Dict[str, Any]] = Field(default_factory=list)
    # Parameters actually used for clustering (recorded in run_report.json)
    umap_params: Dict[str, Any] = Field(default_factory=dict)
    hdbscan_params: Dict[str, Any] = Field(default_factory=dict)


# ─── Stage 1-2: Entry Layer ───────────────────────────────────────────────────

class EntryLayerOutput(BaseModel):
    active_entry_points: List[str]
    dominant_frameworks_detected: List[str]
    rupture_risk: bool = Field(False, description="True if dominant frameworks threaten to overwhelm")
    narrative: str


# ─── Stage 3: Ingestion Node Output (per module/lens) ────────────────────────

class AnalyzedSource(BaseModel):
    title: str
    authors: Union[str, List[str]] = Field(default="Unknown")
    relevance_signal: Optional[str] = Field(None, description="Optional relevance signal")

    @field_validator("authors", mode="before")
    @classmethod
    def normalize_authors(cls, v: Any) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)


class IngestionOutput(BaseModel):
    module: str
    analyzed_sources: List[AnalyzedSource]
    extracted_becomings: List[str]
    identified_tensions: List[str]
    conceptual_entanglement_nexus: str
    # V3: lens resonance score per source (populated when dynamic lenses used)
    lens_resonance_scores: Optional[Dict[str, float]] = Field(None, description="Per-source resonance scores for this lens")


# ─── Stage 4: Resonance Detector ─────────────────────────────────────────────

class ConvergentAnomaly(BaseModel):
    phenomenon: str
    fields_involved: List[str]
    interfering_frameworks: List[str]
    amplification_signal: str


class ResonanceOutput(BaseModel):
    convergent_anomalies: List[ConvergentAnomaly]
    cross_module_tensions: List[str]
    dominant_frameworks_ruptured: List[str] = Field(default_factory=list)
    rupture_trigger: bool = Field(False, description="True if Rupture Protocol should fire")
    rupture_rationale: Optional[str]
    synthesis_note: str


# ─── Stage 5: Rupture Protocol ────────────────────────────────────────────────

class RuptureOutput(BaseModel):
    triggered: bool
    dominant_frameworks_ruptured: List[str]
    outside_view_entry_points: List[str]
    rupture_narrative: str
    # V3: Rupture Agent additions
    axiom_targets: List[str] = Field(default_factory=list, description="Specific axioms being targeted for inversion")
    counter_axioms: List[str] = Field(default_factory=list, description="Heterodox perspectives introduced")
    rupture_vectors: List[str] = Field(default_factory=list, description="Methodological | Epistemological | Ontological per target")


# ─── Stage 6: Assemblage Builder ─────────────────────────────────────────────

class ProvisionalAssemblage(BaseModel):
    label: str
    constituting_elements: List[str]
    becoming_narrative: str  # MUST use present continuous


class AssemblageOutput(BaseModel):
    provisional_assemblages: List[ProvisionalAssemblage]
    deterritorializing_forces: List[str]
    reterritorializing_forces: List[str]
    dominant_narrative: str  # Full present-continuous narrative


# ─── Stage 7: Cartographic Output (6-tab + topography payload) ───────────────

class CartographicOutput(BaseModel):
    tab_entry: Dict[str, Any]
    tab_modules: Dict[str, Any]       # keys: lens/module names → IngestionOutput
    tab_resonance: Dict[str, Any]
    tab_assemblage: Dict[str, Any]
    tab_cartography: Dict[str, Any]
    tab_graph: Dict[str, Any]
    # V3: new tabs
    tab_topography: Dict[str, Any] = Field(default_factory=dict, description="Semantic Topography / Gap Analysis data")
    # V3: pipeline metadata
    pipeline_meta: Dict[str, Any] = Field(default_factory=dict, description="ABS counts, dedup stats, citation anchors, lens names")


# ─── SSE Event Envelope ──────────────────────────────────────────────────────

class PipelineEvent(BaseModel):
    stage: str                         # e.g. "entry", "modules", "resonance", ...
    status: str                        # "running" | "complete" | "error"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ─── Stage 8: Relationship Mapping (Graph) ────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    type: str = Field(..., description="actor | concept | technology | tension | rupture")
    importance: float = Field(0.5, description="Intensity/weight 0-1")
    description: str
    # V3: rupture node metadata
    is_rupture_node: bool = Field(False, description="True if this node was introduced by the Rupture Agent")
    axiom_dismantled: Optional[str] = Field(None, description="The axiom this rupture node dismantles")


class GraphEdge(BaseModel):
    source: str
    target: str = Field("unknown", description="The target node ID")
    relationship: str = Field("connected to", description="The nature of the link")
    intensity: float = Field(0.5)
    # V3: edge classification per Neo4j schema
    edge_type: str = Field("constructive", description="constructive | critical | rhizomatic")
    axiom_target: Optional[str] = Field(None, description="For rhizomatic edges: the axiom being challenged")
    counter_axiom: Optional[str] = Field(None, description="For rhizomatic edges: the heterodox perspective")
    rupture_vector: Optional[str] = Field(None, description="Methodological | Epistemological | Ontological")


class RelationshipGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


# ─── Run History ─────────────────────────────────────────────────────────────

class RunRecord(BaseModel):
    run_id: str
    query: str
    timestamp: str
    model: str
    token_usage: Dict[str, int]
    paper_count: int
    lens_names: List[str]
    rupture_triggered: bool
    tab_entry: Dict[str, Any]
    tab_modules: Dict[str, Any]
    tab_resonance: Dict[str, Any]
    tab_assemblage: Dict[str, Any]
    tab_cartography: Dict[str, Any]
    tab_graph: Dict[str, Any]
    tab_topography: Dict[str, Any]
    pipeline_meta: Dict[str, Any]


class RunSummary(BaseModel):
    run_id: str
    query: str
    timestamp: str
    model: str
    token_usage: Dict[str, int]
    paper_count: int
    lens_names: List[str]
    rupture_triggered: bool


# ─── Final Pipeline Response ─────────────────────────────────────────────────

class PipelineResponse(BaseModel):
    query: str
    entry: EntryLayerOutput
    modules: Dict[str, IngestionOutput]
    resonance: ResonanceOutput
    rupture: RuptureOutput
    assemblage: AssemblageOutput
    cartography: CartographicOutput
    graph: RelationshipGraph
    # V3: additional outputs
    epistemology: Optional[EpistemologyOutput] = None
    abs_check: Optional[ABSCheckResult] = None
    deduplication: Optional[DeduplicationResult] = None
    citation_map: Optional[CitationMapOutput] = None
    gap_analysis: Optional[GapAnalysis] = None
    # V4: new outputs
    metadata_enrichment: Optional[MetadataEnrichResult] = None
    traversal_suggestions: Optional[TraversalSuggestions] = None
