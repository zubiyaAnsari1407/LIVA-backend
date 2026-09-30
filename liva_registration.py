from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import db
from liva_documents import (
    DocumentType,
    LivaDocumentReference,
    get_liva_document_reference,
    link_liva_document,
)
from liva_projects import create_or_get_project_from_registration


router = APIRouter(
    prefix="/api/liva/registration-requests",
    tags=["LIVA Registration Requests"],
)


RegistrationStatus = Literal[
    "SUBMITTED",
    "UNDER_VERIFICATION",
    "RETURNED",
    "OFFICER_VERIFIED",
    "APPROVED",
    "REJECTED",
]

RegistrationDocumentKey = Literal[
    "ownershipProof",
    "landRecord",
    "identityProof",
]

REQUEST_COLLECTION_NAME = "liva_registration_requests"
request_collection = db[REQUEST_COLLECTION_NAME]

_indexes_ready = False

INDEXES = (
    ("requestId", True),
    ("status", False),
    ("surveyNumber", False),
    ("createdAt", False),
    ("updatedAt", False),
)


class RegistrationRequestCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    surveyNumber: str = Field(min_length=1, max_length=100)
    ownerName: str = Field(min_length=1, max_length=150)
    village: str = Field(min_length=1, max_length=150)
    district: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    pincode: str = Field(pattern=r"^\d{6}$")
    area: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=5000)

    ownershipProof: LivaDocumentReference | None = None
    landRecord: LivaDocumentReference | None = None
    identityProof: LivaDocumentReference | None = None


class RegistrationRequestPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: RegistrationStatus | None = None
    officerRemark: str | None = Field(default=None, max_length=5000)

    # Landowners may correct the existing request after it has been
    # returned. These fields are only writable with RETURNED ->
    # UNDER_VERIFICATION below.
    surveyNumber: str | None = Field(default=None, min_length=1, max_length=100)
    ownerName: str | None = Field(default=None, min_length=1, max_length=150)
    village: str | None = Field(default=None, min_length=1, max_length=150)
    district: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    area: str | None = Field(default=None, min_length=1, max_length=100)
    reason: str | None = Field(default=None, min_length=1, max_length=5000)

    documentVerification: (
        dict[RegistrationDocumentKey, bool] | None
    ) = None

    ownershipProof: LivaDocumentReference | None = None
    landRecord: LivaDocumentReference | None = None
    identityProof: LivaDocumentReference | None = None


class AdminDecisionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    decision: Literal["APPROVE", "REJECT"]
    adminRemark: str = Field(
        default="",
        max_length=5000,
    )


class RegistrationRequestResponse(
    RegistrationRequestCreate
):
    requestId: str
    status: RegistrationStatus

    documentVerification: dict[
        RegistrationDocumentKey,
        bool,
    ]

    officerRemark: str = ""
    adminRemark: str = ""
    reviewHistory: list[dict] = Field(default_factory=list)

    livaProjectId: str | None = None

    createdAt: datetime
    updatedAt: datetime


class RegistrationRequestListResponse(BaseModel):
    items: list[RegistrationRequestResponse]
    count: int
    total: int
    skip: int
    limit: int


def ensure_indexes() -> None:
    global _indexes_ready

    if _indexes_ready:
        return

    try:
        for field, unique in INDEXES:
            request_collection.create_index(
                field,
                unique=unique,
                name=(
                    "uq_liva_registration_request_id"
                    if unique
                    else f"ix_liva_registration_{field.lower()}"
                ),
            )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA registration storage is unavailable.",
        ) from None

    _indexes_ready = True


def _next_request_id() -> str:
    highest_number = 0

    for record in request_collection.find(
        {},
        {"requestId": 1},
    ):
        request_id = record.get("requestId", "")

        if (
            not isinstance(request_id, str)
            or not request_id.startswith("REQ-")
        ):
            continue

        suffix = request_id[4:]

        if suffix.isdigit():
            highest_number = max(
                highest_number,
                int(suffix),
            )

    return f"REQ-{highest_number + 1:03d}"


def _serialize(record: dict) -> dict:
    record.pop("_id", None)
    return record


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LIVA registration storage is unavailable.",
    )


