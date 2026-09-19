from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import PyMongoError

from database import db
from workflow_common import (
    decorate,
    list_records,
    oid,
    save_record,
    unavailable,
)
from workflow_models import (
    ActionInput,
    CompensationInput,
    RehabilitationInput,
)

router = APIRouter()


def register(collection, path, model, tag):
    def listing(
        projectId: str | None = None,
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=100),
    ):
        try:
            return list_records(
                collection,
                projectId,
                skip,
                limit,
            )
        except PyMongoError:
            raise unavailable() from None

    def detail(record_id: str):
        try:
            document = db[collection].find_one(
                {"_id": oid(record_id)}
            )

            if document is None:
                raise HTTPException(404, "Record not found.")

            return decorate([document])[0]
        except PyMongoError:
            raise unavailable() from None

    def create(payload):
        try:
            return save_record(collection, payload)
        except PyMongoError:
            raise unavailable() from None

    def update(record_id: str, payload):
        try:
            return save_record(
                collection,
                payload,
                record_id,
            )
        except PyMongoError:
            raise unavailable() from None

    # FastAPI reads these schemas during route registration.
    create.__annotations__["payload"] = model
    update.__annotations__["payload"] = model

    endpoints = [
        ("GET", "", listing, 200),
        ("GET", "/{record_id}", detail, 200),
        ("POST", "", create, 201),
        ("PUT", "/{record_id}", update, 200),
    ]

    for method, suffix, endpoint, status_code in endpoints:
        router.add_api_route(
            path + suffix,
            endpoint,
            methods=[method],
            tags=[tag],
            status_code=status_code,
            name=f"{collection}_{endpoint.__name__}",
        )


register(
    "compensation",
    "/api/compensation",
    CompensationInput,
    "Compensation",
)

register(
    "actions",
    "/api/actions",
    ActionInput,
    "Actions",
)

register(
    "rehabilitation",
    "/api/rehabilitation",
    RehabilitationInput,
    "Rehabilitation",
)