"""
V3: Semantic Topography Engine — Phase 5
Embeds all texts into high-dimensional vector space using SciBERT,
applies UMAP for dimensionality reduction, and HDBSCAN for clustering.
Identifies three types of structural gaps:
  1. Semantic Voids — empty vector space between related clusters
  2. Orthogonal Isolation — same vocabulary, separate semantic spaces
  3. Marginalization Index — geographic/disciplinary deflection from center

BERT is OPTIONAL and runs as a background task. Requires:
  pip install sentence-transformers umap-learn hdbscan

If not installed, returns a GapAnalysis with bert_enabled=False.
"""
import asyncio
from models import (
    GapAnalysis, SemanticCluster, SemanticVoid,
    OrthogonalIsolation, MarginalizationEntry, RawSource,
)
from config import settings
from pipeline import logger


def _try_import_bert_deps():
    """Try importing BERT-related dependencies. Returns None tuple if unavailable."""
    try:
        from sentence_transformers import SentenceTransformer
        import umap
        import hdbscan
        import numpy as np
        return SentenceTransformer, umap, hdbscan, np
    except ImportError as exc:
        logger.info(f"BERT dependencies not available ({exc}). Topography skipped.")
        return None, None, None, None


def _build_corpus(sources: list[RawSource]) -> list[str]:
    """Combine title + abstract for each source into a text corpus."""
    corpus = []
    for s in sources:
        text = s.title
        if s.abstract:
            text += " " + s.abstract
        corpus.append(text.strip())
    return corpus


def _detect_orthogonal_isolations(
    cluster_a: SemanticCluster,
    cluster_b: SemanticCluster,
    similarity_matrix,
    np,
) -> OrthogonalIsolation | None:
    """
    Detect if two clusters share vocabulary but occupy different semantic spaces.
    """
    vocab_a = set(cluster_a.centroid_terms)
    vocab_b = set(cluster_b.centroid_terms)
    shared = vocab_a & vocab_b

    if len(shared) < 2:
        return None

    # High term overlap but high semantic distance = orthogonal isolation
    semantic_dist = float(similarity_matrix[cluster_a.cluster_id][cluster_b.cluster_id])
    if semantic_dist > 0.6 and len(shared) >= 2:
        return OrthogonalIsolation(
            cluster_a_label=cluster_a.label,
            cluster_b_label=cluster_b.label,
            shared_vocabulary=list(shared),
            semantic_distance=semantic_dist,
            interpretation=(
                f"Clusters '{cluster_a.label}' and '{cluster_b.label}' are using "
                f"identical vocabulary ({', '.join(list(shared)[:3])}) but inhabiting "
                "entirely separate semantic spaces, indicating a failure to cross-pollinate "
                "despite shared surface terminology."
            ),
        )
    return None


