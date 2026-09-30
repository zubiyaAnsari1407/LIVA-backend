from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import db
from liva_documents import (
    LivaDocumentReference,
    get_liva_document_reference,
    link_liva_document,
)
from liva_projects import projects_collection
from liva_risk_assessments import create_or_get_assessment_for_verified_grievance


router = APIRouter(
    prefix="/api/liva/grievances",
    tags=["LIVA Grievances"],
)

GrievanceStatus = Literal[
    "SUBMITTED",
    "UNDER_VERIFICATION",
    "RETURNED",
    "PROBLEM_VERIFIED",
]

OfficerWorkStatus = Literal[
    "NOT_STARTED",
    "IN_PROGRESS",
    "ON_HOLD",
    "RESOLVED",
]

GRIEVANCE_COLLECTION_NAME = "liva_grievances"
grievance_collection = db[GRIEVANCE_COLLECTION_NAME]
_indexes_ready = False


class GrievanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    applicantName: str = Field(min_length=1, max_length=150)
    mobile: str = Field(min_length=5, max_length=30)
    surveyNumber: str = Field(min_length=1, max_length=100)
    projectId: str | None = Field(default=None, max_length=100)
    village: str = Field(min_length=1, max_length=150)
    district: str = Field(min_length=1, max_length=100)
    project: str = Field(min_length=1, max_length=250)
    type: Literal[
        "land-dispute",
        "ownership",
        "compensation",
        "document",
        "boundary",
        "other",
    ]
    description: str = Field(min_length=1, max_length=5000)
    supportingDocuments: list[LivaDocumentReference] = Field(
        default_factory=list,
        max_length=3,
    )


class OfficerProjectReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    findings: str = Field(min_length=1, max_length=5000)
    rootCause: str | None = Field(default=None, max_length=3000)
    actionPlan: str = Field(min_length=1, max_length=5000)
    workStatus: OfficerWorkStatus
    ownershipIssueConfirmed: bool | None = None
    surveyPending: bool | None = None
    compensationPending: bool | None = None
    overdueDays: int | None = Field(default=None, ge=0, le=3650)


class GrievancePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: GrievanceStatus | None = None
    officerRemark: str | None = Field(default=None, max_length=5000)
    officerReport: OfficerProjectReport | None = None


class GrievanceResponse(GrievanceCreate):
    grievanceId: str
    status: GrievanceStatus
    officerRemark: str = ""
    officerReport: OfficerProjectReport | None = None
    reviewHistory: list[dict] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class GrievanceListResponse(BaseModel):
    items: list[GrievanceResponse]
    count: int
    total: int
    skip: int
    limit: int


INDEXES = (
    ("grievanceId", True),
    ("status", False),
    ("surveyNumber", False),
    ("projectId", False),
    ("createdAt", False),
)


def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return

    try:
        for field, unique in INDEXES:
            grievance_collection.create_index(
                field,
                unique=unique,
                name=(
                    "uq_liva_grievance_id"
                    if unique
                    else f"ix_liva_grievance_{field.lower()}"
                ),
            )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA grievance storage is unavailable.",
        ) from None

    _indexes_ready = True


def _next_grievance_id() -> str:
    highest_number = 0
    for record in grievance_collection.find({}, {"grievanceId": 1}):
        grievance_id = record.get("grievanceId", "")
        if isinstance(grievance_id, str) and grievance_id.startswith("GRV-"):
            suffix = grievance_id[4:]
            if suffix.isdigit():
                highest_number = max(highest_number, int(suffix))
    return f"GRV-{highest_number + 1:03d}"


def _serialize(record: dict) -> dict:
    record.pop("_id", None)
    return record


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LIVA grievance storage is unavailable.",
    )


def _resolve_project_id(payload: GrievanceCreate) -> str | None:
    """Validate an explicit project ID or resolve an exact legacy submission."""
    project_query = {
        "surveyNumber": payload.surveyNumber,
        "projectName": payload.project,
    }
    try:
        if payload.projectId:
            project = projects_collection.find_one(
                {"projectId": payload.projectId}
            )
            if project is None:
                raise HTTPException(status_code=404, detail="LIVA project not found.")
            if any(project.get(key) != value for key, value in project_query.items()):
                raise HTTPException(
                    status_code=422,
                    detail="Grievance survey and project must match the selected LIVA project.",
                )
            return payload.projectId

        # Older clients may omit projectId. Associate only an unambiguous exact
        # project match; never infer a link from village, owner, or partial text.
        matches = list(
            projects_collection.find(project_query).limit(2)
        )
    except HTTPException:
        raise
    except PyMongoError:
        raise _unavailable() from None

    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple LIVA projects match this grievance; select a project explicitly.",
        )
    return matches[0].get("projectId") if matches else None