@router.post(
    "",
    response_model=RegistrationRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_registration_request(
    payload: RegistrationRequestCreate,
):
    ensure_indexes()

    now = datetime.now(timezone.utc)

    document = payload.model_dump(mode="json")

    document_types: dict[str, DocumentType] = {
        "ownershipProof": "ownershipProof",
        "landRecord": "landRecord",
        "identityProof": "identityProof",
    }

    for field, document_type in document_types.items():
        reference = getattr(payload, field)

        if reference is not None:
            document[field] = get_liva_document_reference(
                reference.fileId,
                "registration",
                document_type,
            )

    document.update(
        {
            "requestId": "",
            "status": "SUBMITTED",
            "documentVerification": {
                "ownershipProof": False,
                "landRecord": False,
                "identityProof": False,
            },
            "officerRemark": "",
            "adminRemark": "",
            "reviewHistory": [],
            "createdAt": now,
            "updatedAt": now,
        }
    )

    for _ in range(25):
        document["requestId"] = _next_request_id()

        try:
            request_collection.insert_one(document)

            for field, document_type in document_types.items():
                reference = document.get(field)

                if reference is not None:
                    link_liva_document(
                        reference["fileId"],
                        "registration",
                        document_type,
                        document["requestId"],
                    )

            return _serialize(document.copy())

        except DuplicateKeyError:
            continue

        except PyMongoError:
            raise _database_unavailable() from None

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a unique registration request ID.",
    )


@router.get(
    "",
    response_model=RegistrationRequestListResponse,
)
def list_registration_requests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    request_status: RegistrationStatus | None = Query(
        default=None,
        alias="status",
    ),
):
    ensure_indexes()

    query = (
        {"status": request_status}
        if request_status
        else {}
    )

    try:
        total = request_collection.count_documents(query)

        records = list(
            request_collection.find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )

    except PyMongoError:
        raise _database_unavailable() from None

    return {
        "items": [
            _serialize(record)
            for record in records
        ],
        "count": len(records),
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{request_id}",
    response_model=RegistrationRequestResponse,
)
def get_registration_request(
    request_id: str,
):
    ensure_indexes()

    try:
        record = request_collection.find_one(
            {"requestId": request_id}
        )

    except PyMongoError:
        raise _database_unavailable() from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found.",
        )

    return _serialize(record)


