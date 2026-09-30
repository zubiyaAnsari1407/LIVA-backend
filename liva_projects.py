from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import db


router = APIRouter(prefix="/api/liva/projects", tags=["LIVA Projects"])
projects_collection = db["liva_projects"]
_indexes_ready = False


class LivaProjectResponse(BaseModel):
    projectId: str
    projectName: str
    surveyNumber: str
    ownerName: str
    village: str
    district: str
    state: str
    pincode: str
    area: str
    sourceRegistrationRequestId: str
    createdAt: datetime
    updatedAt: datetime
    status: str
    isDemo: bool | None = None
    progress: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    locationDisplayName: str | None = None
    locationSource: str | None = None


class LivaProjectUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    projectName: str | None = Field(default=None, min_length=3, max_length=250)
    surveyNumber: str | None = Field(default=None, min_length=1, max_length=100)
    ownerName: str | None = Field(default=None, min_length=2, max_length=150)
    village: str | None = Field(default=None, min_length=2, max_length=150)
    district: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    area: str | None = Field(default=None, min_length=1, max_length=80)
    status: str | None = Field(default=None, min_length=2, max_length=40)
    progress: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    locationDisplayName: str | None = Field(default=None, max_length=250)
    locationSource: str | None = Field(default=None, max_length=80)


def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return

    try:
        projects_collection.create_index(
            "projectId",
            unique=True,
            name="uq_liva_project_id",
        )
        projects_collection.create_index(
            "sourceRegistrationRequestId",
            unique=True,
            name="uq_liva_project_registration_request",
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project storage is unavailable.",
        ) from None

    _indexes_ready = True


def _serialize(project: dict) -> dict:
    project.pop("_id", None)
    return project


def create_or_get_project_from_registration(request: dict) -> dict:
    ensure_indexes()
    request_id = request["requestId"]

    try:
        existing = projects_collection.find_one(
            {"sourceRegistrationRequestId": request_id}
        )
        if existing is not None:
            return _serialize(existing)

        suffix = request_id.removeprefix("REQ-")
        if not suffix.isdigit():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration request ID cannot be used for project ID generation.",
            )

        # Project-list demo records can already occupy IDs that match request
        # numbers (for example REQ-006 and LIVA-PRJ-006). Keep the familiar
        # sequence where available, then allocate the next free ID.
        candidate = int(suffix)
        while True:
            project_id = f"LIVA-PRJ-{candidate:03d}"
            if projects_collection.find_one({"projectId": project_id}) is not None:
                candidate += 1
                continue

            now = datetime.now(timezone.utc)
            project = {
                "projectId": project_id,
                "projectName": (
                    f"{request['village']} {request['surveyNumber']} "
                    "Land Acquisition Project"
                ),
                "surveyNumber": request["surveyNumber"],
                "ownerName": request["ownerName"],
                "village": request["village"],
                "district": request["district"],
                "state": request["state"],
                "pincode": request["pincode"],
                "area": request["area"],
                "sourceRegistrationRequestId": request_id,
                "createdAt": now,
                "updatedAt": now,
                "status": "ACTIVE",
            }

            try:
                projects_collection.insert_one(project)
                return project
            except DuplicateKeyError:
                # A concurrent approval may have created this request's
                # project, or occupied this candidate ID after our lookup.
                existing = projects_collection.find_one(
                    {"sourceRegistrationRequestId": request_id}
                )
                if existing is not None:
                    return _serialize(existing)
                candidate += 1
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project storage is unavailable.",
        ) from None


@router.get("", response_model=list[LivaProjectResponse])
def list_liva_projects():
    ensure_indexes()
    try:
        projects = list(
            projects_collection.find().sort("createdAt", -1).limit(500)
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project storage is unavailable.",
        ) from None

    return [_serialize(project) for project in projects]


@router.get("/{project_id}", response_model=LivaProjectResponse)
def get_liva_project(project_id: str):
    ensure_indexes()
    try:
        project = projects_collection.find_one({"projectId": project_id})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project storage is unavailable.",
        ) from None

    if project is None:
        raise HTTPException(status_code=404, detail="LIVA project not found.")
    return _serialize(project)


