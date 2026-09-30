from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from gridfs import NoFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import PyMongoError

from documents import MAX_SIZE, detect_type, file_records, files, parse_id


router = APIRouter(
    prefix="/api/liva/documents",
    tags=["LIVA Documents"],
)

WorkflowType = Literal["registration", "grievance"]
DocumentType = Literal[
    "ownershipProof",
    "landRecord",
    "identityProof",
    "grievanceSupporting",
]

DocumentContentType = Literal[
    "application/pdf",
    "image/jpeg",
    "image/png",
]


class LivaDocumentReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fileId: str = Field(min_length=24, max_length=24)
    filename: str = Field(min_length=1, max_length=180)
    contentType: DocumentContentType
    size: int = Field(ge=1)
    uploadedAt: datetime

    @field_validator("fileId")
    @classmethod
    def validate_file_id(cls, value: str) -> str:
        if not ObjectId.is_valid(value):
            raise ValueError("fileId must be a MongoDB GridFS file ID.")
        return value


def get_liva_document_reference(
    file_id: str,
    workflow_type: WorkflowType,
    document_type: DocumentType,
) -> dict:
    object_id = parse_id(file_id)

    try:
        record = file_records.find_one(
            {
                "_id": object_id,
                "metadata.livaWorkflow": True,
                "metadata.workflowType": workflow_type,
                "metadata.documentType": document_type,
                "metadata.archived": {"$ne": True},
            }
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA document storage is unavailable.",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document reference is not a stored LIVA upload for this field.",
        )

    metadata = record.get("metadata", {})
    return LivaDocumentReference(
        fileId=str(record["_id"]),
        filename=record.get("filename", "Document"),
        contentType=metadata.get("contentType", "application/octet-stream"),
        size=record.get("length", 0),
        uploadedAt=record["uploadDate"],
    ).model_dump(mode="python")


def link_liva_document(
    file_id: str,
    workflow_type: WorkflowType,
    document_type: DocumentType,
    record_id: str,
) -> None:
    object_id = parse_id(file_id)

    try:
        result = file_records.update_one(
            {
                "_id": object_id,
                "metadata.livaWorkflow": True,
                "metadata.workflowType": workflow_type,
                "metadata.documentType": document_type,
                "metadata.archived": {"$ne": True},
            },
            {
                "$set": {
                    "metadata.recordId": record_id,
                    "metadata.recordType": workflow_type,
                }
            },
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA document storage is unavailable.",
        ) from None

    if result.matched_count != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document reference is not a stored LIVA upload for this field.",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_liva_document(
    workflowType: WorkflowType = Form(...),
    documentType: DocumentType = Form(...),
    file: UploadFile = File(...),
):
    if workflowType == "registration" and documentType == "grievanceSupporting":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grievance documents must use the grievance workflow type.",
        )

    if workflowType == "grievance" and documentType != "grievanceSupporting":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grievance uploads must use the grievanceSupporting document type.",
        )

    try:
        data = file.file.read(MAX_SIZE + 1)
        if not data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The file is empty.",
            )
        if len(data) > MAX_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Maximum file size is 15 MB.",
            )

        content_type = detect_type(data)
        raw_name = (file.filename or "Document").replace("\\", "/")
        filename = raw_name.rsplit("/", 1)[-1]
        filename = "".join(char for char in filename if char.isprintable())[:180]
        filename = filename or "Document"
        uploaded_at = datetime.now(timezone.utc)

        file_id = files.put(
            data,
            filename=filename,
            metadata={
                "livaWorkflow": True,
                "workflowType": workflowType,
                "documentType": documentType,
                "contentType": content_type,
                "archived": False,
            },
        )

        return {
            "fileId": str(file_id),
            "filename": filename,
            "contentType": content_type,
            "size": len(data),
            "uploadedAt": uploaded_at,
        }
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA document storage is unavailable.",
        ) from None
    finally:
        file.file.close()


@router.get("/{file_id}")
def view_liva_document(file_id: str):
    object_id: ObjectId = parse_id(file_id)

    try:
        record = file_records.find_one(
            {
                "_id": object_id,
                "metadata.livaWorkflow": True,
                "metadata.archived": {"$ne": True},
            }
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LIVA document not found.",
            )

        stored = files.get(object_id)
    except NoFile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LIVA document file not found.",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA document storage is unavailable.",
        ) from None

    filename = quote(record.get("filename", "Document"), safe="")

    def chunks():
        try:
            while chunk := stored.read(256 * 1024):
                yield chunk
        finally:
            stored.close()

    return StreamingResponse(
        chunks(),
        media_type=record.get("metadata", {}).get(
            "contentType", "application/octet-stream"
        ),
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "Content-Length": str(record["length"]),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{file_id}")
def archive_unlinked_liva_document(file_id: str):
    object_id = parse_id(file_id)

    try:
        result = file_records.update_one(
            {
                "_id": object_id,
                "metadata.livaWorkflow": True,
                "metadata.recordId": {"$exists": False},
                "metadata.archived": {"$ne": True},
            },
            {
                "$set": {
                    "metadata.archived": True,
                    "metadata.archivedAt": datetime.now(timezone.utc),
                }
            },
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA document storage is unavailable.",
        ) from None

    if result.matched_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only unlinked LIVA uploads can be archived.",
        )

    return {"archived": True, "fileId": file_id}
