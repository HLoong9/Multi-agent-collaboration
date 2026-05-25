"""FastAPI application entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_approvals import router as approval_router
from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.api.routes_reports import router as report_router
from app.api.routes_tasks import router as task_router

app = FastAPI(title="Orchestrator API")
app.include_router(health_router)
app.include_router(task_router)
app.include_router(approval_router)
app.include_router(report_router)
app.include_router(chat_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
@app.get("/chat", include_in_schema=False)
async def orchestrator_chat() -> FileResponse:
    return FileResponse(static_dir / "chat.html")
