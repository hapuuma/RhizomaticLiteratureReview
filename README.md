# Rhizomatic Research Agent — V4

A process-relational research pipeline for literature analysis, tracing becomings rather than retrieving facts. Implements a **rhizomatic ontology** (Deleuzian) to analyze a phenomenon zone through 15 specialized agents running in a 7-phase pipeline.

---

## Prerequisites

- **Python 3.12+**
- **Ollama** running locally — [ollama.com](https://ollama.com)
- **Model pulled** (default):
  ```bash
  ollama pull mistral-large-3:675b-cloud
  ```

---

## Quick Start (Linux)

```bash
bash run_linux.sh
```

The launcher handles everything automatically:

- Creates and activates the Python virtual environment
- Installs all Python dependencies
- Downloads Kokoro TTS voice files from HuggingFace
- Downloads the spacy language model required by TTS
- Checks Ollama is running and pulls the configured model if missing
- Starts the server at `http://localhost:8000`

> On first run, expect a few minutes for downloads. Subsequent runs start in seconds.

---

## Configuration

All settings live in `backend/.env` (auto-created from `.env.example` on first run):

```env
# LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral-large-3:675b-cloud
OLLAMA_TIMEOUT=600

# Literature search
OPENALEX_EMAIL=your@email.com
OPENALEX_RESULTS_PER_PAGE=15

# Number of dynamic theoretical lenses (default: 4)
NUM_DYNAMIC_LENSES=4

# BERT Semantic Topography (Topology tab)
BERT_ENABLED=true
BERT_MODEL=allenai/scibert_scivocab_uncased

# Neo4j Graph Persistence (optional)
# NEO4J_ENABLED=true
# NEO4J_URI=bolt://localhost:7687
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=your_password
```

---

## Features

### Pipeline — 7 Tabs

| Tab | Content |
|---|---|
| Entry | Active entry points, dominant frameworks, rupture risk narrative |
| Modules | Per-lens ingestion output from all dynamic theoretical lenses |
| Resonance | Cross-lens tensions and convergent anomalies |
| Assemblage | Provisional constellations of becoming (present-continuous tense) |
| Cartography | Research trajectory, source mapping, traversal suggestions, pipeline metadata |
| Graph | Interactive D3.js force-directed knowledge graph |
| Topology | BERT semantic clusters, voids, orthogonal isolations, marginalization index |

### Kokoro TTS — Voice Reader

A voice reader bar appears once results are available. Powered by [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) — a natural-sounding open-source TTS model.

- Automatically announces *"Entry analysis ready"*, *"Modules analysis ready"*, etc. as each tab completes
- **▶ Play** — reads the current tab aloud using Kokoro
- **⏸ Pause / Resume**
- **■ Stop**
- **AUTO** — toggle auto-read: full tab content is read automatically as it arrives
- **Voice selector** — 10 voices: American and British, male and female

Voice files are downloaded automatically by `run_linux.sh`. Falls back to browser speech synthesis if the backend is unavailable.

### BERT Semantic Topography

Activates the Topology tab with SciBERT embeddings → UMAP (10D, cosine) → HDBSCAN clustering. Detects:
- **Semantic Clusters** — thematic groupings in vector space
- **Semantic Voids** — structural research gaps between cluster centroids
- **Orthogonal Isolations** — shared vocabulary, separate semantic spaces (disciplinary silos)
- **Marginalization Index** — papers > 1.5 standard deviations from the corpus centroid

Requires `BERT_ENABLED=true` and a minimum of four sources. Dependencies installed automatically by `run_linux.sh`.

### Neo4j Graph Persistence (optional)

Persists the classified knowledge graph across sessions. Install a local Neo4j instance, then set in `.env`:

```env
NEO4J_ENABLED=true
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### Graph Interaction

- **Click node** — info panel with axiom data for rupture nodes
- **Click rupture node** (diamond shape) — blast radius mode: dims unconnected nodes/edges
- **Click edge** — edge detail (constructive / critical / rhizomatic + axiom metadata)
- **Drag / zoom / pan** — standard D3 force graph

### Run History

Every completed traversal is saved to disk. Access past runs via the History panel or directly:

- `GET /api/runs` — list all runs (newest first), includes token usage per run
- `GET /api/runs/{run_id}` — retrieve full tab data for a specific run

---

## Methodological Framework (7-Phase Pipeline)

The Rhizomatic Research Agent employs a process-relational methodology, moving beyond static literature review toward a dynamic tracing of "becomings" within a phenomenon zone.

### Phase 1: Dynamic Ontological Setup (Epistemology Agent)

The pipeline begins by destabilizing the researcher's initial query. The **Epistemology Agent** analyzes the phenomenon zone and generates 3–5 **orthogonal theoretical lenses** (e.g., *Algorithmic Governmentality*, *Post-Human Affect*, *Thermodynamic Materialism*, *Degrowth Economics*). This ensures the corpus is not read through a single dominant paradigm but through a multi-vocal framework. If the LLM call fails, the agent falls back to static module definitions from configuration.

### Phase 2: Corpus Ingestion & Integrity

Six agents operate across four sub-phases:

- **Phase 2a (parallel):**
  - **Entry Layer** — identifies which of five rhizomatic entry points are active (material flows, information governance, organizing forms, imaginaries, assemblage moments), detects dominant frameworks implied by the query, assesses rupture risk, and generates an opening present-continuous narrative.
  - **Researcher (OpenAlex + arXiv + Semantic Scholar)** — triple-source concurrent fetching of metadata and abstracts, preserving both central and marginal scholarly voices.

- **Phase 2b — Deduplication** — DOI normalization and trigram Dice coefficient (≥ 0.85) produces a clean, non-redundant corpus.

- **Phase 2c — Metadata Enricher** — fills missing abstracts, journal names, and authors for any DOI-bearing paper via CrossRef (primary) and OpenAlex DOI lookup (fallback), running up to five concurrent enrichment calls.

- **Phase 2d (parallel):**
  - **ABS Evaluator** — cross-references journals against the Academic Journal Guide (ABS) database, supplemented by LLM signal checking. Quarantined papers are excluded from the active corpus but preserved in the output for inspection.
  - **Citation Mapper** — identifies structurally influential anchor papers and maps the citation shadow to reveal paradigmatic dominance structures.

### Phase 3: Parallel Ingestion Nodes

The corpus is processed through all dynamic lenses generated in Phase 1. Each lens runs as an autonomous concurrent agent, scanning the literature for lens-specific signal vocabularies and theoretical tensions. Uses `asyncio.gather`-based parallel execution; automatically falls back to sequential on LLM overload (429/503).

### Phase 4: Resonance & Rupture Detection

- **Resonance Detector** — cross-lens anomaly extraction: finds *convergent anomalies*, points where multiple theoretically incommensurable lenses independently locate the same tension or gap. Outputs a `rupture_trigger` boolean when dominant frameworks are enclosing the analysis.
- **Rupture Protocol** — deterministic (no LLM) routing agent that reads the `rupture_trigger` flag. When triggered, selects exterior theoretical positions (degrowth economics, post-colonial STS, indigenous ontologies, feminist political ecology, queer temporalities, anarchist infrastructure theory) and constructs a rupture narrative. The pipeline then fetches additional heterodox literature using rupture-mode query expansion.

> Note: Graph centralization detection (whether top nodes hold > 40% of edges) is performed by the Rhizome Builder in Phase 5b, not by the Rupture Protocol.

### Phase 5: Synthesis & Mapping

Four agents across three sub-phases:

- **Phase 5a (parallel):**
  - **Assemblage Builder** — synthesizes Entry Layer output, ingestion outputs, resonance findings, and rupture status into *provisional constellations of becoming*, written in present-continuous tense.
  - **Relationship Mapper** — constructs a weighted relational graph in which each edge carries metadata about relational type, strength, and theoretical grounding.

- **Phase 5b — Rhizome Builder** — classifies edges into three types via LLM:
  1. **Constructive (solid):** extends, builds-on, borrows-method
  2. **Critical (dashed):** contradicts, problematizes, challenges
  3. **Rhizomatic (neon):** paradigm ruptures that dismantle foundational axioms

  Also performs graph centralization detection (≥ 40% edge concentration in top nodes triggers a rupture recommendation). Optionally persists classified graph to Neo4j.

- **Phase 5c — Traversal Suggester** — generates 3–5 *lines of flight*: specific research queries the user can pursue next. Each is tagged with a trajectory type (deepening, rupturing, extending, or transversal) and a tension source.

### Phase 6: Cartographic Output

No dedicated agent. Pure data consolidation into six UI tabs. The Cartography tab includes traversal suggestions and a centralization warning if the 40% threshold was reached. Pipeline metadata recorded: aggregate token usage (prompt + completion + total + call count), paper count, lens names, rupture trigger status, Neo4j persistence status, centralization ratio, suggested traversal count. Full run record saved to the run history.

### Phase 7: Semantic Topography (BERT)

SciBERT-powered vector analysis provides a structural view of the corpus:
- **Semantic Clusters** — thematic groupings in high-dimensional vector space
- **Semantic Voids** — structural research gaps between cluster centroids (mid-range distance 0.3–0.8)
- **Orthogonal Isolation** — clusters using identical vocabulary but inhabiting separate semantic spaces
- **Marginalization Index** — papers > 1.5 standard deviations from the corpus centroid

Requires `BERT_ENABLED=true` and `sentence-transformers`, `umap-learn`, `hdbscan`. Minimum 4 sources. Runs in a thread pool executor to avoid blocking the async pipeline.

---

## Scientific Methodology (for Article Drafting)

*Researchers using this tool for peer-reviewed publications may adapt the following description for their "Methods" section:*

> "We employed a multi-agent process-relational pipeline (Rhizomatic Agent V4) to conduct a non-linear analysis of the [Topic] literature. The methodology follows a seven-phase architecture: (1) **Ontological Destabilization**, where an Epistemology Agent generates 3–5 orthogonal theoretical lenses to mitigate paradigm bias; (2) **Corpus Ingestion**, integrating metadata from OpenAlex, arXiv, and Semantic Scholar with DOI-level deduplication (Dice coefficient ≥ 0.85), CrossRef metadata enrichment, ABS-ranking evaluation, and citation influence mapping; (3) **Multi-Vocal Ingestion**, utilizing parallel LLM-based agents to analyze the corpus through each generated lens simultaneously; (4) **Resonance and Rupture Detection**, identifying cross-lens convergent anomalies and triggering heterodox re-entry when dominant frameworks enclose the analysis; (5) **Synthesis**, generating present-continuous assemblage narratives, a classified relational knowledge graph (constructive / critical / rhizomatic edges), and suggested next traversal queries; (6) **Cartographic Output**, consolidating all analytical products into a structured research cartography with aggregate token-usage transparency metadata; and (7) **Semantic Topography**, employing SciBERT embeddings with UMAP dimensionality reduction and HDBSCAN clustering to identify semantic voids, orthogonal disciplinary isolations, and marginalized literature in the current research landscape."

---

## The 15 Agents

| Agent | Phase | Theoretical Role | Technical Implementation |
|---|---|---|---|
| **Epistemology Agent** | 1 | Ontological diversification | LLM-based dynamic lens generator |
| **Entry Layer** | 2a | Entry point identification & rupture risk | LLM — five entry points, framework detection |
| **Researcher** | 2a | Empirical acquisition | OpenAlex + arXiv + Semantic Scholar APIs |
| **Deduplication Agent** | 2b | Structural integrity | DOI normalization + Trigram Dice (≥ 0.85) |
| **Metadata Enricher** | 2c | Bibliographic completeness | CrossRef + OpenAlex DOI lookup |
| **ABS Evaluator** | 2d | Institutional rigor analysis | Local JSON DB + LLM verification |
| **Citation Mapper** | 2d | Influence topology mapping | Anchor paper & citation shadow extraction |
| **Ingestion Nodes** | 3 | Multi-vocal parallel reading | N concurrent lens-specific LLM agents |
| **Resonance Detector** | 4a | Convergent anomaly detection | Cross-lens LLM synthesis |
| **Rupture Protocol** | 4b | Paradigm maintenance | Deterministic routing + heterodox expansion |
| **Assemblage Builder** | 5a | Synthesis of becoming | Present-continuous LLM synthesis |
| **Relationship Mapper** | 5a | Relational graph construction | Weighted edge graph via LLM |
| **Rhizome Builder** | 5b | Edge classification + centralization detection | LLM tripartite classifier + optional Neo4j |
| **Traversal Suggester** | 5c | Lines of flight generation | LLM-based next-query suggester |
| **Topography Engine** | 7 | Structural gap analysis | SciBERT + UMAP + HDBSCAN |

**Orchestrator**: `api/traverse.py` — SSE streaming pipeline controller

---

## Project Structure

```
Rhizomatic Model 2/
├── README.md
├── run_linux.sh                       # One-command launcher (setup + run)
├── launcher.py                        # Python entry point
│
├── backend/
│   ├── main.py                        # FastAPI app + router registration
│   ├── config.py                      # Pydantic settings
│   ├── models.py                      # Pydantic v2 schemas
│   ├── requirements.txt               # All Python dependencies
│   ├── .env                           # Local config (gitignored)
│   ├── .env.example                   # Config template
│   │
│   ├── api/
│   │   ├── traverse.py                # SSE orchestrator — 7-phase pipeline
│   │   ├── search.py                  # Triple-source search (OpenAlex + arXiv + Semantic Scholar)
│   │   ├── runs.py                    # Run history — list + retrieve past traversals
│   │   ├── projects.py                # Project workspace CRUD
│   │   ├── abs_manager.py             # ABS list upload + stats + manual flag
│   │   └── tts.py                     # Kokoro TTS endpoints
│   │
│   ├── pipeline/
│   │   ├── __init__.py                # Token tracking, prompt loader, JSON cleaner
│   │   ├── epistemology_agent.py      # Phase 1
│   │   ├── entry_layer.py             # Phase 2a
│   │   ├── deduplication_agent.py     # Phase 2b
│   │   ├── metadata_enricher.py       # Phase 2c
│   │   ├── abs_evaluator.py           # Phase 2d
│   │   ├── citation_mapper.py         # Phase 2d
│   │   ├── ingestion_nodes.py         # Phase 3
│   │   ├── resonance_detector.py      # Phase 4a
│   │   ├── rupture_protocol.py        # Phase 4b
│   │   ├── assemblage_builder.py      # Phase 5a
│   │   ├── relationship_mapper.py     # Phase 5a
│   │   ├── rhizome_builder.py         # Phase 5b
│   │   ├── traversal_suggester.py     # Phase 5c
│   │   ├── cartographic_output.py     # Phase 6
│   │   └── semantic_topography.py     # Phase 7
│   │
│   ├── models/
│   │   └── kokoro/
│   │       └── voices/                # Kokoro TTS voice files (auto-downloaded)
│   │
│   ├── prompts/
│   │   ├── epistemology_agent.txt
│   │   ├── citation_analyzer.txt
│   │   ├── abs_evaluator.txt
│   │   ├── assemblage_builder.txt
│   │   ├── ingestion_template.txt
│   │   ├── master_system_prompt.txt
│   │   ├── relationship_mapper.txt
│   │   └── resonance_detector.txt
│   │
│   ├── database/
│   │   ├── neo4j_client.py
│   │   └── abs_store.py
│   │
│   └── data/
│       ├── abs_journals.json
│       └── runs.json                  # Run history (auto-created)
│
└── frontend/
    ├── index.html                     # 7-tab dark-glass UI + TTS bar
    ├── app.js                         # D3.js graph + SSE consumer + Kokoro TTS
    └── style.css                      # Glassmorphism dark UI
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/traverse` | Run pipeline — SSE stream |
| `GET` | `/api/health` | Health check + feature flags |
| `GET` | `/api/runs` | List all past runs (newest first) |
| `GET` | `/api/runs/{run_id}` | Retrieve full tab data for a run |
| `GET` | `/api/projects` | List project workspaces |
| `POST` | `/api/projects` | Create project |
| `PUT` | `/api/projects/{id}` | Update project |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `POST` | `/api/abs/upload` | Upload ABS journal CSV |
| `GET` | `/api/abs/stats` | ABS database statistics |
| `POST` | `/api/abs/flag` | Manually flag a journal |
| `POST` | `/api/tts/speak` | Generate speech — returns WAV audio |
| `GET` | `/api/tts/voices` | List available Kokoro voices |

### SSE Stream Events

Each event: `{"stage": "...", "status": "running"|"complete"|"error", "data": {...}}`

Stages in order:
```
epistemology → search → entry → metadata_enrichment →
abs_check → citations → modules → resonance → rupture →
[rupture_search] → assemblage → graph → traversal_suggestions →
cartography → topography → done
```

---

## Building the Executable (Windows)

If you need to rebuild `RhizomaticAgent.exe` for Windows:

1. Install requirements: `pip install -r backend/requirements.txt pyinstaller`
2. Run PyInstaller:
   ```bash
   pyinstaller RhizomaticAgent.spec --clean
   ```
3. The standalone executable will be in the `dist/` directory.

Prebuilt executables are published on the repository's [Releases](https://github.com/hapuuma/RhizomaticLiteratureReview/releases) page rather than committed to git. Place `backend/.env` (copied from `backend/.env.example`) next to the `.exe` so BERT topography is enabled.

> **Note**: The EXE handles path resolution automatically, creating a `backend/data` folder in its own directory for persistent project and run history storage.

---

## Parallelism

The pipeline uses `asyncio.gather` with automatic fallback to sequential on 429/503:

| Phase | Concurrent LLM calls |
|---|---|
| Phase 2a | 2 — Researcher + Entry Layer |
| Phase 2d | 2 — ABS Evaluator + Citation Mapper |
| Phase 3 | N — all lenses simultaneously |
| Phase 5a | 2 — Assemblage Builder + Relationship Mapper |

For true Ollama concurrency:
```bash
export OLLAMA_NUM_PARALLEL=4
```

---

## Licence

All rights reserved. The code is public for review and for reproducing the reported results; any other use requires written permission. See [LICENSE](LICENSE).
