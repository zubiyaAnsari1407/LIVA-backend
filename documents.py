from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from gridfs import GridFS, NoFile
from pymongo.errors import PyMongoError

from database import db
from project_registry import project_refs, require_project

router = APIRouter(prefix="/api/documents", tags=["Documents"])
files = GridFS(db, collection="document_files")
file_records = db["document_files.files"]

MAX_SIZE = 15 * 1024 * 1024

Category = Literal[
    "Land record",
    "Ownership document",
    "Survey drawing",
    "Acquisition notice",
    "Compensation record",
    "Court order",
    "Other",
]


def parse_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid record ID.")
    return ObjectId(value)


def detect_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (
        data.startswith(b"RIFF")
        and len(data) >= 12
        and data[8:12] == b"WEBP"
    ):
        return "image/webp"

    raise HTTPException(
        status_code=415,
        detail="Choose a PDF, JPG, PNG or WebP file.",
    )


def serialize(record: dict, project_name: str) -> dict:
    metadata = record.get("metadata", {})

    return {
        "id": str(record["_id"]),
        "name": record.get("filename", "Document"),
        "projectId": metadata.get("projectId", ""),
        "project": project_name,
        "category": metadata.get("category", "Other"),
        "size": record.get("length", 0),
        "contentType": metadata.get("contentType", ""),
        "isDemo": metadata.get("isDemo", True),
        "uploadedAt": record["uploadDate"].isoformat(),
        "internalOnly": metadata.get("internalOnly", False),
    }


def require_staff(role: str) -> None:
    if role not in {"officer", "admin"}:
        raise HTTPException(status_code=403, detail="Officer or admin access required.")


@router.post("", status_code=201)
def upload_document(
    projectId: str = Form(...),
    category: Category = Form(...),
    file: UploadFile = File(...),
    role: str = Header("landowner", alias="X-Liva-Role"),
):
    try:
        require_staff(role)
        project = require_project(projectId)
        project_ref = project["_projectRef"]

        data = file.file.read(MAX_SIZE + 1)

        if not data:
            raise HTTPException(status_code=422, detail="The file is empty.")

        if len(data) > MAX_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Maximum file size is 15 MB.",
            )

        content_type = detect_type(data)

        raw_name = (file.filename or "Document").replace("\\", "/")
        name = raw_name.rsplit("/", 1)[-1]
        name = "".join(char for char in name if char.isprintable())[:180]
        name = name or "Document"

        metadata = {
            "projectId": str(project_ref),
            "category": category,
            "contentType": content_type,
            "isDemo": project.get("isDemo", True),
            "archived": False,
            "internalOnly": True,
        }

        document_id = files.put(
            data,
            filename=name,
            metadata=metadata,
        )

        return {
            "id": str(document_id),
            "name": name,
            "projectId": str(project_ref),
            "project": project.get("_projectName", project.get("name", "")),
            "category": category,
            "size": len(data),
            "contentType": content_type,
            "isDemo": metadata["isDemo"],
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Document storage unavailable.",
        ) from None

    finally:
        file.file.close()


@router.get("")
def list_documents(role: str = Header("landowner", alias="X-Liva-Role")):
    try:
        query = {
            "metadata.archived": {"$ne": True},
            "metadata.livaWorkflow": {"$ne": True},
        }
        if role not in {"officer", "admin"}:
            query["metadata.internalOnly"] = {"$ne": True}

        records = list(
            file_records.find(query).sort("_id", -1)
        )

        project_names = project_refs({
            str(record.get("metadata", {}).get("projectId", ""))
            for record in records
        })

        return {
            "items": [
                serialize(
                    record,
                    project_names.get(
                        record.get("metadata", {}).get("projectId"),
                        "Project unavailable",
                    ),
                )
                for record in records
            ],
            "total": file_records.count_documents(query),
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Document storage unavailable.",
        ) from None


