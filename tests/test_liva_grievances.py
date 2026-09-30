from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import liva_grievances


class FakeCursor:
    def __init__(self, records):
        self.records = records

    def sort(self, field, direction):
        self.records.sort(
            key=lambda record: record.get(field),
            reverse=direction < 0,
        )
        return self

    def skip(self, count):
        self.records = self.records[count:]
        return self

    def limit(self, count):
        self.records = self.records[:count]
        return self

    def __iter__(self):
        return iter(self.records)


class FakeCollection:
    def __init__(self):
        self.records = []
        self.indexes = {}

    def create_index(self, field, unique, name):
        self.indexes[name] = {"field": field, "unique": unique}
        return name

    def find(self, query=None, projection=None):
        query = query or {}
        return FakeCursor([
            deepcopy(record)
            for record in self.records
            if all(record.get(key) == value for key, value in query.items())
        ])

    def find_one(self, query):
        for record in self.records:
            if all(record.get(key) == value for key, value in query.items()):
                return deepcopy(record)
        return None

    def insert_one(self, document):
        if any(record["grievanceId"] == document["grievanceId"] for record in self.records):
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError("Duplicate grievanceId")
        stored = deepcopy(document)
        stored["_id"] = len(self.records) + 1
        self.records.append(stored)

    def update_one(self, query, update):
        for record in self.records:
            if all(record.get(key) == value for key, value in query.items()):
                record.update(deepcopy(update["$set"]))
                return type("Result", (), {"matched_count": 1})()
        return type("Result", (), {"matched_count": 0})()

    def count_documents(self, query):
        return len(list(self.find(query)))


