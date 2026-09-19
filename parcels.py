from datetime import date, datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)
from pymongo.errors import PyMongoError

from database import db

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

    @model_validator(mode="after")
    def validate_source(self):
        if not self.isDemo and (
            not self.sourceName or self.sourceUrl is None
        ):
            raise ValueError(
                "Non-demo records require a source name and source URL."
            )
        return self


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid project ID.")
    return ObjectId(value)


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
    project_oid = object_id(payload.projectId)

    try:
        project = db.projects.find_one({"_id": project_oid})

        if project is None:
            raise HTTPException(
                status_code=404,
                detail="Project not found. Create the project first.",
            )

        if not payload.isDemo and project.get("isDemo", True):
            raise HTTPException(
                status_code=422,
                detail="A non-demo parcel cannot be linked to a demo project.",
            )

        document = payload.model_dump(mode="json")
        document["projectId"] = str(project_oid)
        document["createdAt"] = datetime.now(timezone.utc)

        result = db.parcels.insert_one(document)
        document["_id"] = result.inserted_id

        return serialize_parcel(document, project.get("name", ""))

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
        query["projectId"] = str(object_id(projectId))

    try:
        total = db.parcels.count_documents(query)

        documents = list(
            db.parcels.find(query)
            .sort("_id", -1)
            .skip(skip)
            .limit(limit)
        )

        project_ids = {
            ObjectId(item["projectId"])
            for item in documents
            if ObjectId.is_valid(str(item.get("projectId", "")))
        }

        names = {
            str(item["_id"]): item.get("name", "")
            for item in db.projects.find(
                {"_id": {"$in": list(project_ids)}},
                {"name": 1},
            )
        }

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