@router.get("/workflow")
def list_project_workflow_documents(
    projectId: str,
    role: str = Header("landowner", alias="X-Liva-Role"),
):
    require_staff(role)
    project = require_project(projectId)
    project_name = project.get("_projectName", project.get("name", "Project"))
    registration_conditions = [{"livaProjectId": projectId}]
    source_request_id = project.get("sourceRegistrationRequestId")
    if source_request_id:
        registration_conditions.append({"requestId": source_request_id})
    registration_query = {"$or": registration_conditions}

    try:
        registrations = list(db["liva_registration_requests"].find(registration_query))
        grievances = list(db["liva_grievances"].find({"projectId": projectId}))
        if not project.get("_isLivaProject") and project.get("surveyNumber"):
            registrations.extend(db["liva_registration_requests"].find({"surveyNumber": project["surveyNumber"]}))
            grievances.extend(db["liva_grievances"].find({"surveyNumber": project["surveyNumber"], "projectId": {"$in": [None, ""]}}))

        references: list[tuple[dict, str, str]] = []
        for request in registrations:
            for field, label in (
                ("ownershipProof", "Ownership document"),
                ("landRecord", "Land record"),
                ("identityProof", "Identity document"),
            ):
                reference = request.get(field)
                if isinstance(reference, dict) and reference.get("fileId"):
                    references.append((reference, label, f"Registration · {request.get('requestId', '')}"))
        for grievance in grievances:
            for reference in grievance.get("supportingDocuments", []):
                if isinstance(reference, dict) and reference.get("fileId"):
                    references.append((reference, "Grievance supporting document", f"Grievance · {grievance.get('grievanceId', '')}"))

        items = []
        seen: set[str] = set()
        for reference, category, source_label in references:
            file_id = str(reference["fileId"])
            if file_id in seen or not ObjectId.is_valid(file_id):
                continue
            seen.add(file_id)
            record = file_records.find_one({
                "_id": ObjectId(file_id),
                "metadata.livaWorkflow": True,
                "metadata.archived": {"$ne": True},
            })
            if record is None:
                continue
            items.append({
                "id": file_id,
                "name": record.get("filename", reference.get("filename", "Document")),
                "projectId": projectId,
                "project": project_name,
                "category": category,
                "size": record.get("length", reference.get("size", 0)),
                "contentType": record.get("metadata", {}).get("contentType", reference.get("contentType", "application/pdf")),
                "isDemo": False,
                "uploadedAt": record["uploadDate"].isoformat(),
                "internalOnly": True,
                "isWorkflow": True,
                "sourceLabel": source_label,
            })
        return {"items": items, "total": len(items)}
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Document storage unavailable.") from None


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    download: bool = True,
    role: str = Header("landowner", alias="X-Liva-Role"),
):
    oid = parse_id(document_id)

    try:
        record = file_records.find_one({
            "_id": oid,
            "metadata.archived": {"$ne": True},
            "metadata.livaWorkflow": {"$ne": True},
            **({} if role in {"officer", "admin"} else {"metadata.internalOnly": {"$ne": True}}),
        })

        if record is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        stored = files.get(oid)

    except NoFile:
        raise HTTPException(status_code=404, detail="File not found.") from None
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Document storage unavailable.",
        ) from None

    def chunks():
        try:
            while chunk := stored.read(256 * 1024):
                yield chunk
        finally:
            stored.close()

    disposition = "attachment" if download else "inline"
    filename = quote(record.get("filename", "Document"), safe="")

    return StreamingResponse(
        chunks(),
        media_type=record.get("metadata", {}).get(
            "contentType", "application/octet-stream"
        ),
        headers={
            "Content-Disposition":
                f"{disposition}; filename*=UTF-8''{filename}",
            "Content-Length": str(record["length"]),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{document_id}")
def archive_document(
    document_id: str,
    role: str = Header("landowner", alias="X-Liva-Role"),
):
    oid = parse_id(document_id)

    try:
        require_staff(role)
        result = file_records.update_one(
            {
                "_id": oid,
                "metadata.archived": {"$ne": True},
            },
            {
                "$set": {
                    "metadata.archived": True,
                    "metadata.archivedAt": datetime.now(timezone.utc),
                }
            },
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Document not found.")

        return {"message": "Document archived. Stored file preserved."}

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Document storage unavailable.",
        ) from None
