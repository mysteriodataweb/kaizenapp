"""Client HTTP respectueux des sources : User-Agent identifiable, délai minimal par hôte,
respect de robots.txt pour les pages HTML, gestion de Retry-After, aucune tentative de
contournement (CAPTCHA, authentification, anti-bot)."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.collector.http")


class ConnectorError(Exception):
    """Erreur bloquante pour une source (réseau, format inattendu, accès refusé)."""


class AccessDenied(ConnectorError):
    """La source refuse l'accès (robots.txt, 401/403, CAPTCHA) : on s'arrête, sans contournement."""


class PoliteClient:
    def __init__(
        self,
        *,
        min_delay: float = 2.0,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 2,
        sleep=time.sleep,  # type: ignore[no-untyped-def]
    ):
        settings = get_settings()
        self.user_agent = settings.collector_user_agent
        self.min_delay = min_delay
        self.max_retries = max_retries
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.client = httpx.Client(
            timeout=timeout or settings.collector_timeout_seconds,
            headers={"User-Agent": self.user_agent, "Accept-Language": "fr,en;q=0.8"},
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_delay - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = time.monotonic()

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                self._throttle(parts.netloc)
                resp = self.client.get(base + "/robots.txt")
                if resp.status_code >= 400:
                    parser = None  # pas de robots.txt : pas de restriction déclarée
                else:
                    assert parser is not None
                    parser.parse(resp.text.splitlines())
            except httpx.HTTPError:
                parser = None
            self._robots[base] = parser
        parser = self._robots[base]
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def get(self, url: str, *, params: dict | None = None, check_robots: bool = False) -> httpx.Response:
        if check_robots and not self.allowed_by_robots(url):
            raise AccessDenied(f"robots.txt interdit l'accès à {url}")
        host = urlsplit(url).netloc
        attempt = 0
        while True:
            self._throttle(host)
            try:
                resp = self.client.get(url, params=params)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    self._sleep(2**attempt)
                    continue
                raise ConnectorError(f"Délai dépassé pour {host}") from exc
            except httpx.HTTPError as exc:
                raise ConnectorError(f"Erreur réseau pour {host} : {exc.__class__.__name__}") from exc
            if resp.status_code in (429, 502, 503, 504) and attempt < self.max_retries:
                attempt += 1
                retry_after = resp.headers.get("retry-after", "")
                delay = float(retry_after) if retry_after.isdigit() else 2**attempt * 2
                self._sleep(min(delay, 60))
                continue
            if resp.status_code in (401, 403):
                raise AccessDenied(f"Accès refusé par {host} (HTTP {resp.status_code}) — aucun contournement tenté.")
            if resp.status_code == 404:
                raise ConnectorError(f"Ressource introuvable (HTTP 404) : {url}")
            if resp.status_code >= 400:
                raise ConnectorError(f"HTTP {resp.status_code} pour {host}")
            if "captcha" in resp.text[:5000].lower() and "text/html" in resp.headers.get("content-type", ""):
                raise AccessDenied(f"{host} présente un CAPTCHA — collecte arrêtée sans contournement.")
            return resp

    def get_json(self, url: str, *, params: dict | None = None) -> object:
        resp = self.get(url, params=params)
        try:
            return resp.json()
        except ValueError as exc:
            raise ConnectorError(f"Réponse JSON invalide de {urlsplit(url).netloc}") from exc
