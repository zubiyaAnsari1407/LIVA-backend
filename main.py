import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from database import client, db
from projects import router as projects_router
from parcels import router as parcels_router
from documents import router as documents_router
from ownership_survey import router as ownership_survey_router
from litigation import router as litigation_router
from register_workflows import register_workflows
from risk_routes import router as risk_router
from simulation_routes import router as simulation_router
from geocode_routes import router as geocode_router
from gis_routes import router as gis_router


logger = logging.getLogger("uvicorn.error")


def get_allowed_origins() -> list[str]:
    origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }

    single_origin = os.getenv("FRONTEND_ORIGIN", "").strip()

    if single_origin:
        origins.add(single_origin.rstrip("/"))

    multiple_origins = os.getenv("FRONTEND_ORIGINS", "")

    for origin in multiple_origins.split(","):
        cleaned = origin.strip().rstrip("/")

        if cleaned:
            origins.add(cleaned)

    return sorted(origins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        client.close()


app = FastAPI(
    title="Liva API",
    description="Land Acquisition Intelligence and Decision Support",
    version="0.4.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


app.include_router(projects_router)
app.include_router(parcels_router)
app.include_router(documents_router)
app.include_router(ownership_survey_router)
app.include_router(litigation_router)
app.include_router(risk_router)

register_workflows(app)

app.include_router(simulation_router)
app.include_router(geocode_router)
app.include_router(gis_router)


@app.get("/")
def root():
    return {
        "message": "Liva API is running",
        "phase": "Deployment-ready prototype",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "liva-api",
    }


@app.get("/api/health/database")
def database_health():
    try:
        client.admin.command("ping")

        return {
            "status": "ok",
            "database": db.name,
            "message": "MongoDB connected successfully",
        }

    except PyMongoError:
        logger.warning("MongoDB health check failed")

        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "message": "MongoDB connection failed.",
            },
        )