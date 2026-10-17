"""HTTP client for the Part A service, as the connector's fixed user.

Every request carries X-User-Id (the user the connector was started as) and X-Channel:
connector, so the service applies the usage-connector switch and logs refusals against the
connector. A refusal comes back as a Denial value, never as data; anything else that isn't
a 200 is a ServiceError, so a failure can't be mistaken for an empty answer.
"""

from typing import Any

import httpx2

from app.models.denial import Denial


class ServiceError(Exception):
    """The service could not answer: unreachable, timed out, or an unexpected status."""


class UsageService:
    def __init__(
        self,
        base_url: str,
        user_id: str,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._http = httpx2.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/v1",
            headers={"X-User-Id": user_id, "X-Channel": "connector"},
            transport=transport,
            timeout=timeout,
        )

    @property
    def base_url(self) -> str:
        return str(self._http.base_url)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, **params: Any) -> Any | Denial:
        query = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", path, params=query)

    async def put(self, path: str, body: dict[str, Any]) -> Any | Denial:
        return await self._request("PUT", path, json=body)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any | Denial:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            raise ServiceError(f"usage service unreachable ({type(exc).__name__})") from exc
        if response.status_code == 200:
            return response.json()
        if response.status_code == 403:
            try:
                return Denial.model_validate(response.json())  # keeps required_scope
            except ValueError as exc:
                raise ServiceError(f"usage service sent a malformed refusal: {exc}") from exc
        if response.status_code == 401:
            # Mid-session, this means the user was deactivated after the connector started.
            return Denial(reason=_detail(response))
        raise ServiceError(f"usage service answered {response.status_code}: {_detail(response)}")


def _detail(response: httpx2.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("reason") or body.get("detail") or body)
    return str(body)
