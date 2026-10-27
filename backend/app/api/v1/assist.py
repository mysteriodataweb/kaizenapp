from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.misc import AssistOut, AssistRequest
from app.services import ai, opportunities
from app.services import profile as profile_service

router = APIRouter(prefix="/assist", tags=["assistant IA (facultatif)"])

WARNING = (
    "Brouillon généré à partir de votre profil et de l'annonce uniquement. Relisez, corrigez et validez-le : "
    "rien n'est envoyé automatiquement."
)


@router.get("/status")
def status() -> dict[str, object]:
    return {"enabled": ai.get_provider() is not None}


@router.post("/generate", response_model=AssistOut)
def generate(data: AssistRequest, user: CurrentUser, db: DbSession) -> AssistOut:
    opp = opportunities.get_opportunity(db, data.opportunity_id)
    profile = profile_service.get_or_create(db, user)
    db.commit()
    missing = ai.missing_information(data.kind, profile)
    provider = ai.get_provider()
    if provider is None:
        return AssistOut(
            enabled=False,
            kind=data.kind,
            draft=None,
            missing_information=missing,
            used_fields=[],
            warning="Assistant IA désactivé : configurez AI_PROVIDER et AI_API_KEY pour l'activer. "
            "Toutes les autres fonctionnalités restent disponibles.",
        )
    draft = provider.generate(
        ai.SYSTEM_PROMPT, ai.build_prompt(data.kind, profile, opp, data.instructions, data.questions)
    )
    used = sorted(k for k in ai._profile_facts(profile))
    return AssistOut(
        enabled=True, kind=data.kind, draft=draft, missing_information=missing, used_fields=used, warning=WARNING
    )