def _compute_gap_analysis_from_clusters(
    sources: list[RawSource],
    labels: list[int],
    embeddings,
    np,
    coords_2d=None,
    coords_3d=None,
) -> GapAnalysis:
    """Build GapAnalysis from cluster labels and embeddings."""
    unique_labels = set(labels) - {-1}  # -1 = noise in HDBSCAN

    # Build semantic clusters
    clusters: list[SemanticCluster] = []
    cluster_centroids = {}

    for label in sorted(unique_labels):
        indices = [i for i, l in enumerate(labels) if l == label]
        cluster_sources = [sources[i] for i in indices]
        cluster_embeddings = embeddings[indices]
        centroid = np.mean(cluster_embeddings, axis=0)
        cluster_centroids[label] = centroid

        # Extract centroid terms from titles (simple frequency heuristic)
        all_words = []
        for s in cluster_sources:
            all_words.extend(s.title.lower().split())
        stopwords = {"the", "a", "an", "of", "in", "for", "and", "or", "is", "are",
                     "to", "with", "on", "at", "by", "from", "this", "that", "as"}
        word_freq = {}
        for w in all_words:
            w = w.strip('.,;:()"\'')
            if len(w) > 3 and w not in stopwords:
                word_freq[w] = word_freq.get(w, 0) + 1
        top_terms = sorted(word_freq, key=lambda x: -word_freq[x])[:6]

        # Generate evocative cluster label from top terms
        cluster_label = " · ".join(top_terms[:3]).title() if top_terms else f"Cluster {label}"

        clusters.append(
            SemanticCluster(
                cluster_id=label,
                label=cluster_label,
                paper_titles=[s.title for s in cluster_sources],
                centroid_terms=top_terms,
                size=len(cluster_sources),
            )
        )

    # Compute pairwise cluster distances
    cluster_list = sorted(unique_labels)
    n = len(cluster_list)
    dist_matrix = [[0.0] * n for _ in range(n)]
    for i, la in enumerate(cluster_list):
        for j, lb in enumerate(cluster_list):
            if i != j and la in cluster_centroids and lb in cluster_centroids:
                diff = cluster_centroids[la] - cluster_centroids[lb]
                dist_matrix[i][j] = float(np.linalg.norm(diff))

    # Semantic Voids: midpoints between related clusters that are empty
    semantic_voids: list[SemanticVoid] = []
    void_id = 0
    for i, la in enumerate(cluster_list):
        for j, lb in enumerate(cluster_list):
            if j <= i:
                continue
            dist = dist_matrix[i][j]
            # Mid-range distance = potential void (not too close, not too far)
            if 0.3 < dist < 0.8:
                ci = clusters[i]
                cj = clusters[j]
                semantic_voids.append(
                    SemanticVoid(
                        void_id=void_id,
                        description=(
                            f"Empty semantic space between '{ci.label}' and '{cj.label}' — "
                            "bridging literature connecting these traditions is absent."
                        ),
                        adjacent_cluster_labels=[ci.label, cj.label],
                        quantified_gap=round(dist, 4),
                    )
                )
                void_id += 1

    # Orthogonal Isolations
    orthogonal_isolations: list[OrthogonalIsolation] = []
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            oi = _detect_orthogonal_isolations(
                clusters[i], clusters[j], dist_matrix, np
            )
            if oi:
                orthogonal_isolations.append(oi)

    # Marginalization Index: papers far from the centroid of all embeddings
    global_centroid = np.mean(embeddings, axis=0)
    marginalization: list[MarginalizationEntry] = []
    distances = [float(np.linalg.norm(embeddings[i] - global_centroid))
                 for i in range(len(sources))]
    mean_dist = sum(distances) / len(distances) if distances else 1.0
    std_dist = float(np.std(distances)) if distances else 0.1

    for i, source in enumerate(sources):
        dist = distances[i]
        if dist > mean_dist + 1.5 * std_dist:
            marginalization.append(
                MarginalizationEntry(
                    paper_title=source.title,
                    semantic_distance_from_center=round(dist, 4),
                    geographic_region=None,  # Would require metadata enrichment
                    marginalization_signal=(
                        f"This paper is structurally distant from the corpus centroid "
                        f"(distance: {dist:.3f} vs mean: {mean_dist:.3f}), suggesting "
                        "marginalization from the dominant discourse."
                    ),
                )
            )

    # Build cluster label lookup
    cluster_label_map = {c.cluster_id: c.label for c in clusters}
    marginalized_titles = {m.paper_title for m in marginalization}

    # Per-paper UMAP coordinates for frontend scatter plots
    umap_points_2d = []
    if coords_2d is not None:
        for i, source in enumerate(sources):
            umap_points_2d.append({
                "title": source.title,
                "x": round(float(coords_2d[i][0]), 4),
                "y": round(float(coords_2d[i][1]), 4),
                "cluster_id": int(labels[i]),
                "cluster_label": cluster_label_map.get(labels[i], "Noise"),
                "is_marginalized": source.title in marginalized_titles,
                "year": source.year,
                "authors": ", ".join(source.authors[:2]) if source.authors else "",
            })

    umap_points_3d = []
    if coords_3d is not None:
        for i, source in enumerate(sources):
            umap_points_3d.append({
                "title": source.title,
                "x": round(float(coords_3d[i][0]), 4),
                "y": round(float(coords_3d[i][1]), 4),
                "z": round(float(coords_3d[i][2]), 4),
                "cluster_id": int(labels[i]),
                "cluster_label": cluster_label_map.get(labels[i], "Noise"),
                "is_marginalized": source.title in marginalized_titles,
                "year": source.year,
                "authors": ", ".join(source.authors[:2]) if source.authors else "",
            })

    return GapAnalysis(
        semantic_clusters=clusters,
        semantic_voids=semantic_voids,
        orthogonal_isolations=orthogonal_isolations,
        marginalization_index=marginalization,
        bert_enabled=True,
        message=f"SciBERT topography: {len(clusters)} clusters, {len(semantic_voids)} voids, {len(orthogonal_isolations)} orthogonal isolations.",
        umap_points_2d=umap_points_2d,
        umap_points_3d=umap_points_3d,
    )


