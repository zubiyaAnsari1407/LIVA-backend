from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import liva_registration


class FakeCursor:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def sort(self, field: str, direction: int):
        self.records.sort(
            key=lambda item: item.get(field),
            reverse=direction < 0,
        )
        return self

    def skip(self, count: int):
        self.records = self.records[count:]
        return self

    def limit(self, count: int):
        self.records = self.records[:count]
        return self

    def __iter__(self):
        return iter(self.records)


@dataclass
class InsertResult:
    inserted_id: int


@dataclass
class UpdateResult:
    matched_count: int


class FakeCollection:
    def __init__(self):
        self.records: list[dict[str, Any]] = []
        self.indexes: dict[str, dict[str, Any]] = {}

    def create_index(self, field: str, unique: bool, name: str):
        self.indexes[name] = {"field": field, "unique": unique}
        return name

    def find(self, query=None, projection=None):
        query = query or {}
        records = [
            deepcopy(record)
            for record in self.records
            if all(record.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(records)

    def find_one(self, query):
        for record in self.records:
            if all(record.get(key) == value for key, value in query.items()):
                return deepcopy(record)
        return None

    def insert_one(self, document):
        if any(
            record["requestId"] == document["requestId"]
            for record in self.records
        ):
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError("Duplicate requestId")

        stored = deepcopy(document)
        stored["_id"] = len(self.records) + 1
        self.records.append(stored)
        return InsertResult(stored["_id"])

    def update_one(self, query, update):
        for record in self.records:
            if all(record.get(key) == value for key, value in query.items()):
                for field, value in deepcopy(update["$set"]).items():
                    if "." in field:
                        parent, child = field.split(".", 1)
                        record.setdefault(parent, {})[child] = value
                    else:
                        record[field] = value
                return UpdateResult(1)
        return UpdateResult(0)

    def count_documents(self, query):
        return len(list(self.find(query)))


@pytest.fixture
def api_client(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(liva_registration, "request_collection", collection)
    monkeypatch.setattr(liva_registration, "_indexes_ready", False)

    filenames = {
        "ownershipProof": "ownership-proof.pdf",
        "landRecord": "land-record.jpg",
        "identityProof": "identity-proof.png",
    }

    def get_document_reference(file_id, workflow_type, document_type):
        return {
            "fileId": file_id,
            "filename": filenames[document_type],
            "contentType": "application/pdf",
            "size": 128,
            "uploadedAt": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(
        liva_registration,
        "get_liva_document_reference",
        get_document_reference,
    )
    monkeypatch.setattr(
        liva_registration,
        "link_liva_document",
        lambda *args: None,
    )

    app = FastAPI()
    app.include_router(liva_registration.router)

    with TestClient(app) as client:
        yield client, collection


def request_payload(survey_number="42/1A"):
    return {
        "surveyNumber": survey_number,
        "ownerName": "Ramesh Kumar",
        "village": "Devpura",
        "district": "Dharanpur",
        "state": "Madhya Pradesh",
        "pincode": "461001",
        "area": "0.85 hectares",
        "reason": "Land is not available in the project records.",
        "ownershipProof": {
            "fileId": "64b000000000000000000001",
            "filename": "ownership-proof.pdf",
            "contentType": "application/pdf",
            "size": 128,
            "uploadedAt": "2026-09-29T00:00:00Z",
        },
        "landRecord": {
            "fileId": "64b000000000000000000002",
            "filename": "land-record.jpg",
            "contentType": "image/jpeg",
            "size": 128,
            "uploadedAt": "2026-09-29T00:00:00Z",
        },
        "identityProof": {
            "fileId": "64b000000000000000000003",
            "filename": "identity-proof.png",
            "contentType": "image/png",
            "size": 128,
            "uploadedAt": "2026-09-29T00:00:00Z",
        },
    }


def test_registration_request_lifecycle_and_isolated_indexes(api_client):
    client, collection = api_client

    created = client.post(
        "/api/liva/registration-requests",
        json=request_payload(),
    )
    assert created.status_code == 201
    request = created.json()
    assert request["requestId"] == "REQ-001"
    assert request["status"] == "SUBMITTED"
    assert request["ownershipProof"]["filename"] == "ownership-proof.pdf"
    assert request["ownershipProof"]["fileId"] == "64b000000000000000000001"
    assert "url" not in request["ownershipProof"]
    assert "projectId" not in request
    assert "project_id" not in request

    request_id = request["requestId"]
    assert client.get(
        f"/api/liva/registration-requests/{request_id}"
    ).json()["surveyNumber"] == "42/1A"

    listing = client.get("/api/liva/registration-requests")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["items"][0]["requestId"] == request_id

    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "UNDER_VERIFICATION"},
    ).json()["status"] == "UNDER_VERIFICATION"

    incomplete_verification = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED"},
    )
    assert incomplete_verification.status_code == 409

    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={
            "documentVerification": {
                "ownershipProof": True,
                "landRecord": True,
                "identityProof": True,
            }
        },
    ).status_code == 200

    returned = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={
            "status": "RETURNED",
            "officerRemark": "Please clarify the survey entry.",
        },
    ).json()
    assert returned["status"] == "RETURNED"
    assert returned["officerRemark"] == "Please clarify the survey entry."
    assert returned["surveyNumber"] == "42/1A"
    assert returned["ownershipProof"]["filename"] == "ownership-proof.pdf"

    returned_cannot_skip_correction = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED"},
    )
    assert returned_cannot_skip_correction.status_code == 409

    resubmitted = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={
            "status": "UNDER_VERIFICATION",
            "surveyNumber": "42/1B",
            "ownerName": "Ramesh Kumar Corrected",
            "village": "Devpura North",
            "district": "Dharanpur",
            "state": "Madhya Pradesh",
            "pincode": "461002",
            "area": "0.90 hectares",
            "reason": "Corrected land record details.",
            "ownershipProof": {
                **request_payload()["ownershipProof"],
                "fileId": "64b000000000000000000004",
            },
            "landRecord": request_payload()["landRecord"],
            "identityProof": request_payload()["identityProof"],
            "documentVerification": {
                "ownershipProof": False,
                "landRecord": False,
                "identityProof": False,
            },
        },
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["requestId"] == request_id
    assert resubmitted.json()["status"] == "UNDER_VERIFICATION"
    assert resubmitted.json()["ownerName"] == "Ramesh Kumar Corrected"
    assert resubmitted.json()["surveyNumber"] == "42/1B"
    assert not any(resubmitted.json()["documentVerification"].values())
    assert resubmitted.json()["officerRemark"] == ""
    assert resubmitted.json()["reviewHistory"][-1]["status"] == "RETURNED"
    assert resubmitted.json()["reviewHistory"][-1]["officerRemark"] == "Please clarify the survey entry."

    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={
            "documentVerification": {
                "ownershipProof": True,
                "landRecord": True,
                "identityProof": True,
            }
        },
    ).status_code == 200
    verified_after_resubmission = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED"},
    )
    assert verified_after_resubmission.status_code == 200
    assert verified_after_resubmission.json()["status"] == "OFFICER_VERIFIED"

    second = client.post(
        "/api/liva/registration-requests",
        json=request_payload("76/3B"),
    ).json()
    assert second["requestId"] == "REQ-002"

    assert client.patch(
        f"/api/liva/registration-requests/{second['requestId']}",
        json={
            "documentVerification": {
                "ownershipProof": True,
                "landRecord": True,
                "identityProof": True,
            }
        },
    ).status_code == 200

    assert client.patch(
        f"/api/liva/registration-requests/{second['requestId']}",
        json={"status": "UNDER_VERIFICATION"},
    ).json()["status"] == "UNDER_VERIFICATION"

    verified = client.patch(
        f"/api/liva/registration-requests/{second['requestId']}",
        json={"status": "OFFICER_VERIFIED"},
    ).json()
    assert verified["status"] == "OFFICER_VERIFIED"

    denied_admin_transition = client.patch(
        f"/api/liva/registration-requests/{second['requestId']}",
        json={"status": "APPROVED"},
    )
    assert denied_admin_transition.status_code == 403
    assert client.get(
        f"/api/liva/registration-requests/{second['requestId']}"
    ).json()["status"] == "OFFICER_VERIFIED"

    assert set(index["field"] for index in collection.indexes.values()) == {
        "requestId",
        "status",
        "surveyNumber",
        "createdAt",
        "updatedAt",
    }
    assert collection.indexes["uq_liva_registration_request_id"]["unique"] is True


