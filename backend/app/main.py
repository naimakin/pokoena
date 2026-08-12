from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    activities,
    auth,
    change_requests,
    dashboard,
    invites,
    platform,
    platform_auth,
    projects,
    subcontractor_organizations,
    team,
    update_periods,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="POKO API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(platform_auth.router)
app.include_router(platform.router)
app.include_router(invites.router)
app.include_router(team.router)
app.include_router(subcontractor_organizations.router)
app.include_router(projects.router)
app.include_router(update_periods.router)
app.include_router(activities.router)
app.include_router(change_requests.router)
app.include_router(dashboard.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
