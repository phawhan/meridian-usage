from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.deps import Unidentified
from app.api.routes import capabilities, directory, me, meta, usage
from app.core.config import Settings
from app.core.env_config import load_policy
from app.db.session import connect, init_db
from app.models.denial import Unidentified as UnidentifiedBody
from app.services.authz import AccessDenied
from app.services.sync import run_sync

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    policy = load_policy(settings)  # invalid environment config: refuse to start
    conn = connect(settings.database_file)
    try:
        init_db(conn, settings.app_env)
        report = run_sync(conn, settings, policy, trigger="startup")
    finally:
        conn.close()
    app.state.policy = policy
    app.state.policy_file_id = report.policy_file_id
    yield


async def _denied(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AccessDenied)
    return JSONResponse(status_code=403, content=exc.denial.model_dump(exclude_none=True))


async def _unidentified(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=401, content=UnidentifiedBody(reason=str(exc)).model_dump())


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Meridian usage service", version=version("meridian-usage"), lifespan=lifespan
    )
    app.state.settings = settings or Settings()
    app.add_exception_handler(AccessDenied, _denied)
    app.add_exception_handler(Unidentified, _unidentified)
    app.include_router(meta.router, prefix=API_PREFIX)
    for router in (me.router, usage.router, capabilities.router, directory.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
