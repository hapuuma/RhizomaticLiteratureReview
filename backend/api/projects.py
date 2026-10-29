"""
V3: Projects API — Isolated Research Workspaces
CRUD endpoints for managing research projects.
Projects provide workspace isolation per the V3 spec.

GET    /api/projects          — list all projects
POST   /api/projects          — create new project
GET    /api/projects/{id}     — get project by ID
PUT    /api/projects/{id}     — update project config
DELETE /api/projects/{id}     — delete project
"""
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from models import Project, ProjectConfig
from config import settings
from pipeline import logger


router = APIRouter()


# ─── Storage Helpers ──────────────────────────────────────────────────────────

def _load_projects() -> dict[str, Project]:
    path = Path(settings.projects_data_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {pid: Project(**p) for pid, p in data.items()}
    except Exception as exc:
        logger.error(f"Projects load error: {exc}")
        return {}


def _save_projects(projects: dict[str, Project]) -> None:
    path = Path(settings.projects_data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {pid: p.model_dump() for pid, p in projects.items()},
            f,
            ensure_ascii=False,
            indent=2,
        )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects():
    projects = _load_projects()
    return {"projects": [p.model_dump() for p in projects.values()]}


@router.post("/projects", status_code=201)
async def create_project(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")

    projects = _load_projects()
    project_id = str(uuid.uuid4())[:8]
    project = Project(
        id=project_id,
        name=name,
        description=body.get("description"),
        config=ProjectConfig(**(body.get("config") or {})),
    )
    projects[project_id] = project
    _save_projects(projects)
    return project.model_dump()


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    projects = _load_projects()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project.model_dump()


@router.put("/projects/{project_id}")
async def update_project(project_id: str, body: dict):
    projects = _load_projects()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    if "name" in body:
        project.name = body["name"]
    if "description" in body:
        project.description = body["description"]
    if "config" in body:
        project.config = ProjectConfig(**(body["config"]))

    projects[project_id] = project
    _save_projects(projects)
    return project.model_dump()


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found.")
    del projects[project_id]
    _save_projects(projects)
    return {"deleted": project_id}
