from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.access import many_groups, one_group
from app.api.deps import Caller, CurrentPolicy, Db, RequestChannel, connector_gate
from app.core.periods import PERIOD_PATTERN, DataWindow, Period, PeriodError, resolve
from app.models.api import Breakdown, Dimension, TopUser, UsageSummary
from app.repositories.usage import DIMENSION_COLUMNS
from app.services import usage
from app.services.usage import data_window

router = APIRouter(prefix="/usage", tags=["usage"], dependencies=[Depends(connector_gate)])

PeriodParam = Annotated[
    str,
    Query(
        pattern=PERIOD_PATTERN,
        description="last_7_days | last_30_days | ISO week (2026-W36) | month (2026-09);"
        " relative periods end at the newest usage day",
    ),
]
GroupParam = Annotated[str | None, Query(description="group_id; omitted: see each endpoint")]


def _period(label: str, window: DataWindow) -> Period:
    try:
        return resolve(label, window)
    except PeriodError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary", response_model=UsageSummary)
def summary(
    caller: Caller,
    channel: RequestChannel,
    policy: CurrentPolicy,
    conn: Db,
    period: PeriodParam,
    group: GroupParam = None,
) -> UsageSummary:
    """Tokens and cost per platform for one group. Omitted group: the caller's own."""
    group_id = one_group(conn, caller, "read_usage", policy, group, channel)
    window = data_window(conn)
    return usage.summary(conn, group_id, _period(period, window), window)


@router.get("/breakdown", response_model=Breakdown)
def breakdown(
    caller: Caller,
    channel: RequestChannel,
    policy: CurrentPolicy,
    conn: Db,
    period: PeriodParam,
    group: GroupParam = None,
    by: Annotated[
        str, Query(description=f"comma-separated, from: {', '.join(DIMENSION_COLUMNS)}")
    ] = "platform",
) -> Breakdown:
    """Tokens and cost sliced by any of platform, group, week, month, model, product.
    Omitted group: every group the caller may see."""
    dimensions = [d.strip() for d in by.split(",") if d.strip()]
    unknown = [d for d in dimensions if d not in DIMENSION_COLUMNS]
    if unknown or len(set(dimensions)) != len(dimensions):
        raise HTTPException(
            status_code=422,
            detail=f"'by' takes distinct values from {', '.join(DIMENSION_COLUMNS)}; got {by!r}",
        )
    groups = many_groups(conn, caller, "read_usage", policy, group, channel)
    window = data_window(conn)
    dims: list[Dimension] = dimensions  # type: ignore[assignment]  # validated above
    return usage.breakdown(conn, groups, _period(period, window), window, dims)


@router.get("/top-users", response_model=list[TopUser])
def top_users(
    caller: Caller,
    channel: RequestChannel,
    policy: CurrentPolicy,
    conn: Db,
    period: PeriodParam,
    group: GroupParam = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[TopUser]:
    """Heaviest users by total tokens. Omitted group: every group the caller may see."""
    groups = many_groups(conn, caller, "read_usage", policy, group, channel)
    return usage.top_users(conn, groups, _period(period, data_window(conn)), limit)