def _pairwise_cosine(embeddings, np) -> list[list[float]]:
    """Compute pairwise cosine similarity matrix from an embedding array."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normed = embeddings / np.maximum(norms, 1e-10)
    matrix = normed @ normed.T
    n = len(embeddings)
    return [[round(float(matrix[i][j]), 4) for j in range(n)] for i in range(n)]


async def run_semantic_topography(
    sources: list[RawSource],
    lens_texts: list[str] | None = None,
) -> tuple[GapAnalysis, list[list[float]] | None]:
    """
    Run the full BERT semantic topography pipeline.
    Optionally embeds lens_texts and returns their pairwise cosine matrix.
    Returns (GapAnalysis, lens_cosine_matrix | None).
    """
    _stub = GapAnalysis(
        semantic_clusters=[],
        semantic_voids=[],
        orthogonal_isolations=[],
        marginalization_index=[],
        bert_enabled=False,
        message="",
    )

    if not settings.bert_enabled:
        _stub.message = "BERT topography disabled. Set BERT_ENABLED=true and install sentence-transformers, umap-learn, hdbscan to activate."
        return _stub, None

    SentenceTransformer, umap_lib, hdbscan_lib, np = _try_import_bert_deps()
    if SentenceTransformer is None:
        _stub.message = "BERT dependencies not installed. Run: pip install sentence-transformers umap-learn hdbscan"
        return _stub, None

    if len(sources) < 4:
        _stub.bert_enabled = True
        _stub.message = f"Insufficient sources for topography ({len(sources)} < 4 minimum)."
        return _stub, None

    try:
        loop = asyncio.get_event_loop()
        corpus = _build_corpus(sources)

        def _compute():
            model = SentenceTransformer(settings.bert_model)
            embeddings = model.encode(corpus, show_progress_bar=False)

            # Optionally embed lens texts using the same model load
            cosine_matrix = None
            if lens_texts and len(lens_texts) >= 2:
                import numpy as np_inner
                lens_embs = model.encode(lens_texts, show_progress_bar=False)
                cosine_matrix = _pairwise_cosine(lens_embs, np_inner)

            n_neighbors = min(15, len(corpus) - 1)

            # UMAP 10D for clustering (high-dimensional, more faithful structure)
            reducer_10d = umap_lib.UMAP(
                n_neighbors=n_neighbors,
                n_components=10,
                metric="cosine",
                random_state=42,
            )
            reduced = reducer_10d.fit_transform(embeddings)

            # UMAP 2D for visualization
            reducer_2d = umap_lib.UMAP(
                n_neighbors=n_neighbors,
                n_components=2,
                metric="cosine",
                random_state=42,
            )
            coords_2d = reducer_2d.fit_transform(embeddings)

            # UMAP 3D for visualization
            reducer_3d = umap_lib.UMAP(
                n_neighbors=n_neighbors,
                n_components=3,
                metric="cosine",
                random_state=42,
            )
            coords_3d = reducer_3d.fit_transform(embeddings)

            # HDBSCAN clustering on 10D space
            min_cluster_size = max(2, len(corpus) // 5)
            clusterer = hdbscan_lib.HDBSCAN(
                min_cluster_size=min_cluster_size,
                metric="euclidean",
                cluster_selection_method="eom",
            )
            labels = clusterer.fit_predict(reduced)
            return reduced, labels.tolist(), coords_2d.tolist(), coords_3d.tolist(), cosine_matrix

        reduced, labels, coords_2d, coords_3d, lens_cosine_matrix = await loop.run_in_executor(None, _compute)

        import numpy as np_module
        gap_analysis = _compute_gap_analysis_from_clusters(
            sources, labels, np_module.array(reduced), np_module,
            coords_2d=coords_2d, coords_3d=coords_3d,
        )
        gap_analysis.umap_params = {
            "n_neighbors": min(15, len(sources) - 1),
            "min_dist": 0.1,  # umap-learn default
            "n_components": 10,
            "metric": "cosine",
            "random_state": 42,
            "visualization_n_components": [2, 3],
        }
        gap_analysis.hdbscan_params = {
            "min_cluster_size": max(2, len(sources) // 5),
            "metric": "euclidean",
            "cluster_selection_method": "eom",
        }
        logger.info(f"Semantic Topography: {gap_analysis.message}")
        return gap_analysis, lens_cosine_matrix

    except Exception as exc:
        logger.error(f"Semantic Topography failed: {exc}")
        return GapAnalysis(
            semantic_clusters=[],
            semantic_voids=[],
            orthogonal_isolations=[],
            marginalization_index=[],
            bert_enabled=True,
            message=f"Topography computation failed: {exc}",
        ), None
