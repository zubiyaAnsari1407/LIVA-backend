from datetime import datetime, timezone
from io import BytesIO

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

import liva_documents


class FakeFileRecords:
    def __init__(self):
        self.records = {}

    def find_one(self, query):
        record = self.records.get(query.get("_id"))
        if record is None:
            return None
        for field, expected in query.items():
            if field == "_id":
                continue
            value = record
            for part in field.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if isinstance(expected, dict) and "$ne" in expected:
                if value == expected["$ne"]:
                    return None
            elif value != expected:
                return None
        return record.copy()

    def update_one(self, query, update):
        record = self.records.get(query.get("_id"))
        if record is None:
            return type("Result", (), {"matched_count": 0})()
        for field, expected in query.items():
            if field == "_id":
                continue
            value = record
            for part in field.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if isinstance(expected, dict) and "$exists" in expected:
                if (value is not None) != expected["$exists"]:
                    return type("Result", (), {"matched_count": 0})()
            elif isinstance(expected, dict) and "$ne" in expected:
                if value == expected["$ne"]:
                    return type("Result", (), {"matched_count": 0})()
            elif value != expected:
                return type("Result", (), {"matched_count": 0})()
        for field, value in update["$set"].items():
            parent, child = field.split(".", 1)
            record.setdefault(parent, {})[child] = value
        return type("Result", (), {"matched_count": 1})()


class FakeGridFS:
    def __init__(self, file_records):
        self.file_records = file_records
        self.content = {}

    def put(self, data, filename, metadata):
        file_id = ObjectId()
        self.content[file_id] = data
        self.file_records.records[file_id] = {
            "_id": file_id,
            "filename": filename,
            "length": len(data),
            "uploadDate": datetime.now(timezone.utc),
            "metadata": metadata,
        }
        return file_id

    def get(self, file_id):
        return BytesIO(self.content[file_id])


def test_liva_upload_reuses_gridfs_and_serves_inline_bytes(monkeypatch):
    file_records = FakeFileRecords()
    gridfs = FakeGridFS(file_records)
    monkeypatch.setattr(liva_documents, "file_records", file_records)
    monkeypatch.setattr(liva_documents, "files", gridfs)

    app = FastAPI()
    app.include_router(liva_documents.router)
    client = TestClient(app)
    content = b"%PDF-1.7\nLIVA preview fixture"

    uploaded = client.post(
        "/api/liva/documents",
        data={"workflowType": "registration", "documentType": "ownershipProof"},
        files={"file": ("proof.pdf", content, "application/pdf")},
    )

    assert uploaded.status_code == 201
    reference = uploaded.json()
    assert set(reference) == {"fileId", "filename", "contentType", "size", "uploadedAt"}
    assert reference["filename"] == "proof.pdf"
    assert reference["contentType"] == "application/pdf"
    assert reference["size"] == len(content)

    viewed = client.get(f"/api/liva/documents/{reference['fileId']}")
    assert viewed.status_code == 200
    assert viewed.content == content
    assert viewed.headers["content-type"] == "application/pdf"
    assert viewed.headers["content-disposition"].startswith("inline;")

    stored_reference = liva_documents.get_liva_document_reference(
        reference["fileId"],
        "registration",
        "ownershipProof",
    )
    assert stored_reference["fileId"] == reference["fileId"]
    liva_documents.link_liva_document(
        reference["fileId"],
        "registration",
        "ownershipProof",
        "REQ-TEST",
    )
    assert client.delete(
        f"/api/liva/documents/{reference['fileId']}"
    ).status_code == 409
