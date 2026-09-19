"""
LIVA complete end-to-end demo seed.

Purpose
-------
Creates ONE clearly labelled illustrative demo project and connected records
across the current LIVA MongoDB collections.

Safety / data policy
--------------------
- Every seeded record is marked isDemo=True.
- No seeded record is represented as an official/government fact.
- Official projects already in MongoDB are not modified.
- Re-running this file is idempotent for this seed key: previous records
  created by this script are removed/replaced instead of duplicated.

Run from the backend folder:
    uv run python seed_complete_demo.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from gridfs import GridFS

from database import db


SEED_KEY = "liva-complete-demo-v1"
PROJECT_NAME = "LIVA End-to-End Demo Corridor"
PROJECT_RECORD_ID = "DEMO-LIVA-001"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_date(days_from_today: int = 0) -> str:
    return (utc_now().date() + timedelta(days=days_from_today)).isoformat()


def pdf_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def make_demo_pdf(title: str, lines: Iterable[str]) -> bytes:
    """
    Build a tiny valid one-page PDF without any extra dependency.
    Good enough for LIVA's GridFS document preview/download testing.
    """
    content_lines = [
        "BT",
        "/F1 17 Tf",
        "50 790 Td",
        f"({pdf_escape(title)}) Tj",
        "/F1 10 Tf",
    ]

    for line in lines:
        content_lines.extend(
            [
                "0 -22 Td",
                f"({pdf_escape(line)}) Tj",
            ]
        )

    content_lines.append("ET")
    stream = ("\n".join(content_lines) + "\n").encode("latin-1", "replace")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"endstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )

    return bytes(pdf)


def cleanup_previous_seed(project_id: str) -> None:
    """
    Remove only records created by this seed.
    Does not touch manually created demo records or official source records.
    """
    for collection_name in [
        "parcels",
        "litigation",
        "compensation",
        "actions",
        "rehabilitation",
        "simulation_runs",
    ]:
        db[collection_name].delete_many({"demoSeedKey": SEED_KEY})

    fs = GridFS(db, collection="document_files")
    file_records = db["document_files.files"]

    for record in file_records.find({"metadata.demoSeedKey": SEED_KEY}, {"_id": 1}):
        fs.delete(record["_id"])


def upsert_demo_project() -> dict:
    now = utc_now()

    project = db.projects.find_one({"demoSeedKey": SEED_KEY})

    fields = {
        "name": PROJECT_NAME,
        "state": "Maharashtra",
        "district": "Raigad",
        "stage": "Compensation",
        "progress": 68.0,
        "description": (
            "ILLUSTRATIVE DEMO RECORD. This project exists only to demonstrate "
            "LIVA's end-to-end land-acquisition workflow, GIS, documents, "
            "litigation, compensation, rehabilitation, actions, risk intelligence "
            "and Digital Twin features. It is not an official infrastructure record."
        ),
        "sector": "Road Transport & Highways",
        "line_ministry": "Ministry of Road Transport & Highways",
        "original_cost_cr": 850.0,
        "expenditure_cr": 410.0,
        "physical_progress_pct": 68.0,
        "original_completion_year": 2028,
        "sanction_year": 2024,
        "latitude": 18.9894,
        "longitude": 73.1175,
        "locationDisplayName": (
            "Illustrative demo location near Panvel, Raigad, Maharashtra, India"
        ),
        "locationSource": "LIVA demo seed — illustrative coordinate",
        "image": "/images/liva-land.png",
        "imagePublicId": None,
        "isDemo": True,
        "sourceName": "LIVA Illustrative Demo Dataset",
        "sourceUrl": None,
        "sourceRecordId": PROJECT_RECORD_ID,
        "sourceDate": None,
        "demoSeedKey": SEED_KEY,
        "updatedAt": now,
    }

    if project is None:
        fields["createdAt"] = now
        result = db.projects.insert_one(fields)
        project = db.projects.find_one({"_id": result.inserted_id})
    else:
        db.projects.update_one(
            {"_id": project["_id"]},
            {"$set": fields},
        )
        project = db.projects.find_one({"_id": project["_id"]})

    if project is None:
        raise RuntimeError("Could not create the demo project.")

    return project


def seed_parcels(project_id: str) -> list[dict]:
    now = utc_now()

    parcel_specs = [
        {
            "surveyNumber": "DEMO-101A",
            "village": "Illustrative Village A",
            "district": "Raigad",
            "areaHa": 3.20,
            "ownership": "Verified",
            "stage": "Compensation",
            "ownershipReview": {
                "status": "Verified",
                "officer": "Demo Land Officer",
                "reviewDate": iso_date(-28),
                "remarks": (
                    "Illustrative demo review: ownership documents were marked "
                    "verified for workflow demonstration only."
                ),
                "updatedAt": now,
            },
            "surveyReview": {
                "status": "Approved",
                "officer": "Demo Survey Officer",
                "reviewDate": iso_date(-31),
                "remarks": (
                    "Illustrative demo survey record. Measurements are not real "
                    "land-record evidence."
                ),
                "measuredAreaHa": 3.18,
                "updatedAt": now,
            },
        },
        {
            "surveyNumber": "DEMO-102B",
            "village": "Illustrative Village B",
            "district": "Raigad",
            "areaHa": 2.45,
            "ownership": "Verified",
            "stage": "Award",
            "ownershipReview": {
                "status": "Verified",
                "officer": "Demo Land Officer",
                "reviewDate": iso_date(-18),
                "remarks": "Illustrative ownership verification for the LIVA demo.",
                "updatedAt": now,
            },
            "surveyReview": {
                "status": "Field work completed",
                "officer": "Demo Survey Officer",
                "reviewDate": iso_date(-21),
                "remarks": "Illustrative field-work completion for the LIVA demo.",
                "measuredAreaHa": 2.44,
                "updatedAt": now,
            },
        },
        {
            "surveyNumber": "DEMO-103C",
            "village": "Illustrative Village C",
            "district": "Raigad",
            "areaHa": 1.85,
            "ownership": "Disputed",
            "stage": "Verification",
            "ownershipReview": {
                "status": "Disputed",
                "officer": "Demo Land Officer",
                "reviewDate": iso_date(-8),
                "remarks": (
                    "Illustrative dispute added to demonstrate escalation, "
                    "litigation and action workflows."
                ),
                "updatedAt": now,
            },
            "surveyReview": {
                "status": "Under review",
                "officer": "Demo Survey Officer",
                "reviewDate": iso_date(-9),
                "remarks": "Illustrative re-check pending for demo purposes.",
                "measuredAreaHa": 1.83,
                "updatedAt": now,
            },
        },
    ]

    created: list[dict] = []

    for spec in parcel_specs:
        document = {
            "projectId": project_id,
            **spec,
            "isDemo": True,
            "sourceName": None,
            "sourceUrl": None,
            "sourceRecordId": None,
            "sourceDate": None,
            "demoSeedKey": SEED_KEY,
            "createdAt": now,
            "updatedAt": now,
        }
        result = db.parcels.insert_one(document)
        document["_id"] = result.inserted_id
        created.append(document)

    return created


def seed_documents(project_id: str) -> list[str]:
    fs = GridFS(db, collection="document_files")

    documents = [
        (
            "DEMO_Survey_Verification_Note.pdf",
            "Survey drawing",
            "LIVA Demo — Survey Verification Note",
            [
                "Illustrative demo document. Not an official survey record.",
                "Parcel: DEMO-101A",
                "Status: Survey review approved",
                "Purpose: demonstrate LIVA document workflow.",
            ],
        ),
        (
            "DEMO_Acquisition_Notice.pdf",
            "Acquisition notice",
            "LIVA Demo — Acquisition Notice",
            [
                "Illustrative demo document. Not a statutory acquisition notice.",
                "Linked project: LIVA End-to-End Demo Corridor",
                "Purpose: demonstrate notice storage and retrieval.",
            ],
        ),
        (
            "DEMO_Compensation_Statement.pdf",
            "Compensation record",
            "LIVA Demo — Compensation Statement",
            [
                "Illustrative demo document. Amounts are fictional demo values.",
                "Award reference: DEMO-AWARD-001",
                "Purpose: demonstrate compensation evidence workflow.",
            ],
        ),
        (
            "DEMO_Possession_Readiness_Checklist.pdf",
            "Other",
            "LIVA Demo — Possession Readiness Checklist",
            [
                "Illustrative demo checklist. Not an official possession record.",
                "Shows how a possession-stage evidence file appears in LIVA.",
            ],
        ),
    ]

    created_ids: list[str] = []

    for filename, category, title, lines in documents:
        data = make_demo_pdf(title, lines)

        document_id = fs.put(
            data,
            filename=filename,
            metadata={
                "projectId": project_id,
                "category": category,
                "contentType": "application/pdf",
                "isDemo": True,
                "archived": False,
                "demoSeedKey": SEED_KEY,
            },
        )
        created_ids.append(str(document_id))

    return created_ids


def seed_litigation(project_id: str, disputed_parcel_id: str) -> str:
    now = utc_now()

    document = {
        "projectId": project_id,
        "parcelId": disputed_parcel_id,
        "title": "Illustrative ownership-title clarification",
        "reference": "DEMO-CASE-001",
        "court": "Illustrative District Court",
        "status": "Pending",
        "filedOn": iso_date(-45),
        "nextHearing": iso_date(21),
        "officer": "Demo Legal Officer",
        "notes": (
            "ILLUSTRATIVE DEMO CASE. This is not a real court matter. "
            "It exists only to demonstrate litigation-linked delay monitoring."
        ),
        "isDemo": True,
        "sourceName": None,
        "sourceUrl": None,
        "demoSeedKey": SEED_KEY,
        "createdAt": now,
        "updatedAt": now,
    }

    return str(db.litigation.insert_one(document).inserted_id)


def seed_compensation(project_id: str, parcels: list[dict]) -> list[str]:
    now = utc_now()

    specs = [
        {
            "parcelId": str(parcels[0]["_id"]),
            "reference": "DEMO-AWARD-001",
            "beneficiaryReference": "DEMO-BEN-001",
            "approved": 1250000.00,
            "disbursed": 900000.00,
            "officer": "Demo Compensation Officer",
            "lastPaymentDate": iso_date(-12),
            "notes": (
                "Illustrative compensation amount for demonstration only; "
                "not linked to a real beneficiary."
            ),
        },
        {
            "parcelId": str(parcels[1]["_id"]),
            "reference": "DEMO-AWARD-002",
            "beneficiaryReference": "DEMO-BEN-002",
            "approved": 980000.00,
            "disbursed": 0.00,
            "officer": "Demo Compensation Officer",
            "lastPaymentDate": None,
            "notes": "Illustrative pending disbursement for workflow demonstration.",
        },
    ]

    ids: list[str] = []

    for spec in specs:
        document = {
            "projectId": project_id,
            **spec,
            "isDemo": True,
            "sourceName": None,
            "sourceUrl": None,
            "demoSeedKey": SEED_KEY,
            "createdAt": now,
            "updatedAt": now,
        }
        ids.append(str(db.compensation.insert_one(document).inserted_id))

    return ids


def seed_rehabilitation(project_id: str, parcels: list[dict]) -> list[str]:
    now = utc_now()

    specs = [
        {
            "parcelId": str(parcels[0]["_id"]),
            "familyReference": "DEMO-FAMILY-001",
            "milestone": "Eligibility assessment completed",
            "status": "Approved",
            "officer": "Demo R&R Officer",
            "targetDate": iso_date(14),
            "notes": (
                "Illustrative R&R record. No real household or personal data "
                "is represented."
            ),
        },
        {
            "parcelId": str(parcels[1]["_id"]),
            "familyReference": "DEMO-FAMILY-002",
            "milestone": "Relocation assistance review",
            "status": "Under review",
            "officer": "Demo R&R Officer",
            "targetDate": iso_date(30),
            "notes": "Illustrative R&R milestone for end-to-end demo.",
        },
    ]

    ids: list[str] = []

    for spec in specs:
        document = {
            "projectId": project_id,
            **spec,
            "isDemo": True,
            "sourceName": None,
            "sourceUrl": None,
            "demoSeedKey": SEED_KEY,
            "createdAt": now,
            "updatedAt": now,
        }
        ids.append(str(db.rehabilitation.insert_one(document).inserted_id))

    return ids


def seed_actions(project_id: str, parcels: list[dict]) -> list[str]:
    now = utc_now()

    specs = [
        {
            "parcelId": str(parcels[2]["_id"]),
            "title": "Resolve demo ownership discrepancy",
            "officer": "Demo Land Officer",
            "status": "Open",
            "priority": "High",
            "dueDate": iso_date(-3),
            "notes": (
                "Illustrative overdue task linked to disputed parcel DEMO-103C."
            ),
        },
        {
            "parcelId": str(parcels[1]["_id"]),
            "title": "Complete award verification checklist",
            "officer": "Demo Project Officer",
            "status": "In progress",
            "priority": "High",
            "dueDate": iso_date(5),
            "notes": "Illustrative in-progress action for award-stage workflow.",
        },
        {
            "parcelId": str(parcels[0]["_id"]),
            "title": "Confirm next compensation tranche",
            "officer": "Demo Compensation Officer",
            "status": "Blocked",
            "priority": "Medium",
            "dueDate": iso_date(10),
            "notes": "Illustrative blocker used to demonstrate action escalation.",
        },
        {
            "parcelId": str(parcels[0]["_id"]),
            "title": "Upload survey verification note",
            "officer": "Demo Survey Officer",
            "status": "Completed",
            "priority": "Low",
            "dueDate": iso_date(-10),
            "notes": "Illustrative completed task for board/list views.",
        },
    ]

    ids: list[str] = []

    for spec in specs:
        document = {
            "projectId": project_id,
            **spec,
            "isDemo": True,
            "sourceName": None,
            "sourceUrl": None,
            "demoSeedKey": SEED_KEY,
            "createdAt": now,
            "updatedAt": now,
        }
        ids.append(str(db.actions.insert_one(document).inserted_id))

    return ids


def seed_simulation_history(project_id: str) -> str:
    """
    Adds one clearly labelled illustrative history row.

    The actual ML prediction endpoint remains model-driven.
    This seeded history row is only for demonstrating the saved-history UI.
    """
    now = utc_now()

    document = {
        "project_id": project_id,
        "project_name": PROJECT_NAME,
        "current_risk_score": 72.0,
        "simulated_risk_score": 49.0,
        "current_risk_level": "HIGH",
        "simulated_risk_level": "MEDIUM",
        "score_change": -23.0,
        "risk_reduction_points": 23.0,
        "direction": "IMPROVED",
        "applied_changes": {
            "ownership_disputes_resolved": 1,
            "pending_documents_closed": 2,
            "coordination_meeting_completed": True,
        },
        "summary": (
            "ILLUSTRATIVE DEMO HISTORY: shows how an intervention result appears. "
            "It is not a measured or official project outcome."
        ),
        "demoSeedKey": SEED_KEY,
        "isDemo": True,
        "created_at": now,
    }

    return str(db.simulation_runs.insert_one(document).inserted_id)


def verify(project_id: str) -> dict:
    file_records = db["document_files.files"]

    return {
        "projectId": project_id,
        "projects": db.projects.count_documents({"demoSeedKey": SEED_KEY}),
        "parcels": db.parcels.count_documents({"demoSeedKey": SEED_KEY}),
        "documents": file_records.count_documents(
            {"metadata.demoSeedKey": SEED_KEY, "metadata.archived": {"$ne": True}}
        ),
        "litigation": db.litigation.count_documents({"demoSeedKey": SEED_KEY}),
        "compensation": db.compensation.count_documents({"demoSeedKey": SEED_KEY}),
        "rehabilitation": db.rehabilitation.count_documents(
            {"demoSeedKey": SEED_KEY}
        ),
        "actions": db.actions.count_documents({"demoSeedKey": SEED_KEY}),
        "simulationRuns": db.simulation_runs.count_documents(
            {"demoSeedKey": SEED_KEY}
        ),
    }


def main() -> None:
    print("\nLIVA COMPLETE DEMO SEED")
    print("=" * 64)
    print("All inserted records are illustrative and marked as DEMO.")
    print("Official/source-backed projects are not modified.\n")

    project = upsert_demo_project()
    project_id = str(project["_id"])

    cleanup_previous_seed(project_id)

    # Keep the project itself, then refresh its timestamp after cleanup.
    db.projects.update_one(
        {"_id": project["_id"]},
        {
            "$set": {
                "demoSeedKey": SEED_KEY,
                "updatedAt": utc_now(),
            }
        },
    )

    parcels = seed_parcels(project_id)
    document_ids = seed_documents(project_id)
    case_id = seed_litigation(
        project_id,
        str(parcels[2]["_id"]),
    )
    compensation_ids = seed_compensation(project_id, parcels)
    rehabilitation_ids = seed_rehabilitation(project_id, parcels)
    action_ids = seed_actions(project_id, parcels)
    simulation_id = seed_simulation_history(project_id)

    counts = verify(project_id)

    print("Seed completed successfully.")
    print(f"Project: {PROJECT_NAME}")
    print(f"Project ID: {project_id}")
    print(f"Project Lens: /projects/{project_id}")
    print(f"Intelligence: /intelligence?project={project_id}")
    print(f"Simulator: /simulator?projectId={project_id}")
    print(f"GIS: /dashboard?gisProject={project_id}")
    print()
    print("Created/verified demo records:")
    for key, value in counts.items():
        print(f"  {key}: {value}")

    print()
    print(f"Document IDs: {len(document_ids)}")
    print(f"Litigation ID: {case_id}")
    print(f"Compensation records: {len(compensation_ids)}")
    print(f"R&R records: {len(rehabilitation_ids)}")
    print(f"Action records: {len(action_ids)}")
    print(f"Simulation history ID: {simulation_id}")
    print()
    print(
        "NOTE: Risk Intelligence itself is NOT fake-seeded. "
        "Open Intelligence for this demo project so your trained official-data "
        "model computes the prediction from the project's demo feature values."
    )


if __name__ == "__main__":
    main()
