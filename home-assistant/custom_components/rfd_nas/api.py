"""Client dell'API v1 del NAS (chiave API in X-API-Key)."""
from __future__ import annotations

import aiohttp


class NasError(Exception):
    """Errore di comunicazione con il NAS."""


class NasAuthError(NasError):
    """Chiave API errata."""


class NasApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, key: str, ssl: bool, verify: bool) -> None:
        self._s, self._key = session, key
        self._base = f"{'https' if ssl else 'http'}://{host}/api/v1"
        self._ssl = None if (ssl and verify) else False

    async def _req(self, method: str, path: str) -> dict:
        try:
            async with self._s.request(method, self._base + path, headers={"X-API-Key": self._key},
                                       ssl=self._ssl, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 401:
                    raise NasAuthError("chiave API errata")
                data = await r.json(content_type=None)
                if r.status >= 400:
                    raise NasError((data or {}).get("error") or f"HTTP {r.status}")
                return data or {}
        except (aiohttp.ClientError, TimeoutError) as e:
            raise NasError(str(e)) from e

    async def status(self) -> dict:
        return await self._req("GET", "/status")

    async def post(self, path: str) -> dict:
        return await self._req("POST", path)
