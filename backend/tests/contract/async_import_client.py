"""Legacy contract adapter that completes the new real JobWorker in old API tests."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.worker.service import JobWorker


class CompletingImportClient(httpx.AsyncClient):
    """Let pre-M1 assertions inspect a terminal response after a real queued run."""

    def __init__(self, *, worker: JobWorker, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._import_worker = worker

    async def request(self, method: str, url: httpx._types.URLTypes, **kwargs: Any):
        response = await super().request(method, url, **kwargs)
        path = str(url)
        if (
            method.upper() != "POST"
            or "/sessions/" not in path
            or not path.endswith("/messages")
            or response.status_code != 202
        ):
            return response
        accepted = response.json()
        await self._import_worker.run_once()
        result = await self._wait_for_result(str(accepted["result_url"]))
        body = result.json()
        error_code = body.get("error_code")
        run_status = body.get("run_status")
        if run_status in {"failed", "cancelled"}:
            status = (
                504
                if error_code == "RUN_TIMEOUT"
                else 502
                if str(error_code).startswith("PROVIDER_")
                else 500
            )
            return httpx.Response(
                status,
                json={
                    "error_code": error_code,
                    "message": "The import did not complete.",
                    "trace_id": body.get("trace_id"),
                    "issues": [],
                    "recovery_actions": body.get("recovery_actions", []),
                },
                request=response.request,
            )
        body.setdefault("undo_token", None)
        body.setdefault("undo_expires_at", None)
        body["replayed"] = bool(accepted.get("replayed"))
        return httpx.Response(
            200,
            json=body,
            headers={"X-Request-ID": response.headers.get("X-Request-ID", "")},
            request=response.request,
        )

    async def _wait_for_result(self, path: str) -> httpx.Response:
        for _ in range(200):
            result = await super().request("GET", path)
            if result.status_code != 200:
                return result
            if result.json().get("run_status") not in {"queued", "running"}:
                return result
            await self._import_worker.run_once()
            await asyncio.sleep(0.01)
        raise AssertionError("queued content import did not reach a terminal state")
