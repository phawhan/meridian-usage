from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import meta
from app.core.config import Settings
from app.db.session import connect, init_db

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    conn = connect(settings.database_file)
    try:
        init_db(conn, settings.app_env)
    finally:
        conn.close()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Meridian usage service", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.include_router(meta.router, prefix=API_PREFIX)
    return app


app = create_app()
