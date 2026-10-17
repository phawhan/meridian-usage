from datetime import date, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import Db
from app.core.timestamps import iso_week, month
from app.services.usage import data_window

router = APIRouter(tags=["meta"])


@router.get("/healthz")
def healthz(request: Request) -> dict[str, str]:
    """Liveness, plus the environment and the hash of the policy file in force, so the
    connector can refuse to start against a service running different rules."""
    return {
        "status": "ok",
        "environment": request.app.state.settings.app_env,
        "policy_sha256": request.app.state.policy.sha256,
    }


class Periods(BaseModel):
    data_from: date
    data_to_exclusive: date
    periods: list[str]  # newest first: relative periods, then months, then ISO weeks


@router.get("/periods", response_model=Periods)
def periods(conn: Db) -> Periods:
    """Period labels the data covers, for pickers. Not access-controlled: it reveals only the
    date range of the data, never usage."""
    window = data_window(conn)
    days = [
        window.start + timedelta(days=i) for i in range((window.end_exclusive - window.start).days)
    ]
    months = sorted({month(d) for d in days}, reverse=True)
    weeks = sorted({iso_week(d) for d in days}, reverse=True)
    return Periods(
        data_from=window.start,
        data_to_exclusive=window.end_exclusive,
        periods=["last_7_days", "last_30_days", *months, *weeks],
    )