@router.post("", response_model=GrievanceResponse, status_code=201)
def create_grievance(payload: GrievanceCreate):
    ensure_indexes()
    document = payload.model_dump(mode="python")
    document["projectId"] = _resolve_project_id(payload)

    for item in document["supportingDocuments"]:
        reference = get_liva_document_reference(
            item["fileId"],
            "grievance",
            "grievanceSupporting",
        )
        item.update(reference)

    now = datetime.now(timezone.utc)
    document.update(
        {
            "grievanceId": "",
            "status": "SUBMITTED",
            "officerRemark": "",
            "officerReport": None,
            "reviewHistory": [],
            "createdAt": now,
            "updatedAt": now,
        }
    )

    for _ in range(25):
        document["grievanceId"] = _next_grievance_id()
        try:
            grievance_collection.insert_one(document)
            for reference in document["supportingDocuments"]:
                link_liva_document(
                    reference["fileId"],
                    "grievance",
                    "grievanceSupporting",
                    document["grievanceId"],
                )
            return _serialize(document.copy())
        except DuplicateKeyError:
            continue
        except PyMongoError:
            raise _unavailable() from None

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a unique grievance ID.",
    )


@router.get("", response_model=GrievanceListResponse)
def list_grievances(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    grievance_status: GrievanceStatus | None = Query(default=None, alias="status"),
):
    ensure_indexes()
    query = {"status": grievance_status} if grievance_status else {}
    try:
        total = grievance_collection.count_documents(query)
        records = list(
            grievance_collection.find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )
    except PyMongoError:
        raise _unavailable() from None

    return {
        "items": [_serialize(record) for record in records],
        "count": len(records),
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{grievance_id}", response_model=GrievanceResponse)
def get_grievance(grievance_id: str):
    ensure_indexes()
    try:
        record = grievance_collection.find_one({"grievanceId": grievance_id})
    except PyMongoError:
        raise _unavailable() from None

    if record is None:
        raise HTTPException(status_code=404, detail="Grievance not found.")
    return _serialize(record)


@router.patch("/{grievance_id}", response_model=GrievanceResponse)
def update_grievance(grievance_id: str, payload: GrievancePatch):
    ensure_indexes()
    if not payload.model_fields_set:
        raise HTTPException(
            status_code=422,
            detail="Provide a status or officerRemark update.",
        )
    if "status" in payload.model_fields_set and payload.status is None:
        raise HTTPException(status_code=422, detail="Status cannot be null.")

    try:
        existing = grievance_collection.find_one({"grievanceId": grievance_id})
    except PyMongoError:
        raise _unavailable() from None
    if existing is None:
        raise HTTPException(status_code=404, detail="Grievance not found.")

    if (
        payload.status == "PROBLEM_VERIFIED"
        and existing["status"] == "PROBLEM_VERIFIED"
    ):
        try:
            create_or_get_assessment_for_verified_grievance(existing)
        except PyMongoError:
            raise _unavailable() from None
        return _serialize(existing)

    allowed_transitions = {
        "SUBMITTED": {"UNDER_VERIFICATION"},
        "UNDER_VERIFICATION": {"RETURNED", "PROBLEM_VERIFIED"},
        "RETURNED": {"UNDER_VERIFICATION"},
    }
    if payload.status is not None and payload.status not in allowed_transitions.get(
        existing["status"], set()
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invalid grievance status transition: {existing['status']} "
                f"to {payload.status}."
            ),
        )

    changes = payload.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)
    changes["updatedAt"] = now
    if (
        payload.officerReport is not None
        or (payload.officerRemark is not None and payload.officerRemark.strip())
        or payload.status in {"RETURNED", "PROBLEM_VERIFIED"}
    ):
        review_history = list(existing.get("reviewHistory", []))
        review_history.append({
            "status": payload.status or existing["status"],
            "officerRemark": payload.officerRemark if payload.officerRemark is not None else existing.get("officerRemark", ""),
            "officerReport": payload.officerReport.model_dump(mode="json") if payload.officerReport is not None else existing.get("officerReport"),
            "recordedAt": now,
        })
        changes["reviewHistory"] = review_history
    try:
        grievance_collection.update_one(
            {"grievanceId": grievance_id},
            {"$set": changes},
        )
        updated = grievance_collection.find_one({"grievanceId": grievance_id})
    except PyMongoError:
        raise _unavailable() from None
    if updated is None:
        raise HTTPException(status_code=404, detail="Grievance not found.")

    if updated["status"] == "PROBLEM_VERIFIED":
        create_or_get_assessment_for_verified_grievance(updated)

    return _serialize(updated)
