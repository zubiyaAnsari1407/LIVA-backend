from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from gridfs import GridFS, NoFile
from pymongo.errors import PyMongoError

from database import db

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
    }


@router.post("", status_code=201)
def upload_document(
    projectId: str = Form(...),
    category: Category = Form(...),
    file: UploadFile = File(...),
):
    try:
        project_oid = parse_id(projectId)

        project = db.projects.find_one({"_id": project_oid})
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")

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
            "projectId": str(project_oid),
            "category": category,
            "contentType": content_type,
            "isDemo": project.get("isDemo", True),
            "archived": False,
        }

        document_id = files.put(
            data,
            filename=name,
            metadata=metadata,
        )

        return {
            "id": str(document_id),
            "name": name,
            "projectId": str(project_oid),
            "project": project.get("name", ""),
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
def list_documents():
    try:
        query = {"metadata.archived": {"$ne": True}}

        records = list(
            file_records.find(query).sort("_id", -1).limit(100)
        )

        project_ids = {
            ObjectId(record["metadata"]["projectId"])
            for record in records
            if ObjectId.is_valid(
                str(record.get("metadata", {}).get("projectId", ""))
            )
        }

        project_names = {
            str(project["_id"]): project.get("name", "")
            for project in db.projects.find(
                {"_id": {"$in": list(project_ids)}},
                {"name": 1},
            )
        }

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


@router.get("/{document_id}/file")
def get_document_file(document_id: str, download: bool = True):
    oid = parse_id(document_id)

    try:
        record = file_records.find_one({
            "_id": oid,
            "metadata.archived": {"$ne": True},
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
def archive_document(document_id: str):
    oid = parse_id(document_id)

    try:
        result = file_records.update_one(
            {"_id": oid},
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