import json
import os
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from database import db
from ml.mongo_feature_service import build_project_risk_features
from ml.risk_engine import predict_delay_risk

load_dotenv()

AI_MODEL = os.getenv("LIVA_AI_MODEL", "openai/gpt-oss-20b")


SYSTEM_INSTRUCTIONS = """
You are LIVA AI, the intelligent assistant inside the
LIVA Land Acquisition Intelligence System.

Your job is to help government and project officers
understand REAL LIVA project data.

IMPORTANT RULES:

1. Use ONLY the LIVA database context supplied by the backend.

2. Never invent:
   - project facts
   - numbers
   - dates
   - survey numbers
   - landowners
   - parcels
   - court cases
   - compensation records
   - documents
   - approvals
   - actions

3. If requested information is not available in the
   supplied LIVA records, clearly say:

   "This information is not available in the current
   LIVA records."

4. Clearly distinguish between:
   - Observed database data
   - LIVA risk-engine output
   - AI explanation

5. Never describe an AI prediction as guaranteed.

6. Do not infer missing information.

7. Do not create facts from general knowledge.

8. Give concise, professional answers.

9. Use bullet points when useful.

10. Markdown formatting is allowed.

11. Use **bold** for important values, headings and
    important conclusions.

12. When answering a project-specific question, stay
    focused on the selected LIVA project.

13. If the user asks about information that was not
    retrieved because it is unavailable, clearly state
    that it is not available in the current LIVA records.

    ============================================================
TABLE FORMATTING
============================================================

When a comparison or structured list contains multiple
records and a table improves clarity, you MAY use a Markdown
table.

Use this exact format:

| Field | Value |
|---|---|
| Project | C/o NITB Imphal Airport |
| Progress | 49% |
| Risk Level | LOW |

Rules:

1. Always include the header row.
2. Always include the separator row.
3. Keep column names short and clear.
4. Do not create very wide tables.
5. If a table would require too many columns, use bullet
   points instead.
6. Use the user's response language for table headings
   where appropriate.
7. Do not put unsupported information into a table.
8. If a value is unavailable, write:
   "Not available in current LIVA records."
"""


def get_ai_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    return Groq(api_key=api_key)


def _clean_value(value: Any) -> Any:
    """
    Convert MongoDB/BSON values into JSON-safe values.
    """

    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    try:
        from bson import ObjectId

        if isinstance(value, ObjectId):
            return str(value)

    except Exception:
        pass

    if isinstance(value, dict):
        return {
            str(key): _clean_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _clean_value(item)
            for item in value
        ]

    return value


def _get_project(project_id: str) -> dict:
    """
    Retrieve one project from MongoDB.
    """

    from bson import ObjectId

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise LookupError(
            f"Invalid project ID: {project_id}"
        )

    project = db.projects.find_one(
        {"_id": object_id}
    )

    if not project:
        raise LookupError(
            f"Project '{project_id}' was not found."
        )

    return _clean_value(project)


def _get_project_records(project: dict) -> dict:
    """
    Retrieve records linked to the selected project.

    This is the structured-data retrieval layer used
    by LIVA AI.
    """

    project_id = str(project.get("_id"))

    reference_values = [project_id]

    if project.get("_id") is not None:
        reference_values.append(project.get("_id"))

    project_fields = [
        "project_id",
        "projectId",
        "project",
        "parent_project_id",
        "project_ref",
    ]

    linked_query = {
        "$or": [
            {
                field: {
                    "$in": reference_values
                }
            }
            for field in project_fields
        ]
    }

    collection_map = {
        "parcels": [
            "parcels",
            "land_parcels",
        ],

        "ownership": [
            "ownership",
            "ownership_reviews",
            "ownership_review",
        ],

        "surveys": [
            "surveys",
            "survey",
            "survey_reviews",
            "survey_review",
        ],

        "litigation": [
            "litigation",
            "litigations",
            "court_cases",
        ],

        "documents": [
            "documents",
            "project_documents",
        ],

        "compensation": [
            "compensation",
            "compensations",
        ],

        "approvals": [
            "approvals",
            "approval",
        ],

        "actions": [
            "actions",
            "tasks",
        ],
    }

    records: dict[str, list] = {}

    existing_collections = set(
        db.list_collection_names()
    )

    for category, names in collection_map.items():

        selected_collection = None

        for name in names:

            if name in existing_collections:
                selected_collection = db[name]
                break

        if selected_collection is None:
            records[category] = []
            continue

        documents = list(
            selected_collection
            .find(linked_query)
            .limit(50)
        )

        records[category] = [
            _clean_value(document)
            for document in documents
        ]

    return records


