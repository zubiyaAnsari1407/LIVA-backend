from fastapi import FastAPI

from workflow_reports import router as report_router
from workflow_routes import router as workflow_router


def register_workflows(app: FastAPI):
    if getattr(app.state, "liva_workflows_registered", False):
        return

    app.include_router(workflow_router)
    app.include_router(report_router)

    app.state.liva_workflows_registered = True