def test_admin_rejected_request_can_be_corrected_without_losing_review_history(api_client):
    client, _ = api_client
    created = client.post(
        "/api/liva/registration-requests",
        json=request_payload(),
    ).json()
    request_id = created["requestId"]

    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "UNDER_VERIFICATION"},
    ).status_code == 200
    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"documentVerification": {"ownershipProof": True, "landRecord": True, "identityProof": True}},
    ).status_code == 200
    verified = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED", "officerRemark": "Officer verified the documents."},
    )
    assert verified.status_code == 200
    rejected = client.patch(
        f"/api/liva/registration-requests/{request_id}/admin-decision",
        json={"decision": "REJECT", "adminRemark": "Correct the survey details and resubmit."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    correction = request_payload("42/1B")
    correction.update({
        "status": "UNDER_VERIFICATION",
        "ownerName": "Ramesh Kumar Corrected",
        # Even stale client verification flags must not carry into a new review cycle.
        "documentVerification": {"ownershipProof": True, "landRecord": True, "identityProof": True},
    })
    resubmitted = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json=correction,
    )
    assert resubmitted.status_code == 200
    result = resubmitted.json()
    assert result["requestId"] == request_id
    assert result["status"] == "UNDER_VERIFICATION"
    assert result["surveyNumber"] == "42/1B"
    assert result["officerRemark"] == ""
    assert result["adminRemark"] == ""
    assert result["reviewHistory"][-1]["status"] == "REJECTED"
    assert result["reviewHistory"][-1]["officerRemark"] == "Officer verified the documents."
    assert result["reviewHistory"][-1]["adminRemark"] == "Correct the survey details and resubmit."
    assert not any(result["documentVerification"].values())

    # The new cycle can be reviewed normally after fresh document verification.
    assert client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"documentVerification": {"ownershipProof": True, "landRecord": True, "identityProof": True}},
    ).status_code == 200
    next_review = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED", "officerRemark": "Corrected details verified."},
    )
    assert next_review.status_code == 200
    assert next_review.json()["reviewHistory"][-1]["adminRemark"] == "Correct the survey details and resubmit."


