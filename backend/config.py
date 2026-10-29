import os
from pydantic_settings import BaseSettings
from typing import Dict, Optional
from pathlib import Path
import sys

# ── Dynamic Path Resolution ──────────────────────────────────────────────────
if hasattr(sys, '_MEIPASS'):
    # Running as PyInstaller EXE — Read-only resources
    BASE_PATH = Path(sys._MEIPASS)
else:
    # Dev mode
    BASE_PATH = Path(__file__).parent.parent.absolute()

# Directory where user config and data (like .env and projects.json) live
EXE_DIR = Path(os.environ.get("RHIZOMATIC_EXE_DIR", BASE_PATH))

class Settings(BaseSettings):
    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral-large-3:675b-cloud"
    ollama_timeout: int = 300  # seconds

    # ── OpenAlex literature search ────────────────────────────────────────────
    openalex_api_url: str = "https://api.openalex.org/works"
    openalex_results_per_page: int = 15
    openalex_email: str = "rhizomatic-agent@research.dev"

    # ── arXiv ─────────────────────────────────────────────────────────────────
    arxiv_api_url: str = "http://export.arxiv.org/api/query"
    arxiv_results_per_source: int = 8

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: Optional[str] = None
    neo4j_user: Optional[str] = None
    neo4j_password: Optional[str] = None
    neo4j_enabled: bool = False

    # ── BERT ──────────────────────────────────────────────────────────────────
    bert_model: str = "allenai/scibert_scivocab_uncased"
    bert_enabled: bool = False

    # ── ABS Journal Database — ensure data/ dir exists in EXE_DIR ──────────────
    abs_database_path: str = str(EXE_DIR / "backend" / "data" / "abs_journals.json")

    # ── Projects — writable ────────────────────────────────────────────────────
    projects_data_path: str = str(EXE_DIR / "backend" / "data" / "projects.json")

    # ── Run History — writable ─────────────────────────────────────────────────
    runs_data_path: str = str(EXE_DIR / "backend" / "data" / "runs.json")

    # ── Epistemology Agent ────────────────────────────────────────────────────
    num_dynamic_lenses: int = 4

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: list = ["*"]

    class Config:
        # Prioritize .env in the same folder as the .exe
        env_file = str(EXE_DIR / "backend" / ".env")
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure writable data directory exists near the EXE if not in BASE_PATH
DATA_DIR = EXE_DIR / "backend" / "data"
if not DATA_DIR.exists():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except:
        pass

# ─── Static Fallback Module Definitions ─────────────────────────────────────
# These are used when the Epistemology Agent is disabled or as fallback.
# In V3, the Epistemology Agent dynamically generates lenses per-project.

MODULES: Dict[str, Dict[str, str]] = {
    "Innovation Commons": {
        "name": "Innovation Commons",
        "target": (
            "Track the emergence of new organizational forms, commons, "
            "cooperatives, and peer-to-peer networks within the phenomenon zone. "
            "Identify how innovation knowledge is being coordinated, enclosed, or "
            "liberated across open-source projects, collective action, and platform "
            "cooperativism. Map who controls the knowledge and who is excluded from it."
        ),
    },
    "Complexity & Assemblage": {
        "name": "Complexity & Assemblage",
        "target": (
            "Track self-organizing dynamics, emergent patterns, and non-human "
            "agency across scales (micro, meso, macro). Detect where adaptive "
            "systems theory, complex adaptive systems, or assemblage thinking "
            "intersects with the phenomenon zone. Identify rupture "
            "points and moments of systemic bifurcation."
        ),
    },
    "Material & Infrastructural Flows": {
        "name": "Material & Infrastructural Flows",
        "target": (
            "Track how material systems, infrastructures, and technologies are "
            "reconfiguring information, power, and resource flows across the "
            "phenomenon zone. Identify entanglements between data infrastructure, "
            "algorithmic governance, physical systems, and political economy. "
            "Pay attention to how infrastructural asymmetries shape access and agency."
        ),
    },
}
