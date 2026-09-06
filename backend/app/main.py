import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    activities,
    activity_codes,
    auth,
    change_requests,
    dashboard,
    dcma,
    evm,
    export,
    invites,
    logic_diff,
    metadata,
    password_reset,
    platform,
    platform_auth,
    projects,
    risk,
    schedule_imports,
    subcontractor_organizations,
    sync,
    team,
    update_periods,
    wbs,
)
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title="POKO API", version="0.1.0")


# Registered *before* CORSMiddleware below deliberately: Starlette's
# middleware order is last-added-is-outermost, and an @app.exception_handler
# for a bare Exception (or status 500) is wired into ServerErrorMiddleware —
# which is always the outermost layer, outside every add_middleware() call,
# CORS included (see starlette.applications.build_middleware_stack). A
# handler registered that way would never let CORSMiddleware see or tag its
# response. A plain HTTP middleware here instead sits *inside* CORSMiddleware
# as long as it's added first, so when it catches an unhandled exception and
# returns a normal JSONResponse, that response still flows back out through
# CORSMiddleware and gets tagged correctly. Without this, any unhandled
# exception anywhere in the app reaches the browser with no CORS headers at
# all, which Chrome/Firefox report as "blocked by CORS policy" — hiding the
# real 500 behind a misleading, undiagnosable error.
@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
app.include_router(password_reset.router)
app.include_router(team.router)
app.include_router(subcontractor_organizations.router)
app.include_router(projects.router)
app.include_router(update_periods.router)
app.include_router(activities.router)
app.include_router(schedule_imports.router)
app.include_router(sync.router)
app.include_router(dcma.router)
app.include_router(evm.router)
app.include_router(risk.router)
app.include_router(logic_diff.router)
app.include_router(export.router)
app.include_router(wbs.router)
app.include_router(activity_codes.router)
app.include_router(metadata.router)
app.include_router(change_requests.router)
app.include_router(dashboard.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
