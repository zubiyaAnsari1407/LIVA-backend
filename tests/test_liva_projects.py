from copy import deepcopy

import liva_projects
from pymongo.errors import DuplicateKeyError


class FakeProjectCollection:
    def __init__(self, records):
        self.records = deepcopy(records)

    def create_index(self, *_args, **_kwargs):
        return "index"

    def find_one(self, query):
        for record in self.records:
            if all(record.get(key) == value for key, value in query.items()):
                return deepcopy(record)
        return None

    def insert_one(self, document):
        if self.find_one({"projectId": document["projectId"]}):
            raise DuplicateKeyError("duplicate projectId")
        if self.find_one({"sourceRegistrationRequestId": document["sourceRegistrationRequestId"]}):
            raise DuplicateKeyError("duplicate source request")
        stored = deepcopy(document)
        stored["_id"] = len(self.records) + 1
        self.records.append(stored)


def test_registration_project_creation_skips_taken_demo_ids(monkeypatch):
    records = [
        {
            "projectId": f"LIVA-PRJ-{suffix:03d}",
            "sourceRegistrationRequestId": f"DEMO-{suffix}",
        }
        for suffix in range(6, 21)
    ]
    collection = FakeProjectCollection(records)
    monkeypatch.setattr(liva_projects, "projects_collection", collection)
    monkeypatch.setattr(liva_projects, "_indexes_ready", False)

    request = {
        "requestId": "REQ-006",
        "surveyNumber": "215/4A",
        "ownerName": "Demo Applicant",
        "village": "Maasgaon",
        "district": "Pune",
        "state": "Maharashtra",
        "pincode": "411001",
        "area": "0.50 hectares",
    }

    project = liva_projects.create_or_get_project_from_registration(request)

    assert project["projectId"] == "LIVA-PRJ-021"
    assert project["sourceRegistrationRequestId"] == "REQ-006"
    assert project["surveyNumber"] == request["surveyNumber"]
    assert len(collection.records) == len(records) + 1

    # Retrying an approval returns the same project instead of creating one.
    repeated = liva_projects.create_or_get_project_from_registration(request)
    assert repeated["projectId"] == project["projectId"]
    assert len(collection.records) == len(records) + 1