def _select_relevant_categories(
    message: str,
) -> list[str]:
    """
    Select relevant structured-data categories based
    on the officer's question.

    The project itself and risk information are always
    included separately.
    """

    text = message.lower()

    selected: set[str] = set()

    keyword_groups = {
        "parcels": [
            "parcel",
            "land parcel",
            "land",
            "acquisition area",
            "acquired area",
            "plot",
        ],

        "ownership": [
            "owner",
            "landowner",
            "ownership",
            "title",
            "ownership issue",
        ],

        "surveys": [
            "survey",
            "survey number",
            "measurement",
            "survey status",
        ],

        "litigation": [
            "litigation",
            "court",
            "case",
            "legal",
            "lawsuit",
            "dispute",
        ],

        "documents": [
            "document",
            "file",
            "record",
            "paperwork",
        ],

        "compensation": [
            "compensation",
            "payment",
            "paid",
            "payout",
            "amount paid",
            "award",
        ],

        "approvals": [
            "approval",
            "approved",
            "permission",
            "sanction",
        ],

        "actions": [
            "action",
            "task",
            "follow-up",
            "follow up",
            "pending action",
            "overdue",
        ],
    }

    for category, keywords in keyword_groups.items():

        if any(
            keyword in text
            for keyword in keywords
        ):
            selected.add(category)

    # General project questions should receive
    # the available project-level records.
    if not selected:
        selected.update(
            [
                "parcels",
                "ownership",
                "surveys",
                "litigation",
                "documents",
                "compensation",
                "approvals",
                "actions",
            ]
        )

    return sorted(selected)


def _build_database_context(
    project_id: str | None,
    message: str,
) -> dict[str, Any]:

    if not project_id:

        return {
            "available": False,
            "message": (
                "No project ID was supplied. "
                "Project-specific LIVA database information "
                "is unavailable."
            ),
        }

    project = _get_project(project_id)

    all_records = _get_project_records(project)

    relevant_categories = (
        _select_relevant_categories(message)
    )

    retrieved_records = {
        category: all_records.get(
            category,
            [],
        )
        for category in relevant_categories
    }

    # Build risk context separately because risk is
    # relevant to most project-intelligence questions.
    risk_features = build_project_risk_features(
        project_id
    )

    risk_features_data = (
        risk_features.model_dump(
            mode="json"
        )
    )

    try:

        risk_result = predict_delay_risk(
            risk_features
        )

        risk_data = (
            risk_result.model_dump(
                mode="json"
            )
        )

    except Exception as exc:

        risk_data = {
            "available": False,
            "error": str(exc),
        }

    return {
        "available": True,

        "retrieval": {
            "method": "structured_database_retrieval",
            "selected_categories": relevant_categories,
        },

        "project": project,

        "risk_features": risk_features_data,

        "liva_risk": risk_data,

        "retrieved_records": {
            category: {
                "count": len(items),
                "records": items,
            }
            for category, items in retrieved_records.items()
        },
    }


def ask_liva_ai(
    message: str,
    project_id: str | None = None,
    project: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> str:

    client = get_ai_client()

    database_context = None

    if project_id:

        database_context = (
            _build_database_context(
                project_id=project_id,
                message=message,
            )
        )

    supplied_context = {
        "project": project,
        "risk": risk,
    }

    user_input = f"""
LIVA RETRIEVED DATABASE CONTEXT
================================

{json.dumps(
    database_context,
    indent=2,
    default=str,
)}

ADDITIONAL CONTEXT
==================

{json.dumps(
    supplied_context,
    indent=2,
    default=str,
)}

OFFICER QUESTION
================

{message}
"""

    response = client.chat.completions.create(
        model=AI_MODEL,

        messages=[
            {
                "role": "system",
                "content": SYSTEM_INSTRUCTIONS,
            },
            {
                "role": "user",
                "content": user_input,
            },
        ],
    )

    answer = (
        response.choices[0]
        .message
        .content
    )

    if not answer:

        return (
            "LIVA AI could not generate a response."
        )

    return answer.strip()