@pytest.fixture
def grievance_client(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(liva_grievances, "grievance_collection", collection)
    monkeypatch.setattr(liva_grievances, "_indexes_ready", False)
    monkeypatch.setattr(
        liva_grievances,
        "get_liva_document_reference",
        lambda file_id, workflow, document_type: {
            "fileId": file_id,
            "filename": f"{file_id}.pdf",
            "contentType": "application/pdf",
            "size": 100,
            "uploadedAt": datetime.now(timezone.utc),
        },
    )
    monkeypatch.setattr(liva_grievances, "link_liva_document", lambda *args: None)

    app = FastAPI()
    app.include_router(liva_grievances.router)
    with TestClient(app) as client:
        yield client, collection


def grievance_payload(documents=None):
    return {
        "applicantName": "Ramesh Kumar",
        "mobile": "9876543210",
        "surveyNumber": "42/1A",
        "village": "Devpura",
        "district": "Dharanpur",
        "project": "Fictional Village Access Project",
        "type": "compensation",
        "description": "Compensation status needs review.",
        "supportingDocuments": documents or [],
    }


def document_reference(file_id):
    return {
        "fileId": file_id,
        "filename": f"support-{file_id[-1]}.pdf",
        "contentType": "application/pdf",
        "size": 100,
        "uploadedAt": "2026-09-29T00:00:00Z",
    }


def test_grievance_support_documents_optional_multiple_and_statuses(grievance_client):
    client, collection = grievance_client

    no_docs = client.post(
        "/api/liva/grievances",
        json=grievance_payload(),
    )
    assert no_docs.status_code == 201
    assert no_docs.json()["supportingDocuments"] == []

    documents = [
        document_reference(f"64b00000000000000000000{index}")
        for index in range(1, 4)
    ]
    created = client.post(
        "/api/liva/grievances",
        json=grievance_payload(documents),
    )
    assert created.status_code == 201
    record = created.json()
    assert record["grievanceId"] == "GRV-002"
    assert len(record["supportingDocuments"]) == 3
    assert record["surveyNumber"] == "42/1A"
    assert record["project"] == "Fictional Village Access Project"

    assert client.patch(
        f"/api/liva/grievances/{record['grievanceId']}",
        json={"status": "UNDER_VERIFICATION"},
    ).json()["status"] == "UNDER_VERIFICATION"
    verified = client.patch(
        f"/api/liva/grievances/{record['grievanceId']}",
        json={
            "status": "PROBLEM_VERIFIED",
            "officerRemark": "Reviewed submitted details.",
        },
    ).json()
    assert verified["status"] == "PROBLEM_VERIFIED"
    assert verified["officerRemark"] == "Reviewed submitted details."
    assert len(verified["supportingDocuments"]) == 3

    assert client.get("/api/liva/grievances").json()["total"] == 2
    assert set(index["field"] for index in collection.indexes.values()) == {
        "grievanceId",
        "status",
        "surveyNumber",
        "projectId",
        "createdAt",
    }


def test_existing_project_link_survives_submission_and_officer_verification(
    grievance_client,
    monkeypatch,
):
    client, collection = grievance_client
    project = {
        "projectId": "LIVA-PRJ-002",
        "projectName": "Devpura 42/1A Land Acquisition Project",
        "surveyNumber": "42/1A",
    }
    verified_assessments = []
    monkeypatch.setattr(
        liva_grievances.projects_collection,
        "find",
        lambda query: FakeCursor(
            [deepcopy(project)]
            if query == {
                "surveyNumber": "42/1A",
                "projectName": project["projectName"],
            }
            else []
        ),
    )
    monkeypatch.setattr(
        liva_grievances,
        "create_or_get_assessment_for_verified_grievance",
        lambda grievance: verified_assessments.append(deepcopy(grievance)),
    )

    payload = grievance_payload()
    payload["project"] = project["projectName"]
    payload["projectId"] = None  # Simulates an older client omitting this field.
    created = client.post("/api/liva/grievances", json=payload)

    assert created.status_code == 201
    grievance = created.json()
    assert grievance["projectId"] == project["projectId"]
    assert client.get("/api/liva/grievances").json()["items"][0]["projectId"] == project["projectId"]

    assert client.patch(
        f"/api/liva/grievances/{grievance['grievanceId']}",
        json={"status": "UNDER_VERIFICATION"},
    ).status_code == 200
    verified = client.patch(
        f"/api/liva/grievances/{grievance['grievanceId']}",
        json={"status": "PROBLEM_VERIFIED"},
    )

    assert verified.status_code == 200
    assert verified.json()["projectId"] == project["projectId"]
    assert len(verified_assessments) == 1
    assert verified_assessments[0]["grievanceId"] == grievance["grievanceId"]
    assert verified_assessments[0]["projectId"] == project["projectId"]
    assert collection.find_one({"grievanceId": grievance["grievanceId"]})["projectId"] == project["projectId"]


def test_grievance_maximum_and_transition_validation(grievance_client):
    client, _ = grievance_client
    documents = [
        document_reference(f"64b00000000000000000000{index}")
        for index in range(1, 5)
    ]
    assert client.post(
        "/api/liva/grievances",
        json=grievance_payload(documents),
    ).status_code == 422

    created = client.post(
        "/api/liva/grievances",
        json=grievance_payload(),
    ).json()
    assert client.patch(
        f"/api/liva/grievances/{created['grievanceId']}",
        json={"status": "PROBLEM_VERIFIED"},
    ).status_code == 409


def test_verified_officer_report_and_reply_are_persisted_on_original_grievance(grievance_client):
    client, collection = grievance_client
    created = client.post(
        "/api/liva/grievances",
        json=grievance_payload(),
    ).json()
    grievance_id = created["grievanceId"]
    assert client.patch(
        f"/api/liva/grievances/{grievance_id}",
        json={"status": "UNDER_VERIFICATION"},
    ).status_code == 200

    officer_report = {
        "findings": "The compensation file is awaiting a joint measurement.",
        "rootCause": "Measurement record has not been received from the survey team.",
        "actionPlan": "Officer has requested the measurement and will follow up.",
        "workStatus": "IN_PROGRESS",
        "ownershipIssueConfirmed": False,
        "surveyPending": True,
        "compensationPending": True,
        "overdueDays": 12,
    }
    response = client.patch(
        f"/api/liva/grievances/{grievance_id}",
        json={
            "status": "PROBLEM_VERIFIED",
            "officerRemark": "The submitted concern is confirmed against the project file.",
            "officerReport": officer_report,
        },
    )

    assert response.status_code == 200
    saved = response.json()
    assert saved["grievanceId"] == grievance_id
    assert saved["description"] == grievance_payload()["description"]
    assert saved["officerReport"] == officer_report
    assert saved["reviewHistory"][-1]["officerReport"] == officer_report
    assert saved["reviewHistory"][-1]["officerRemark"] == "The submitted concern is confirmed against the project file."
    stored = collection.find_one({"grievanceId": grievance_id})
    assert stored["officerReport"]["actionPlan"] == officer_report["actionPlan"]
    admin_record = client.get("/api/liva/grievances").json()["items"][0]
    assert admin_record["description"] == grievance_payload()["description"]
    assert admin_record["officerReport"] == officer_report
    assert admin_record["reviewHistory"][-1]["officerRemark"] == saved["officerRemark"]
