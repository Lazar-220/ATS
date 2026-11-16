from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.api.rankings import router as rankings_router
from ats.db.pool import create_pool
from ats.settings import get_settings


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["reachable", "unreachable"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    pool = create_pool(settings.database_url, settings.db_pool_max_size)
    pool.open(wait=False)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="ATS", lifespan=lifespan)
app.include_router(rankings_router)


def database_reachable(pool: ConnectionPool) -> bool:
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return False
    return True


@app.get("/health")
def health(response: Response) -> Health:
    # A sync endpoint runs in the threadpool, so the blocking pool call does not stall the loop.
    if database_reachable(app.state.pool):
        return Health(status="ok", database="reachable")
    response.status_code = 503
    return Health(status="degraded", database="unreachable")
