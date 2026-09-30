import logging
from datetime import date, datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from database import db

router = APIRouter(prefix="/api/litigation", tags=["Litigation"])
logger = logging.getLogger("uvicorn.error")


class CaseInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    projectId: str
    parcelId: str | None = None

    title: str = Field(min_length=3, max_length=200)
    caseType: Literal[
        "Land acquisition dispute",
        "Compensation dispute",
        "Ownership dispute",
        "Title clarification",
        "Stay / injunction",
        "Other",
    ] = "Land acquisition dispute"

    reference: str = Field(min_length=2, max_length=100)
    court: str = Field(min_length=2, max_length=200)

    status: Literal[
        "Pending",
        "Disposed",
        "Status under verification",
    ] = "Status under verification"

    filedOn: date | None = None
    nextHearing: date | None = None
    officer: str = Field(default="", max_length=150)
    notes: str = Field(default="", max_length=5000)

    isDemo: bool = True
    sourceName: str | None = Field(default=None, max_length=200)
    sourceUrl: HttpUrl | None = None
    sourceRecordId: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_record(self):
        if not self.isDemo and (
            not self.sourceName or self.sourceUrl is None
        ):
            raise ValueError(
                "Non-demo cases require a source name and URL."
            )

        if (
            self.filedOn
            and self.nextHearing
            and self.nextHearing < self.filedOn
        ):
            raise ValueError(
                "Next hearing cannot be before the filing date."
            )

        if self.status == "Disposed" and self.nextHearing:
            raise ValueError(
                "Clear the next hearing date for a disposed case."
            )

        return self


def object_id(value: str, label: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, f"Invalid {label} ID.")

    return ObjectId(value)


def validate_links(payload: CaseInput) -> dict:
    project_oid = object_id(payload.projectId, "project")
    project = db.projects.find_one({"_id": project_oid})

    if project is None:
        raise HTTPException(404, "Project not found.")

    if not payload.isDemo and project.get("isDemo", True):
        raise HTTPException(
            422, "A non-demo case cannot be linked to a demo project."
        )

    document = payload.model_dump(mode="json")
    document["projectId"] = str(project_oid)

    if payload.parcelId:
        parcel_oid = object_id(payload.parcelId, "parcel")
        parcel = db.parcels.find_one({"_id": parcel_oid})

        if parcel is None:
            raise HTTPException(404, "Parcel not found.")

        if str(parcel.get("projectId")) != str(project_oid):
            raise HTTPException(
                422, "The selected parcel belongs to another project."
            )

        if not payload.isDemo and parcel.get("isDemo", True):
            raise HTTPException(
                422, "A non-demo case cannot be linked to a demo parcel."
            )

        document["parcelId"] = str(parcel_oid)
    else:
        document["parcelId"] = None

    return document


def serialize(document: dict, projects: dict) -> dict:
    project_id = str(document.get("projectId", ""))

    fields = [
        "title",
        "caseType",
        "reference",
        "court",
        "status",
        "filedOn",
        "nextHearing",
        "officer",
        "notes",
        "sourceName",
        "sourceUrl",
        "sourceRecordId",
        "createdAt",
        "updatedAt",
    ]

    return {
        "id": str(document["_id"]),
        "projectId": project_id,
        "project": projects.get(project_id, "Project unavailable"),
        "parcelId": (
            str(document["parcelId"])
            if document.get("parcelId")
            else None
        ),
        "isDemo": document.get("isDemo", True),
        **{field: document.get(field) for field in fields},
    }


def project_names(documents: list[dict]) -> dict:
    ids = {
        str(item.get("projectId", ""))
        for item in documents
    }

    valid_ids = [
        ObjectId(value)
        for value in ids
        if ObjectId.is_valid(value)
    ]

    return {
        str(project["_id"]): project.get("name", "")
        for project in db.projects.find(
            {"_id": {"$in": valid_ids}},
            {"name": 1},
        )
    }


def database_error():
    logger.exception("Litigation database operation failed")
    return HTTPException(
        503,
        "Case operation failed. Check the backend terminal.",
    )


@router.get("")
def list_cases():
    try:
        documents = list(
            db.litigation.find().sort("_id", -1).limit(100)
        )
        names = project_names(documents)

        return {
            "items": [serialize(item, names) for item in documents],
            "count": len(documents),
            "total": db.litigation.count_documents({}),
        }
    except PyMongoError:
        raise database_error() from None


@router.get("/{case_id}")
def get_case(case_id: str):
    oid = object_id(case_id, "case")

    try:
        document = db.litigation.find_one({"_id": oid})

        if document is None:
            raise HTTPException(404, "Case not found.")

        return serialize(document, project_names([document]))
    except PyMongoError:
        raise database_error() from None


@router.post("", status_code=201)
def create_case(payload: CaseInput):
    try:
        document = validate_links(payload)
        now = datetime.now(timezone.utc)
        document["createdAt"] = now
        document["updatedAt"] = now

        names = project_names([document])
        result = db.litigation.insert_one(document)
        document["_id"] = result.inserted_id

        return serialize(document, names)
    except PyMongoError:
        raise database_error() from None


@router.put("/{case_id}")
def update_case(case_id: str, payload: CaseInput):
    oid = object_id(case_id, "case")

    try:
        if db.litigation.find_one({"_id": oid}, {"_id": 1}) is None:
            raise HTTPException(404, "Case not found.")

        changes = validate_links(payload)
        changes["updatedAt"] = datetime.now(timezone.utc)
        names = project_names([changes])

        document = db.litigation.find_one_and_update(
            {"_id": oid},
            {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )

        if document is None:
            raise HTTPException(404, "Case not found.")

        return serialize(document, names)
    except PyMongoError:
        raise database_error() from None
