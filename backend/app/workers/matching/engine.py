"""Moteur de matching déterministe et explicable.

Trois notions strictement séparées :
  A. Éligibilité   : eligible / ineligible / unknown (critères obligatoires publiés).
  B. Compatibilité : score 0–100 pondéré, avec part d'information connue (confiance).
  C. Priorité      : calculée ailleurs (services/priority.py) à partir de A, B et des échéances.

Règles :
  * « ineligible » uniquement si un critère obligatoire publié est explicitement incompatible ;
  * information manquante => « unknown », jamais une supposition ;
  * critère sans objet => retiré du dénominateur (pondération adaptée) ;
  * le score n'est pas une probabilité d'acceptation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.core.text import contains_phrase, normalize_text
from app.workers.matching.vocabulary import LANGUAGE_NAMES_FR, RELATED, concept_terms, concepts_for

ENGINE_VERSION = "1.0.0"
CEFR_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6, "NATIVE": 7}
LEVEL_LABELS = {
    "secondary": "secondaire",
    "bachelor": "licence / bachelor",
    "master": "master",
    "doctorate": "doctorat",
    "other": "autre",
}
DISCLAIMER = (
    "Ce score mesure l'adéquation entre votre profil et l'annonce selon des critères explicites. "
    "Ce n'est pas une probabilité d'acceptation."
)

CriterionStatus = Literal["met", "partial", "unmet", "unknown", "not_applicable"]
CheckStatus = Literal["satisfied", "failed", "unknown"]


# --------------------------------------------------------------------------- données d'entrée
@dataclass
class ProfileData:
    nationalities: list[str] = field(default_factory=list)
    study_level: str | None = None
    field_of_study: str | None = None
    skills: list[str] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    languages: list[dict[str, Any]] = field(default_factory=list)
    target_countries: list[str] = field(default_factory=list)
    internship_fields: list[str] = field(default_factory=list)
    master_fields: list[str] = field(default_factory=list)
    funding_preference: str | None = None
    program_types: list[str] = field(default_factory=list)
    internship_duration_min_months: int | None = None
    internship_duration_max_months: int | None = None
    accepts_remote: bool | None = None
    version: int = 1

    @classmethod
    def from_model(cls, p: Any) -> ProfileData:
        return cls(**{k: getattr(p, k) for k in cls.__dataclass_fields__ if hasattr(p, k)})


@dataclass
class OpportunityData:
    type: str
    title: str
    organization: str = ""
    description: str | None = None
    countries: list[str] = field(default_factory=list)
    remote: bool | None = None
    fields: list[str] = field(default_factory=list)
    study_levels: list[str] = field(default_factory=list)
    eligibility_criteria: str | None = None
    eligible_nationalities: list[str] | None = None
    required_languages: list[dict[str, Any]] = field(default_factory=list)
    funding_type: str = "unknown"
    duration_months: int | None = None
    tags: list[str] = field(default_factory=list)
    deadline_at: datetime | None = None
    status: str = "open"
    content_hash: str = ""

    @classmethod
    def from_model(cls, o: Any) -> OpportunityData:
        return cls(**{k: getattr(o, k) for k in cls.__dataclass_fields__ if hasattr(o, k)})


# --------------------------------------------------------------------------- résultats
@dataclass
class Check:
    key: str
    label: str
    status: CheckStatus
    detail: str


@dataclass
class Criterion:
    key: str
    label: str
    weight: float
    status: CriterionStatus = "unknown"
    value: float = 0.0  # 0..1 sur la part connue
    known_fraction: float = 0.0  # 0..1
    details: list[str] = field(default_factory=list)
    to_complete: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return self.status != "not_applicable"

    @property
    def known_weight(self) -> float:
        return self.weight * self.known_fraction if self.applicable else 0.0

    @property
    def points(self) -> float:
        return self.known_weight * self.value


@dataclass
class MatchResult:
    eligibility: str
    score: float
    confidence: float
    explanation: dict[str, Any]
    missing_profile_fields: list[str]
    engine_version: str = ENGINE_VERSION


@dataclass
class _Part:
    weight: float
    value: float | None  # None = inconnu
    applicable: bool = True
    detail: str = ""


def _combine(criterion: Criterion, parts: Sequence[_Part]) -> Criterion:
    applicable = [p for p in parts if p.applicable]
    criterion.details.extend(p.detail for p in parts if p.detail)
    if not applicable:
        criterion.status = "not_applicable"
        return criterion
    total = sum(p.weight for p in applicable)
    known = [p for p in applicable if p.value is not None]
    known_w = sum(p.weight for p in known)
    criterion.known_fraction = known_w / total if total else 0.0
    if not known:
        criterion.status = "unknown"
        criterion.value = 0.0
        return criterion
    criterion.value = sum(p.weight * (p.value or 0.0) for p in known) / known_w
    criterion.status = "met" if criterion.value >= 0.75 else "partial" if criterion.value >= 0.35 else "unmet"
    return criterion


# --------------------------------------------------------------------------- utilitaires
def _opp_text(o: OpportunityData) -> tuple[str, str, str]:
    structured = normalize_text(" ".join([*o.fields, *o.tags]))
    title = normalize_text(o.title)
    desc = normalize_text(" ".join(filter(None, [o.description, o.eligibility_criteria])))
    return structured, title, desc


def _profile_skills(p: ProfileData) -> list[str]:
    skills: dict[str, str] = {}
    for s in [
        *p.skills,
        *[s for e in p.experiences for s in e.get("skills", []) or []],
        *[s for pr in p.projects for s in pr.get("skills", []) or []],
    ]:
        n = normalize_text(s)
        if n and n not in skills:
            skills[n] = s
    return list(skills.values())


def _lang_level(langs: Iterable[dict[str, Any]], code: str) -> int | None:
    for item in langs:
        if str(item.get("code", "")).lower() == code.lower():
            return CEFR_ORDER.get(str(item.get("level", "")).upper())
    return None


def _lang_name(code: str) -> str:
    return LANGUAGE_NAMES_FR.get(code.lower(), code)


# --------------------------------------------------------------------------- A. éligibilité
def evaluate_eligibility(p: ProfileData, o: OpportunityData) -> tuple[str, list[Check], list[str]]:
    checks: list[Check] = []
    notes: list[str] = []

    if o.eligible_nationalities:
        allowed = {c.upper() for c in o.eligible_nationalities}
        if not p.nationalities:
            checks.append(
                Check(
                    "nationality",
                    "Nationalité",
                    "unknown",
                    "L'annonce restreint les nationalités ; renseignez la vôtre dans le profil.",
                )
            )
        elif allowed & {c.upper() for c in p.nationalities}:
            checks.append(
                Check("nationality", "Nationalité", "satisfied", "Votre nationalité figure parmi celles admises.")
            )
        else:
            checks.append(
                Check(
                    "nationality",
                    "Nationalité",
                    "failed",
                    "Nationalités admises : " + ", ".join(sorted(allowed)) + " — la vôtre n'y figure pas.",
                )
            )

    if o.study_levels:
        labels = ", ".join(LEVEL_LABELS.get(s, s) for s in o.study_levels)
        if not p.study_level:
            checks.append(
                Check(
                    "study_level", "Niveau d'études", "unknown", f"Niveaux admis : {labels}. Renseignez votre niveau."
                )
            )
        elif p.study_level in o.study_levels:
            checks.append(Check("study_level", "Niveau d'études", "satisfied", f"Niveau admis ({labels})."))
        else:
            checks.append(
                Check(
                    "study_level",
                    "Niveau d'études",
                    "failed",
                    f"Niveaux admis : {labels} ; votre niveau : {LEVEL_LABELS.get(p.study_level, p.study_level)}.",
                )
            )

    for req in o.required_languages:
        code, level = str(req.get("code", "")), str(req.get("level", "") or "").upper()
        if not code:
            continue
        required = CEFR_ORDER.get(level)
        mine = _lang_level(p.languages, code)
        label = f"Langue : {_lang_name(code)}" + (f" ({level})" if level else "")
        if mine is None:
            checks.append(
                Check(
                    f"lang_{code}", label, "unknown", f"Niveau en {_lang_name(code)} non renseigné dans votre profil."
                )
            )
        elif required is None or mine >= required:
            checks.append(Check(f"lang_{code}", label, "satisfied", "Niveau suffisant."))
        else:
            checks.append(Check(f"lang_{code}", label, "failed", f"Niveau requis {level} supérieur au vôtre."))

    if o.eligibility_criteria:
        notes.append("Des critères rédigés en texte libre figurent dans l'annonce : vérifiez-les sur le site officiel.")

    if any(c.status == "failed" for c in checks):
        status = "ineligible"
    elif not checks:
        status = "unknown"
        notes.append("L'annonce ne publie pas de critères d'éligibilité structurés : éligibilité à confirmer.")
    elif any(c.status == "unknown" for c in checks):
        status = "unknown"
    else:
        status = "eligible"
    return status, checks, notes


# --------------------------------------------------------------------------- B. compatibilité
def _academic(p: ProfileData, o: OpportunityData, weight: float) -> Criterion:
    c = Criterion("academic", "Niveau et domaine académique", weight)
    parts: list[_Part] = []

    # Niveau : explicite si publié, sinon estimation déterministe selon le type d'opportunité.
    if not p.study_level:
        parts.append(_Part(0.4, None, detail="Niveau d'études non renseigné."))
        c.to_complete.append("study_level")
    elif o.study_levels:
        ok = p.study_level in o.study_levels
        parts.append(
            _Part(
                0.4,
                1.0 if ok else 0.0,
                detail="Niveau d'études conforme à l'annonce." if ok else "Niveau d'études différent de celui visé.",
            )
        )
    else:
        if o.type == "masters_scholarship":
            table = {"bachelor": 1.0, "master": 0.7, "doctorate": 0.4, "secondary": 0.1, "other": 0.5}
            hint = "Estimation : une bourse de master vise surtout les titulaires (ou finissants) d'une licence."
        else:
            table = {"bachelor": 1.0, "master": 1.0, "doctorate": 0.7, "secondary": 0.4, "other": 0.6}
            hint = "Estimation : niveau non précisé par l'annonce de stage."
        parts.append(_Part(0.4, table.get(p.study_level, 0.5), detail=hint))

    # Domaine : concepts bilingues issus du profil comparés aux champs, au titre puis à la description.
    terms = [
        t
        for t in [p.field_of_study, *(p.master_fields if o.type == "masters_scholarship" else p.internship_fields)]
        if t
    ]
    if not terms:
        parts.append(_Part(0.6, None, detail="Domaine d'études / domaines recherchés non renseignés."))
        c.to_complete.append("field_of_study")
    else:
        structured, title, desc = _opp_text(o)
        best, why = 0.0, ""
        for term in terms:
            concepts = concepts_for(term) or set()
            candidates = [normalize_text(term)] + [t for cc in concepts for t in concept_terms(cc)]
            strict = [normalize_text(term)] + [t for cc in concepts for t in concept_terms(cc, include_ambiguous=False)]
            if any(contains_phrase(structured, t) or contains_phrase(title, t) for t in candidates):
                best, why = 1.0, f"Domaine « {term} » correspondant au titre ou aux domaines de l'annonce."
                break
            if any(contains_phrase(desc, t) for t in strict) and best < 0.7:
                best, why = 0.7, f"Domaine « {term} » mentionné dans la description."
            related = {r for cc in concepts for r in RELATED.get(cc, set())} - concepts
            related_terms = [t for rc in related for t in concept_terms(rc, include_ambiguous=False)]
            if best < 0.6 and any(contains_phrase(structured, t) or contains_phrase(title, t) for t in related_terms):
                best, why = 0.6, f"Domaine de l'annonce voisin de « {term} »."
        if not (structured or title or desc):
            parts.append(_Part(0.6, None, detail="L'annonce ne précise pas de domaine."))
        else:
            parts.append(_Part(0.6, best, detail=why or "Aucun de vos domaines n'apparaît dans l'annonce."))
    return _combine(c, parts)


def _skills(p: ProfileData, o: OpportunityData, weight: float) -> Criterion:
    c = Criterion("skills", "Compétences et expériences", weight)
    skills = _profile_skills(p)
    if not skills:
        c.to_complete.append("skills")
        return _combine(c, [_Part(1, None, detail="Aucune compétence renseignée dans le profil.")])
    structured, title, desc = _opp_text(o)
    text = " ".join([structured, title, desc])
    matched = [s for s in skills if contains_phrase(text, s)]
    if matched:
        # Les annonces de master détaillent rarement les compétences : chaque correspondance pèse plus.
        value = min(1.0, len(matched) / 3) if o.type == "internship" else min(1.0, 0.5 + 0.25 * len(matched))
        detail = "Compétences retrouvées dans l'annonce : " + ", ".join(matched[:8])
        if p.experiences:
            detail += f" ({len(p.experiences)} expérience(s) déclarée(s))."
        return _combine(c, [_Part(1, value, detail=detail)])
    if o.type == "internship" and len(desc) >= 200:
        return _combine(c, [_Part(1, 0.0, detail="Aucune de vos compétences n'est mentionnée dans l'annonce.")])
    return _combine(c, [_Part(1, None, detail="L'annonce ne détaille pas suffisamment les compétences attendues.")])


_FUNDING_TABLE = {
    "masters_scholarship": {
        "full_only": {"full": 1.0, "partial": 0.4, "none": 0.0},
        "full_or_partial": {"full": 1.0, "partial": 0.8, "none": 0.0},
        "any": {"full": 1.0, "partial": 0.8, "none": 0.5},
    },
    "internship": {
        "full_only": {"full": 1.0, "partial": 0.8, "none": 0.0},
        "full_or_partial": {"full": 1.0, "partial": 0.9, "none": 0.2},
        "any": {"full": 1.0, "partial": 1.0, "none": 0.6},
    },
}
_FUNDING_LABEL = {"full": "financement complet", "partial": "financement partiel", "none": "non financé"}


def _funding(p: ProfileData, o: OpportunityData, weight: float) -> Criterion:
    c = Criterion("funding", "Objectifs de financement", weight)
    if not p.funding_preference:
        c.to_complete.append("funding_preference")
        return _combine(c, [_Part(1, None, detail="Préférence de financement non renseignée.")])
    if o.funding_type == "unknown":
        return _combine(c, [_Part(1, None, detail="L'annonce ne précise pas le financement.")])
    table = _FUNDING_TABLE.get(o.type, _FUNDING_TABLE["internship"])
    value = table.get(p.funding_preference, {}).get(o.funding_type, 0.5)
    label = _FUNDING_LABEL.get(o.funding_type, o.funding_type)
    if o.type == "internship":
        label = {
            "full": "stage rémunéré",
            "partial": "stage partiellement rémunéré/indemnisé",
            "none": "stage non rémunéré",
        }.get(o.funding_type, label)
    return _combine(c, [_Part(1, value, detail=f"Annonce : {label}.")])


def _preferences(p: ProfileData, o: OpportunityData, weight: float) -> Criterion:
    c = Criterion("preferences", "Pays et types de programmes préférés", weight)
    parts: list[_Part] = []
    if not p.target_countries:
        parts.append(_Part(0.6, None, applicable=False, detail="Aucun pays cible : tous les pays conviennent."))
    elif not o.countries and o.remote is None:
        parts.append(_Part(0.6, None, detail="Pays de l'opportunité non précisé."))
    elif set(o.countries) & set(p.target_countries):
        common = sorted(set(o.countries) & set(p.target_countries))
        parts.append(_Part(0.6, 1.0, detail="Pays souhaité : " + ", ".join(common) + "."))
    elif o.remote and p.accepts_remote:
        parts.append(_Part(0.6, 0.8, detail="Télétravail possible et accepté."))
    else:
        parts.append(_Part(0.6, 0.0, detail="Pays hors de vos préférences."))

    if not p.program_types:
        parts.append(_Part(0.25, None, applicable=False))
    else:
        ok = o.type in p.program_types
        parts.append(
            _Part(
                0.25,
                1.0 if ok else 0.0,
                detail="Type d'opportunité recherché." if ok else "Type d'opportunité non recherché.",
            )
        )

    if o.type == "internship":
        lo, hi = p.internship_duration_min_months, p.internship_duration_max_months
        if lo is None and hi is None:
            parts.append(_Part(0.15, None, applicable=False))
        elif o.duration_months is None:
            parts.append(_Part(0.15, None, detail="Durée du stage non précisée."))
        else:
            ok = (lo is None or o.duration_months >= lo) and (hi is None or o.duration_months <= hi)
            parts.append(
                _Part(
                    0.15,
                    1.0 if ok else 0.3,
                    detail=f"Durée {o.duration_months} mois " + ("conforme." if ok else "hors de votre fourchette."),
                )
            )
    return _combine(c, parts)


def _languages(p: ProfileData, o: OpportunityData, weight: float) -> Criterion:
    c = Criterion("languages", "Langues", weight)
    if not o.required_languages:
        return _combine(c, [_Part(1, None, applicable=False, detail="Aucune exigence linguistique publiée.")])
    parts = []
    for req in o.required_languages:
        code, level = str(req.get("code", "")), str(req.get("level", "") or "").upper()
        mine = _lang_level(p.languages, code)
        required = CEFR_ORDER.get(level, 1)
        if mine is None:
            parts.append(_Part(1, None, detail=f"{_lang_name(code).capitalize()} : niveau non renseigné."))
            if "languages" not in c.to_complete:
                c.to_complete.append("languages")
        else:
            value = 1.0 if mine >= required else max(0.0, 1 - (required - mine) * 0.4)
            parts.append(
                _Part(
                    1,
                    value,
                    detail=f"{_lang_name(code).capitalize()} : "
                    + ("niveau suffisant." if value == 1 else f"niveau inférieur à {level}."),
                )
            )
    return _combine(c, parts)


# --------------------------------------------------------------------------- calcul complet
def compute_match(p: ProfileData, o: OpportunityData, weights: dict[str, float]) -> MatchResult:
    eligibility, checks, notes = evaluate_eligibility(p, o)
    criteria = [
        _academic(p, o, weights.get("academic", 30)),
        _skills(p, o, weights.get("skills", 25)),
        _funding(p, o, weights.get("funding", 20)),
        _preferences(p, o, weights.get("preferences", 15)),
        _languages(p, o, weights.get("languages", 10)),
    ]
    applicable = [c for c in criteria if c.applicable]
    applicable_weight = sum(c.weight for c in applicable)
    known_weight = sum(c.known_weight for c in applicable)
    score = round(100 * sum(c.points for c in applicable) / known_weight, 1) if known_weight else 0.0
    score = max(0.0, min(100.0, score))
    confidence = round(known_weight / applicable_weight, 3) if applicable_weight else 0.0

    missing = sorted({f for c in criteria for f in c.to_complete})
    if eligibility != "ineligible":
        for chk in checks:
            if chk.status == "unknown" and chk.key == "nationality":
                missing.append("nationalities")
    missing = sorted(set(missing))

    label = "élevée" if confidence >= 0.8 else "moyenne" if confidence >= 0.5 else "faible"
    explanation = {
        "engine_version": ENGINE_VERSION,
        "eligibility": {
            "status": eligibility,
            "checks": [chk.__dict__ for chk in checks],
            "notes": notes,
        },
        "criteria": [
            {
                "key": c.key,
                "label": c.label,
                "weight": c.weight,
                "effective_weight": round(100 * c.weight / applicable_weight, 1)
                if c.applicable and applicable_weight
                else 0,
                "status": c.status,
                "value": round(c.value, 3),
                "known_fraction": round(c.known_fraction, 3),
                "points": round(c.points, 2),
                "details": c.details,
            }
            for c in criteria
        ],
        "satisfied": [f"{c.label} : {d}" for c in criteria if c.status == "met" for d in c.details[:1]]
        + [f"{chk.label} : {chk.detail}" for chk in checks if chk.status == "satisfied"],
        "unsatisfied": [f"{c.label} : {d}" for c in criteria if c.status == "unmet" for d in c.details[:1]]
        + [f"{chk.label} : {chk.detail}" for chk in checks if chk.status == "failed"],
        "unknown": [f"{c.label} : {d}" for c in criteria if c.status == "unknown" for d in c.details[:1]]
        + [f"{chk.label} : {chk.detail}" for chk in checks if chk.status == "unknown"],
        "partial": [f"{c.label} : {'; '.join(c.details)}" for c in criteria if c.status == "partial"],
        "to_complete": missing,
        "score": score,
        "confidence": confidence,
        "confidence_label": label,
        "reliable": confidence >= 0.6,
        "disclaimer": DISCLAIMER,
    }
    return MatchResult(
        eligibility=eligibility,
        score=score,
        confidence=confidence,
        explanation=explanation,
        missing_profile_fields=missing,
    )