@router.patch(
    "/{request_id}",
    response_model=RegistrationRequestResponse,
)
def update_registration_request(
    request_id: str,
    payload: RegistrationRequestPatch,
):
    ensure_indexes()

    if not payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a status, officerRemark, or returned-request correction.",
        )

    if (
        "status" in payload.model_fields_set
        and payload.status is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status cannot be null.",
        )

    # Admin decisions must use the separate endpoint.
    if payload.status in {"APPROVED", "REJECTED"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Admin status changes are not available "
                "on this endpoint."
            ),
        )

    try:
        existing = request_collection.find_one(
            {"requestId": request_id}
        )

    except PyMongoError:
        raise _database_unavailable() from None

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found.",
        )

    correction_fields = {
        "surveyNumber",
        "ownerName",
        "village",
        "district",
        "state",
        "pincode",
        "area",
        "reason",
        "ownershipProof",
        "landRecord",
        "identityProof",
    }
    submitted_corrections = correction_fields.intersection(
        payload.model_fields_set
    )
    if submitted_corrections and not (
        existing.get("status") in {"RETURNED", "REJECTED"}
        and payload.status == "UNDER_VERIFICATION"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Registration details can only be corrected while "
                "resubmitting a returned or rejected request for verification."
            ),
        )

    is_correction_resubmission = (
        existing.get("status") in {"RETURNED", "REJECTED"}
        and payload.status == "UNDER_VERIFICATION"
    )
    if is_correction_resubmission and not submitted_corrections:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Corrected registration fields or documents are required to resubmit this request.",
        )

    if payload.status is not None:

        # IMPORTANT:
        # RETURNED can now go back to UNDER_VERIFICATION.
        #
        # This supports:
        #
        # Officer Return
        #       ↓
        # Landowner Correction
        #       ↓
        # Resubmit
        #       ↓
        # Officer Verification
        #
        allowed_transitions = {
            "SUBMITTED": {
                "UNDER_VERIFICATION",
            },

            "UNDER_VERIFICATION": {
                "RETURNED",
                "OFFICER_VERIFIED",
            },

            "RETURNED": {
                "UNDER_VERIFICATION",
            },

            "REJECTED": {
                "UNDER_VERIFICATION",
            },
        }

        allowed_targets = allowed_transitions.get(
            existing["status"],
            set(),
        )

        if payload.status not in allowed_targets:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid status transition: "
                    f"{existing['status']} "
                    f"to {payload.status}."
                ),
            )

        document_verification = {
            **existing.get(
                "documentVerification",
                {
                    "ownershipProof": False,
                    "landRecord": False,
                    "identityProof": False,
                },
            ),
            **(
                payload.documentVerification
                or {}
            ),
        }

        # Officer can only verify after
        # all 3 registration documents
        # are individually verified.
        if (
            payload.status == "OFFICER_VERIFIED"
            and not all(
                document_verification.get(
                    key,
                    False,
                )
                for key in (
                    "ownershipProof",
                    "landRecord",
                    "identityProof",
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Verify each required registration "
                    "document before verifying the request."
                ),
            )

    changes = payload.model_dump(
        mode="json",
        exclude_unset=True
    )

    if is_correction_resubmission:
        # Keep the previous review cycle and its remarks on the same request.
        # The active remark fields are then cleared so new review remarks are
        # not confused with comments from the completed cycle.
        review_history = list(existing.get("reviewHistory", []))
        review_history.append(
            {
                "status": existing["status"],
                "officerRemark": existing.get("officerRemark", ""),
                "adminRemark": existing.get("adminRemark", ""),
                "recordedAt": datetime.now(timezone.utc),
            }
        )
        changes["reviewHistory"] = review_history
        changes["officerRemark"] = ""
        changes["adminRemark"] = ""

    document_types: dict[str, DocumentType] = {
        "ownershipProof": "ownershipProof",
        "landRecord": "landRecord",
        "identityProof": "identityProof",
    }
    replacement_documents: list[tuple[str, DocumentType, str]] = []
    for field, document_type in document_types.items():
        if field not in submitted_corrections:
            continue

        reference = getattr(payload, field)
        if reference is None:
            changes[field] = None
            continue

        canonical_reference = get_liva_document_reference(
            reference.fileId,
            "registration",
            document_type,
        )
        changes[field] = canonical_reference
        previous_reference = existing.get(field) or {}
        if previous_reference.get("fileId") != reference.fileId:
            replacement_documents.append(
                (reference.fileId, document_type, field)
            )

    changes["updatedAt"] = datetime.now(
        timezone.utc
    )

    # Nested documentVerification update.
    if is_correction_resubmission:
        # Any changed/replaced documents need fresh officer verification.
        changes.pop("documentVerification", None)
        for key in (
            "ownershipProof",
            "landRecord",
            "identityProof",
        ):
            changes[f"documentVerification.{key}"] = False
    elif payload.documentVerification is not None:

        changes.pop(
            "documentVerification",
            None,
        )

        for key, verified in (
            payload.documentVerification.items()
        ):
            changes[
                f"documentVerification.{key}"
            ] = verified

    try:
        request_collection.update_one(
            {"requestId": request_id},
            {"$set": changes},
        )

        updated = request_collection.find_one(
            {"requestId": request_id}
        )

    except PyMongoError:
        raise _database_unavailable() from None

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found.",
        )

    for file_id, document_type, _field in replacement_documents:
        link_liva_document(
            file_id,
            "registration",
            document_type,
            request_id,
        )

    return _serialize(updated)


@router.patch(
    "/{request_id}/admin-decision",
    response_model=RegistrationRequestResponse,
)
def decide_registration_request(
    request_id: str,
    payload: AdminDecisionRequest,
):
    ensure_indexes()

    try:
        existing = request_collection.find_one(
            {"requestId": request_id}
        )

    except PyMongoError:
        raise _database_unavailable() from None

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found.",
        )

    target_status = (
        "APPROVED"
        if payload.decision == "APPROVE"
        else "REJECTED"
    )

    # Idempotent approval.
    if existing["status"] == target_status:

        if payload.decision == "APPROVE":
            project = (
                create_or_get_project_from_registration(
                    existing
                )
            )

            existing["livaProjectId"] = (
                project["projectId"]
            )

        return _serialize(existing)

    # Only Officer-verified requests can
    # reach Admin decision.
    if existing["status"] != "OFFICER_VERIFIED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only Officer-verified requests "
                "can receive an Admin decision."
            ),
        )

    project = None

    if payload.decision == "APPROVE":
        project = (
            create_or_get_project_from_registration(
                existing
            )
        )

    changes = {
        "status": target_status,
        "adminRemark": payload.adminRemark,
        "updatedAt": datetime.now(timezone.utc),
    }

    if project is not None:
        changes["livaProjectId"] = (
            project["projectId"]
        )

    try:
        request_collection.update_one(
            {"requestId": request_id},
            {"$set": changes},
        )

        updated = request_collection.find_one(
            {"requestId": request_id}
        )

    except PyMongoError:
        raise _database_unavailable() from None

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration request not found.",
        )

    return _serialize(updated)