@router.patch("/{project_id}", response_model=LivaProjectResponse)
def update_liva_project(project_id: str, payload: LivaProjectUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No project changes supplied.")

    try:
        result = projects_collection.update_one(
            {"projectId": project_id},
            {"$set": {**changes, "updatedAt": datetime.now(timezone.utc)}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="LIVA project not found.")
        project = projects_collection.find_one({"projectId": project_id})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project storage is unavailable.",
        ) from None

    if project is None:
        raise HTTPException(status_code=404, detail="LIVA project not found.")
    return _serialize(project)


@router.delete("/{project_id}")
def delete_liva_project(
    project_id: str,
    role: str = Header("landowner", alias="X-Liva-Role"),
):
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")

    try:
        project = projects_collection.find_one({"projectId": project_id})
        if project is None:
            raise HTTPException(status_code=404, detail="LIVA project not found.")

        source_request_id = project.get("sourceRegistrationRequestId")
        request_filter = {"livaProjectId": project_id}
        if source_request_id:
            request_filter = {"$or": [
                {"livaProjectId": project_id},
                {"requestId": source_request_id},
            ]}
        requests = list(db["liva_registration_requests"].find(request_filter))
        request_ids = [item.get("requestId") for item in requests if item.get("requestId")]
        grievances = list(db["liva_grievances"].find({"projectId": project_id}))
        grievance_ids = [item.get("grievanceId") for item in grievances if item.get("grievanceId")]

        related_file_query = [{"metadata.projectId": project_id}]
        linked_record_ids = [*request_ids, *grievance_ids]
        if linked_record_ids:
            related_file_query.append({"metadata.recordId": {"$in": linked_record_ids}})
        file_records = db["document_files.files"]
        file_chunks = db["document_files.chunks"]
        file_records_to_delete = list(file_records.find({"$or": related_file_query}, {"_id": 1}))
        file_ids = {item["_id"] for item in file_records_to_delete}

        for request in requests:
            for key in ("ownershipProof", "landRecord", "identityProof"):
                reference = request.get(key)
                if isinstance(reference, dict) and ObjectId.is_valid(str(reference.get("fileId", ""))):
                    file_ids.add(ObjectId(str(reference["fileId"])))
        for grievance in grievances:
            for reference in grievance.get("supportingDocuments", []):
                if isinstance(reference, dict) and ObjectId.is_valid(str(reference.get("fileId", ""))):
                    file_ids.add(ObjectId(str(reference["fileId"])))

        if file_ids:
            file_chunks.delete_many({"files_id": {"$in": list(file_ids)}})
            file_records.delete_many({"_id": {"$in": list(file_ids)}})

        relation_filter = {"$or": [
            {"projectId": project_id},
            {"project_id": project_id},
        ]}
        excluded = {
            "liva_projects",
            "liva_registration_requests",
            "liva_grievances",
            "document_files.files",
            "document_files.chunks",
        }
        deleted_related = {}
        for collection_name in db.list_collection_names():
            if collection_name in excluded or collection_name.startswith("system."):
                continue
            result = db[collection_name].delete_many(relation_filter)
            if result.deleted_count:
                deleted_related[collection_name] = result.deleted_count

        if requests:
            db["liva_registration_requests"].delete_many({"requestId": {"$in": request_ids}})
        if grievances:
            db["liva_grievances"].delete_many({"grievanceId": {"$in": grievance_ids}})
        result = projects_collection.delete_one({"projectId": project_id})
        if result.deleted_count != 1:
            raise HTTPException(status_code=404, detail="LIVA project not found.")

        return {
            "deleted": True,
            "projectId": project_id,
            "projectName": project.get("projectName", ""),
            "linkedRequestsDeleted": len(requests),
            "linkedGrievancesDeleted": len(grievances),
            "linkedFilesDeleted": len(file_ids),
            "relatedRecordsDeleted": deleted_related,
        }
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA project and linked record deletion failed.",
        ) from None
