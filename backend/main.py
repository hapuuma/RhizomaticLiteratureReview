import sys
import logging
from pathlib import Path

# ── PyInstaller Path Fix ──────────────────────────────────────────────────────
if hasattr(sys, '_MEIPASS'):
    sys.path.append(sys._MEIPASS)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import settings
from api.traverse import router as traverse_router
from api.projects import router as projects_router
from api.abs_manager import router as abs_router
from api.tts import router as tts_router
from api.lenses import router as lenses_router
from api.runs import router as runs_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("rhizomatic")

app = FastAPI(
    title="Rhizomatic Research Agent",
    description="A process-relational research pipeline for traversing any phenomenon zone.",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(traverse_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(abs_router, prefix="/api")
app.include_router(tts_router, prefix="/api")
app.include_router(lenses_router, prefix="/api")
app.include_router(runs_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {
        "status": "alive",
        "model": settings.ollama_model,
        "ollama_url": settings.ollama_base_url,
        "neo4j_enabled": settings.neo4j_enabled,
        "bert_enabled": settings.bert_enabled,
        "version": "3.0.0",
    }


# ── Serve Frontend ────────────────────────────────────────────
def get_frontend_dir():
    import sys
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / "frontend"
    return Path(__file__).parent.parent / "frontend"

FRONTEND_DIR = get_frontend_dir()

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

# ── Browser Auto-Open ─────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """Open browser on startup, but only once and not in reload workers."""
    import os
    import webbrowser
    import asyncio

    # V3: Initialize Neo4j schema if enabled
    if settings.neo4j_enabled and settings.neo4j_uri:
        try:
            from database.neo4j_client import ensure_schema
            ensure_schema()
        except Exception as e:
            logger.warning(f"Neo4j schema init skipped: {e}")

    # Only open if enabled and not already opened in this session
    if os.environ.get("OPEN_BROWSER", "true").lower() == "true":
        if os.environ.get("RHIZOMATIC_BROWSER_OPENED") is None:
            os.environ["RHIZOMATIC_BROWSER_OPENED"] = "1"

            # Small delay to ensure server is actually listening
            async def open_delayed():
                await asyncio.sleep(2.0)
                url = "http://localhost:8000"
                print(f"[*] Opening browser to {url}...")
                webbrowser.open(url)

            asyncio.create_task(open_delayed())

# ── Dev entrypoint ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import multiprocessing

    # Crucial for PyInstaller + multiprocessing
    multiprocessing.freeze_support()

    print("[*] Starting Rhizomatic Research Agent...")
    # For EXE/Bundle, never reload. For dev, only reload if explicitly asked or via CLI.
    # We disable reload here to prevent the infinite recursion reported.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
