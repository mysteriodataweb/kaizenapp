from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, User
from app.schemas.profile import ProfileIn, ProfileOut

# Champs utiles au matching et à l'éligibilité, avec libellé français.
COMPLETENESS_FIELDS: dict[str, str] = {
    "full_name": "Nom complet",
    "nationalities": "Nationalité(s)",
    "country_of_residence": "Pays de résidence",
    "study_level": "Niveau d'études",
    "field_of_study": "Domaine d'études",
    "institution": "Établissement",
    "expected_graduation": "Date de diplôme prévue",
    "skills": "Compétences",
    "languages": "Langues",
    "experiences": "Expériences",
    "target_countries": "Pays souhaités",
    "funding_preference": "Préférence de financement",
    "program_types": "Types de programmes",
}


def get_or_create(db: Session, user: User) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = Profile(user_id=user.id, contact_email=user.email)
        db.add(profile)
        db.flush()
    return profile


def to_out(profile: Profile) -> ProfileOut:
    out = ProfileOut.model_validate(profile)
    missing = [label for key, label in COMPLETENESS_FIELDS.items() if not getattr(profile, key)]
    out.missing_fields = missing
    out.completeness = round(100 * (len(COMPLETENESS_FIELDS) - len(missing)) / len(COMPLETENESS_FIELDS))
    return out


def update(db: Session, user: User, data: ProfileIn) -> Profile:
    profile = get_or_create(db, user)
    payload = data.model_dump(mode="json")
    payload["expected_graduation"] = data.expected_graduation
    changed = False
    for key, value in payload.items():
        if getattr(profile, key) != value:
            setattr(profile, key, value)
            changed = True
    if changed:
        profile.version = (profile.version or 1) + 1
    db.flush()
    return profile
