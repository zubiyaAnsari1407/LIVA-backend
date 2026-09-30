"""Seed the LIVA landowner project-list demo without creating workflow records.

This targets 20 total records in the existing ``liva_projects`` collection.
Existing records are never updated or deleted. Re-running the script is safe.
The additional records are clearly marked as demo project-list entries and do
not create registration requests, grievances, assessments, or other workflows.

Run from ``backend`` with ``.venv\\Scripts\\python.exe seed_liva_project_list.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from database import db


SEED_KEY = "liva-landowner-project-list-v1"

# ID 003 is an existing real demo record and remains untouched. ID 005 is also
# already present, so the additions fill the gaps and extend through ID 020.
DEMO_PROJECTS = [
    ("004", "Borgaon", "87/1", "Pune", "412205", "0.42 hectares", "UNDER_SURVEY"),
    ("006", "Khedgaon", "112/4A", "Pune", "410505", "0.68 hectares", "LAND_ACQUISITION_IN_PROGRESS"),
    ("007", "Dapoli", "23/2B", "Ratnagiri", "415712", "0.31 hectares", "ACTIVE"),
    ("008", "Nandgaon", "65/3", "Raigad", "402203", "1.15 hectares", "COMPENSATION_PENDING"),
    ("009", "Pimpalwadi", "18/7A", "Ahilyanagar", "414103", "0.56 hectares", "UNDER_SURVEY"),
    ("010", "Sawargaon", "204/1", "Nashik", "422210", "0.87 hectares", "ACTIVE"),
    ("011", "Waki", "91/5C", "Pune", "410512", "0.24 hectares", "LAND_ACQUISITION_IN_PROGRESS"),
    ("012", "Kumbharli", "44/6", "Satara", "415013", "0.73 hectares", "UNDER_SURVEY"),
    ("013", "Shirasgaon", "137/2A", "Kolhapur", "416119", "0.39 hectares", "ACTIVE"),
    ("014", "Ambegaon", "52/9B", "Pune", "410503", "1.02 hectares", "ON_HOLD"),
    ("015", "Palshet", "76/1", "Ratnagiri", "415726", "0.48 hectares", "COMPENSATION_PENDING"),
    ("016", "Karanje", "31/4D", "Satara", "415002", "0.62 hectares", "LAND_ACQUISITION_IN_PROGRESS"),
    ("017", "Belsar", "108/3", "Pune", "412303", "0.91 hectares", "ACTIVE"),
    ("018", "Vadhav", "15/8A", "Raigad", "402107", "0.35 hectares", "UNDER_SURVEY"),
    ("019", "Mhasla", "63/2C", "Raigad", "402105", "0.77 hectares", "LAND_ACQUISITION_IN_PROGRESS"),
    ("020", "Chiplun", "129/5", "Ratnagiri", "415605", "0.54 hectares", "ACTIVE"),
]


def seed() -> int:
    collection = db["liva_projects"]
    now = datetime.now(timezone.utc)
    inserted = 0

    for suffix, village, survey, district, pincode, area, status in DEMO_PROJECTS:
        project_id = f"LIVA-PRJ-{suffix}"
        if collection.find_one({"projectId": project_id}, {"_id": 1}):
            continue

        record = {
            "projectId": project_id,
            "projectName": f"{village} {survey} Land Acquisition Project",
            "surveyNumber": survey,
            "ownerName": "Demo Landowner",
            "village": village,
            "district": district,
            "state": "Maharashtra",
            "pincode": pincode,
            "area": area,
            # Synthetic lineage marker satisfies the existing API schema;
            # it intentionally does not point to or create a request record.
            "sourceRegistrationRequestId": f"DEMO-SEED-{project_id}",
            "createdAt": now,
            "updatedAt": now,
            "status": status,
            "isDemo": True,
            "demoSeedKey": SEED_KEY,
        }
        try:
            collection.insert_one(record)
            inserted += 1
        except DuplicateKeyError:
            # Another run may have inserted this ID concurrently. Never alter
            # the existing project or take over an ID that belongs to a user.
            continue

    total = collection.count_documents({})
    print(f"Inserted {inserted} demo project-list records; liva_projects now has {total} records.")
    return total


if __name__ == "__main__":
    seed()