def test_invalid_transition_extra_fields_and_missing_request(api_client):
    client, _ = api_client

    created = client.post(
        "/api/liva/registration-requests",
        json=request_payload(),
    ).json()
    request_id = created["requestId"]

    invalid_transition = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"status": "OFFICER_VERIFIED"},
    )
    assert invalid_transition.status_code == 409

    arbitrary_update = client.patch(
        f"/api/liva/registration-requests/{request_id}",
        json={"ownerName": "Overwritten Name"},
    )
    assert arbitrary_update.status_code == 409

    assert client.get(
        "/api/liva/registration-requests/REQ-999"
    ).status_code == 404

    assert client.patch(
        "/api/liva/registration-requests/REQ-999",
        json={"officerRemark": "Missing"},
    ).status_code == 404

    invalid_data = request_payload()
    invalid_data["pincode"] = "123"
    assert client.post(
        "/api/liva/registration-requests",
        json=invalid_data,
    ).status_code == 422


def test_request_id_uses_highest_existing_sequence(api_client):
    client, collection = api_client
    collection.records.extend(
        [
            {"requestId": "REQ-002"},
            {"requestId": "REQ-014"},
            {"requestId": "legacy-id"},
        ]
    )

    response = client.post(
        "/api/liva/registration-requests",
        json=request_payload("88/2C"),
    )

    assert response.status_code == 201
    assert response.json()["requestId"] == "REQ-015"
