"""Client for the Alcedo NVR app API (local network / Supervisor network)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=20)


class AlcedoError(Exception):
    """Communication problem."""


class AlcedoAuthError(AlcedoError):
    """API key rejected."""


class AlcedoClient:
    """Thin async client. The API key is sent as Bearer header only."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, api_key: str) -> None:
        self._session = session
        self.base = f"http://{host}:{port}/api"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method, f"{self.base}{path}", headers=self._headers, timeout=TIMEOUT, **kwargs
            ) as resp:
                if resp.status == 401:
                    raise AlcedoAuthError("API key rejected")
                if resp.status in (400, 409):
                    raise AlcedoError((await resp.text())[:300] or f"HTTP {resp.status}")
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.read()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise AlcedoError(f"{path}: {err or type(err).__name__}") from err

    async def info(self) -> dict[str, Any]:
        return await self._request("GET", "/info")

    async def events(self, limit: int = 50, camera: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if camera:
            params["camera"] = camera
        return await self._request("GET", "/events", params=params)

    async def cameras(self) -> list[dict[str, Any]]:
        """All cameras of the app (without credentials)."""
        return await self._request("GET", "/cameras")

    async def add_cameras(self, cameras: list[dict[str, Any]]) -> dict[str, Any]:
        """Add cameras taken over from Home Assistant (the app restarts its cameras)."""
        return await self._request("POST", "/cameras", json={"cameras": cameras})

    async def remove_camera(self, camera: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/cameras/{camera}")

    async def camera_snapshot(self, camera: str) -> bytes:
        return await self._request("GET", f"/cameras/{camera}/snapshot.jpg")

    async def camera_stream(self, camera: str) -> dict[str, str]:
        return await self._request("GET", f"/cameras/{camera}/stream")

    async def set_detection(self, camera: str, enabled: bool) -> None:
        await self._request("POST", f"/cameras/{camera}/detection", json={"enabled": enabled})

    async def trigger(self, camera: str, label: str) -> None:
        """Start (or extend) an event, e.g. from a Ring motion sensor."""
        await self._request("POST", f"/hook/{camera}", params={"label": label})

    async def timeline(self, start: float, end: float) -> dict[str, Any]:
        return await self._request("GET", "/timeline", params={"start": start, "end": end})

    async def timelapse(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/timelapse", json=body)

    async def timelapse_status(self, job: str) -> dict[str, Any]:
        return await self._request("GET", f"/timelapse/{job}")

    async def open_path(
        self, path: str, params: dict[str, Any] | None = None
    ) -> aiohttp.ClientResponse:
        """Open any media path of the app API (caller must release the response)."""
        resp = await self._session.get(
            f"{self.base}/{path}",
            params=params,
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=300),
        )
        if resp.status != 200:
            resp.release()
            raise AlcedoError(f"HTTP {resp.status}")
        return resp

    async def open_file(self, event_id: str, kind: str) -> aiohttp.ClientResponse:
        """Open a snapshot / clip download (caller must release the response)."""
        name = "clip.mp4" if kind == "clip" else "snapshot.jpg"
        resp = await self._session.get(
            f"{self.base}/events/{event_id}/{name}",
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        )
        if resp.status != 200:
            resp.release()
            raise AlcedoError(f"HTTP {resp.status}")
        return resp

    async def listen(
        self,
        on_message: Callable[[dict[str, Any]], Awaitable[None] | None],
        on_state: Callable[[bool], None],
    ) -> None:
        """Keep a WebSocket open for push events (reconnects forever)."""
        backoff = 2.0
        while True:
            try:
                async with self._session.ws_connect(
                    f"{self.base}/ws", headers=self._headers, heartbeat=30
                ) as ws:
                    on_state(True)
                    backoff = 2.0
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            result = on_message(json.loads(msg.data))
                            if asyncio.iscoroutine(result):
                                await result
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("Alcedo WebSocket error: %s", err)
            on_state(False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
