"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app.api.routes_approvals import router as approval_router
from app.api.routes_health import router as health_router
from app.api.routes_reports import router as report_router
from app.api.routes_tasks import router as task_router

app = FastAPI(title="Orchestrator API")
app.include_router(health_router)
app.include_router(task_router)
app.include_router(approval_router)
app.include_router(report_router)
