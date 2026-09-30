from datetime import date, datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
)
from pymongo.errors import PyMongoError

from database import db
from project_registry import project_refs, require_project

router = APIRouter(prefix="/api/parcels", tags=["Parcels"])


class ParcelCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    projectId: str
    surveyNumber: str = Field(min_length=1, max_length=100)
    village: str = Field(min_length=1, max_length=150)
    district: str = Field(min_length=1, max_length=100)

    areaHa: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )

    ownership: Literal[
        "Pending verification",
        "Verified",
        "Disputed",
    ] = "Pending verification"

    stage: Literal[
        "Survey",
        "Verification",
        "Award",
        "Compensation",
        "Possession",
    ] = "Survey"

    isDemo: bool = True

    sourceName: str | None = Field(default=None, max_length=200)
    sourceUrl: HttpUrl | None = None
    sourceRecordId: str | None = Field(default=None, max_length=200)
    sourceDate: date | None = None

def parcel_object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid parcel ID.")
    return ObjectId(value)


def validate_project_for_parcel(payload: ParcelCreate):
    project = require_project(payload.projectId)
    project_ref = project["_projectRef"]

    if not payload.isDemo and project.get("isDemo") is True:
        raise HTTPException(
            status_code=422,
            detail="A non-demo parcel cannot be linked to a demo project.",
        )

    if not payload.isDemo and not project.get("_isLivaProject") and (
        not payload.sourceName or payload.sourceUrl is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Source-backed parcels require a source name and source URL.",
        )

    return project_ref, project


def serialize_parcel(document: dict, project_name: str) -> dict:
    return {
        "id": str(document["_id"]),
        "projectId": str(document["projectId"]),
        "project": project_name,
        "surveyNumber": document.get("surveyNumber", ""),
        "village": document.get("village", ""),
        "district": document.get("district", ""),
        "areaHa": document.get("areaHa"),
        "ownership": document.get("ownership", "Pending verification"),
        "stage": document.get("stage", "Survey"),
        "isDemo": document.get("isDemo", True),
        "sourceName": document.get("sourceName"),
        "sourceUrl": document.get("sourceUrl"),
        "sourceRecordId": document.get("sourceRecordId"),
        "sourceDate": document.get("sourceDate"),
        # Linked modules are not integrated yet.
        "compensationStatus": None,
        "linkedCases": None,
        "documentCount": None,
    }


@router.post("", status_code=201)
def create_parcel(payload: ParcelCreate):
    try:
        project_ref, project = validate_project_for_parcel(payload)

        document = payload.model_dump(mode="json")
        document["projectId"] = str(project_ref)
        document["createdAt"] = datetime.now(timezone.utc)
        document["updatedAt"] = datetime.now(timezone.utc)

        result = db.parcels.insert_one(document)
        document["_id"] = result.inserted_id

        return serialize_parcel(
            document,
            project.get("_projectName", project.get("name", "")),
        )

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again.",
        ) from None


@router.put("/{parcel_id}")
def update_parcel(parcel_id: str, payload: ParcelCreate):
    """
    Update an existing parcel.

    The frontend Edit Parcel form sends the same complete parcel payload
    used by the create form, so one validated model is used for both.
    """
    parcel_oid = parcel_object_id(parcel_id)

    try:
        existing = db.parcels.find_one({"_id": parcel_oid})

        if existing is None:
            raise HTTPException(
                status_code=404,
                detail="Parcel not found.",
            )

        project_ref, project = validate_project_for_parcel(payload)

        updated_fields = payload.model_dump(mode="json")
        updated_fields["projectId"] = str(project_ref)
        updated_fields["updatedAt"] = datetime.now(timezone.utc)

        result = db.parcels.update_one(
            {"_id": parcel_oid},
            {"$set": updated_fields},
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Parcel not found.",
            )

        document = db.parcels.find_one({"_id": parcel_oid})

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Parcel could not be loaded after update.",
            )

        return serialize_parcel(
            document,
            project.get("_projectName", project.get("name", "")),
        )

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again.",
        ) from None


@router.get("")
def list_parcels(
    projectId: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    query = {}

    if projectId is not None:
        project = require_project(projectId)
        query["projectId"] = project["_projectRef"]

    try:
        total = db.parcels.count_documents(query)

        documents = list(
            db.parcels.find(query)
            .sort("_id", -1)
            .skip(skip)
            .limit(limit)
        )

        names = project_refs({str(item.get("projectId", "")) for item in documents})

        return {
            "items": [
                serialize_parcel(
                    item,
                    names.get(str(item["projectId"]), "Project unavailable"),
                )
                for item in documents
            ],
            "count": len(documents),
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again.",
        ) from None
