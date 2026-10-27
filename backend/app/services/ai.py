"""Assistant de rédaction facultatif, derrière une interface de fournisseur.

* AI_PROVIDER vide ou AI_API_KEY absente : fonctionnalité désactivée, le reste de l'application
  fonctionne normalement (aucune dépendance au modèle de langage).
* AI_PROVIDER=anthropic : SDK officiel Anthropic.

Les brouillons n'utilisent QUE les informations du profil et de l'annonce ; les manques sont
listés au lieu d'être inventés. Tout brouillon reste modifiable et doit être validé par l'utilisateur.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.core.logging import log_event
from app.models import Opportunity, Profile

logger = logging.getLogger("app.ai")

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"

KIND_LABELS = {
    "cover_letter": "une lettre de motivation",
    "cv_tailoring": "des suggestions pour adapter le CV à l'annonce (réorganisation et mise en avant d'éléments EXISTANTS)",
    "application_answers": "des réponses aux questions de candidature",
    "email_draft": "un brouillon d'e-mail au contact de l'opportunité",
    "interview_prep": "une préparation d'entretien (questions probables et éléments de réponse tirés du profil)",
}

# Champs requis par type de brouillon : signalés comme manquants plutôt qu'inventés.
REQUIRED_FIELDS = {
    "cover_letter": ["full_name", "field_of_study", "study_level"],
    "cv_tailoring": ["skills"],
    "application_answers": ["full_name"],
    "email_draft": ["full_name"],
    "interview_prep": ["field_of_study"],
}
FIELD_LABELS = {
    "full_name": "nom complet",
    "field_of_study": "domaine d'études",
    "study_level": "niveau d'études",
    "skills": "compétences",
    "experiences": "expériences",
    "languages": "langues",
    "institution": "établissement",
}

SYSTEM_PROMPT = """Tu aides une personne à préparer des documents de candidature (stages, bourses de master).
Règles impératives :
- Utilise UNIQUEMENT les faits présents dans le PROFIL et l'ANNONCE fournis. N'invente jamais d'expérience,
  de compétence, de diplôme, de note, de date, de chiffre ni de nom.
- Si une information utile manque, écris un espace réservé explicite entre crochets, par exemple
  [À COMPLÉTER : projet pertinent], et ne la devine pas.
- Rédige en français, sauf si l'annonce est clairement en anglais : dans ce cas rédige en anglais.
- Le texte produit est un brouillon que la personne relira, modifiera et validera elle-même."""


class AIProvider(Protocol):
    name: str

    def generate(self, system: str, prompt: str) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.client = anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=2)

    def generate(self, system: str, prompt: str) -> str:
        a = self._anthropic
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "medium"},
                # Repli côté serveur si un classifieur de sécurité refuse la requête.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError as exc:
            raise ServiceUnavailable("Clé du fournisseur IA invalide.", code="ai_auth") from exc
        except a.RateLimitError as exc:
            raise ServiceUnavailable("Fournisseur IA saturé, réessayez plus tard.", code="ai_rate_limited") from exc
        except a.APIStatusError as exc:
            raise ServiceUnavailable(f"Erreur du fournisseur IA (HTTP {exc.status_code}).", code="ai_error") from exc
        except a.APIConnectionError as exc:
            raise ServiceUnavailable("Fournisseur IA injoignable.", code="ai_unreachable") from exc
        if response.stop_reason == "refusal":
            raise ServiceUnavailable("Le fournisseur IA a refusé cette demande.", code="ai_refusal")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if response.stop_reason == "max_tokens":
            text += "\n\n[Brouillon tronqué : relancez la génération ou raccourcissez la demande.]"
        return text


def get_provider() -> AIProvider | None:
    settings = get_settings()
    if not settings.ai_enabled:
        return None
    if (settings.ai_provider or "").lower() == "anthropic":
        return AnthropicProvider(settings.ai_api_key or "", settings.ai_model)
    log_event(logger, "unknown AI provider; feature disabled", logging.WARNING, provider=settings.ai_provider)
    return None


def _profile_facts(profile: Profile) -> dict[str, Any]:
    keys = [
        "full_name",
        "headline",
        "summary",
        "study_level",
        "current_degree",
        "institution",
        "field_of_study",
        "academic_year",
        "expected_graduation",
        "academic_results",
        "skills",
        "experiences",
        "projects",
        "leadership",
        "languages",
        "contact_email",
    ]
    facts = {k: getattr(profile, k) for k in keys}
    return {
        k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in facts.items() if v not in (None, "", [], {})
    }


def _opportunity_facts(opp: Opportunity) -> dict[str, Any]:
    return {
        "titre": opp.title,
        "organisme": opp.organization,
        "type": opp.type,
        "description": (opp.description or "")[:12000],
        "criteres": opp.eligibility_criteria,
        "documents_exiges": opp.required_documents,
        "langues": opp.required_languages,
        "lien_officiel": opp.official_url,
    }


def missing_information(kind: str, profile: Profile | None) -> list[str]:
    if profile is None:
        return ["profil non renseigné"]
    missing = [FIELD_LABELS.get(f, f) for f in REQUIRED_FIELDS.get(kind, []) if not getattr(profile, f)]
    if kind in ("cover_letter", "interview_prep", "cv_tailoring") and not (profile.experiences or profile.projects):
        missing.append("expériences ou projets")
    return missing


def build_prompt(kind: str, profile: Profile, opp: Opportunity, instructions: str | None, questions: list[str]) -> str:
    parts = [
        f"Prépare {KIND_LABELS[kind]}.",
        "PROFIL (seules informations autorisées sur la personne) :",
        json.dumps(_profile_facts(profile), ensure_ascii=False, indent=1),
        "ANNONCE :",
        json.dumps(_opportunity_facts(opp), ensure_ascii=False, indent=1),
    ]
    if questions:
        parts += ["QUESTIONS DE CANDIDATURE :", *[f"- {q}" for q in questions]]
    if instructions:
        parts += ["CONSIGNES DE LA PERSONNE (style, longueur) :", instructions]
    return "\n\n".join(parts)
