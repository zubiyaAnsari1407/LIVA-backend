"""Helpers for resolving both portfolio and LIVA project references."""

from bson import ObjectId
from fastapi import HTTPException

from database import db


def find_project(project_id: str) -> dict | None:
    """Return a saved project from either project registry by its public ID."""
    if ObjectId.is_valid(project_id):
        project = db.projects.find_one({"_id": ObjectId(project_id)})
        if project is not None:
            project = dict(project)
            project["_projectRef"] = str(project["_id"])
            project["_projectName"] = project.get("name", "")
            project["_isLivaProject"] = False
            return project

    if project_id.startswith("LIVA-PRJ-"):
        project = db["liva_projects"].find_one({"projectId": project_id})
        if project is not None:
            project = dict(project)
            project["_projectRef"] = project_id
            project["_projectName"] = project.get("projectName", "")
            project["_isLivaProject"] = True
            return project

    return None


def require_project(project_id: str) -> dict:
    project = find_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def project_refs(project_ids: set[str]) -> dict[str, str]:
    """Map existing public project references to their display names."""
    refs = {str(value) for value in project_ids if value}
    names: dict[str, str] = {}
    object_ids = [ObjectId(value) for value in refs if ObjectId.is_valid(value)]
    liva_ids = [value for value in refs if value.startswith("LIVA-PRJ-")]

    if object_ids:
        names.update({
            str(project["_id"]): project.get("name", "")
            for project in db.projects.find(
                {"_id": {"$in": object_ids}}, {"name": 1}
            )
        })
    if liva_ids:
        names.update({
            project["projectId"]: project.get("projectName", "")
            for project in db["liva_projects"].find(
                {"projectId": {"$in": liva_ids}},
                {"projectId": 1, "projectName": 1},
            )
        })
    return names
