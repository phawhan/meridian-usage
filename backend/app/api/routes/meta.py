from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])


@router.get("/healthz")
def healthz(request: Request) -> dict[str, str]:
    return {"status": "ok", "environment": request.app.state.settings.app_env}
