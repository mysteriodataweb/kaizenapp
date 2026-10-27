"""Envoi d'e-mails via Resend, ou simulation si RESEND_API_KEY / EMAIL_FROM sont absents."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import log_event

logger = logging.getLogger("app.email")
RESEND_URL = "https://api.resend.com/emails"


@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str
    idempotency_key: str


@dataclass
class EmailResult:
    status: str  # sent | simulated | failed
    provider: str
    message_id: str | None = None
    error: str | None = None
    retryable: bool = False


class EmailClient(Protocol):
    provider: str

    def send(self, message: EmailMessage) -> EmailResult: ...


class SimulationEmailClient:
    """Aucun e-mail externe n'est envoyé : le message est seulement journalisé."""

    provider = "simulation"

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailResult:
        self.outbox.append(message)
        log_event(logger, "email simulated", subject=message.subject, to_domain=message.to.split("@")[-1])
        return EmailResult(status="simulated", provider=self.provider, message_id=None)


class ResendEmailClient:
    provider = "resend"

    def __init__(self, api_key: str, sender: str, transport: httpx.BaseTransport | None = None, sleep=time.sleep):  # type: ignore[no-untyped-def]
        self.sender = sender
        self._sleep = sleep
        self.client = httpx.Client(timeout=15, headers={"Authorization": f"Bearer {api_key}"}, transport=transport)

    def send(self, message: EmailMessage) -> EmailResult:
        # Clé d'idempotence (Resend la conserve 24 h) : une relance ne crée pas de doublon.
        key = hashlib.sha256(message.idempotency_key.encode()).hexdigest()[:64]
        body = {
            "from": self.sender,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        for attempt in range(3):
            try:
                resp = self.client.post(RESEND_URL, json=body, headers={"Idempotency-Key": key})
            except httpx.HTTPError as exc:
                if attempt < 2:
                    self._sleep(2**attempt)
                    continue
                return EmailResult("failed", self.provider, error=f"Réseau : {exc.__class__.__name__}", retryable=True)
            if resp.status_code in (200, 201):
                return EmailResult("sent", self.provider, message_id=(resp.json() or {}).get("id"))
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < 2:
                    retry = resp.headers.get("retry-after", "")
                    self._sleep(min(float(retry) if retry.replace(".", "", 1).isdigit() else 2 ** (attempt + 1), 30))
                    continue
                return EmailResult("failed", self.provider, error=f"HTTP {resp.status_code}", retryable=True)
            try:
                detail = (resp.json() or {}).get("message", "")
            except ValueError:
                detail = ""
            return EmailResult(
                "failed", self.provider, error=f"HTTP {resp.status_code} {detail}"[:300], retryable=False
            )
        return EmailResult("failed", self.provider, error="Échec après plusieurs tentatives", retryable=True)


_client_override: EmailClient | None = None


def set_email_client(client: EmailClient | None) -> None:
    """Injection pour les tests."""
    global _client_override
    _client_override = client


def get_email_client() -> EmailClient:
    if _client_override is not None:
        return _client_override
    settings = get_settings()
    if settings.email_enabled:
        return ResendEmailClient(settings.resend_api_key or "", settings.email_from or "")
    return SimulationEmailClient()
