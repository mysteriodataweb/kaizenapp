"""Vocabulaire bilingue (FR/EN) des domaines : relie les formulations d'un profil
francophone aux annonces souvent rédigées en anglais ou en allemand."""

from __future__ import annotations

from app.core.text import normalize_text

# concept -> expressions (normalisées à l'import)
FIELD_CONCEPTS: dict[str, list[str]] = {
    "computer_science": [
        "informatique",
        "computer science",
        "computing",
        "software engineering",
        "genie logiciel",
        "software development",
        "developpement logiciel",
        "informatik",
        "it",
        "information technology",
        "computer engineering",
    ],
    "data_science": [
        "data science",
        "science des donnees",
        "data scientist",
        "data analysis",
        "analyse de donnees",
        "data analytics",
        "big data",
        "data engineering",
        "machine learning",
        "apprentissage automatique",
        "statistics",
        "statistique",
        "statistiques",
    ],
    "artificial_intelligence": [
        "intelligence artificielle",
        "artificial intelligence",
        "ai",
        "ia",
        "deep learning",
        "nlp",
        "computer vision",
        "vision par ordinateur",
        "machine learning",
    ],
    "cybersecurity": ["cybersecurite", "cybersecurity", "securite informatique", "information security", "security"],
    "electrical_engineering": [
        "genie electrique",
        "electrical engineering",
        "electronique",
        "electronics",
        "electrical",
        "telecommunications",
        "telecom",
        "embedded systems",
        "systemes embarques",
    ],
    "mechanical_engineering": ["genie mecanique", "mechanical engineering", "mecanique", "mechanical", "mechatronics"],
    "civil_engineering": ["genie civil", "civil engineering", "construction", "btp", "structural engineering"],
    "energy": [
        "energie",
        "energy",
        "renewable energy",
        "energies renouvelables",
        "energy engineering",
        "solar",
        "photovoltaique",
        "photovoltaic",
    ],
    "environment": [
        "environnement",
        "environment",
        "environmental science",
        "sciences de l environnement",
        "climate",
        "climat",
        "sustainability",
        "developpement durable",
        "ecology",
        "ecologie",
    ],
    "agriculture": ["agriculture", "agronomie", "agronomy", "agri food", "agroalimentaire", "food science"],
    "economics": ["economie", "economics", "econometrie", "econometrics", "development economics"],
    "finance": ["finance", "banque", "banking", "comptabilite", "accounting", "audit", "fintech"],
    "management": [
        "management",
        "gestion",
        "business",
        "business administration",
        "administration des affaires",
        "commerce",
        "entrepreneuriat",
        "entrepreneurship",
        "strategy",
        "strategie",
        "operations",
    ],
    "marketing": ["marketing", "communication", "digital marketing", "marketing digital", "brand", "growth"],
    "law": ["droit", "law", "legal", "juridique", "jurist", "juriste"],
    "international_relations": [
        "relations internationales",
        "international relations",
        "political science",
        "sciences politiques",
        "public policy",
        "politiques publiques",
        "international development",
        "developpement international",
        "humanitarian",
        "humanitaire",
    ],
    "public_health": ["sante publique", "public health", "epidemiology", "epidemiologie", "global health"],
    "medicine": ["medecine", "medicine", "medical", "pharmacie", "pharmacy", "nursing", "biomedical"],
    "biology": ["biologie", "biology", "biotechnology", "biotechnologie", "life sciences", "sciences de la vie"],
    "chemistry": ["chimie", "chemistry", "chemical engineering", "genie chimique"],
    "physics": ["physique", "physics", "astrophysics", "optics", "photonics", "photonique"],
    "mathematics": ["mathematiques", "mathematics", "maths", "math", "applied mathematics", "mathematiques appliquees"],
    "education": ["education", "enseignement", "teaching", "pedagogie", "pedagogy"],
    "social_sciences": ["sociologie", "sociology", "psychologie", "psychology", "anthropology", "anthropologie"],
    "humanities": [
        "lettres",
        "humanities",
        "histoire",
        "history",
        "philosophie",
        "philosophy",
        "linguistics",
        "linguistique",
    ],
    "design": ["design", "ux", "ui", "user experience", "graphic design", "design graphique", "architecture"],
    "logistics": ["logistique", "logistics", "supply chain", "chaine d approvisionnement", "transport"],
    "urban_planning": [
        "urbanisme",
        "urban planning",
        "amenagement du territoire",
        "geography",
        "geographie",
        "gis",
        "sig",
    ],
    "water": ["eau", "water", "hydrology", "hydrologie", "water resources", "assainissement", "sanitation"],
}

_NORMALIZED = {concept: sorted({normalize_text(t) for t in terms}) for concept, terms in FIELD_CONCEPTS.items()}

# Expressions trop courtes/ambiguës : uniquement comparées sur les champs structurés et le titre.
AMBIGUOUS = {"ai", "ia", "it", "ux", "ui", "gis", "sig", "math", "eau", "security", "operations", "transport"}


# Domaines voisins : correspondance partielle (0.6) plutôt que nulle.
RELATED: dict[str, set[str]] = {
    "computer_science": {"data_science", "artificial_intelligence", "cybersecurity", "electrical_engineering"},
    "data_science": {"computer_science", "artificial_intelligence", "mathematics", "economics"},
    "artificial_intelligence": {"computer_science", "data_science", "mathematics"},
    "cybersecurity": {"computer_science"},
    "electrical_engineering": {"computer_science", "energy", "physics"},
    "mechanical_engineering": {"energy", "civil_engineering", "physics"},
    "civil_engineering": {"urban_planning", "water", "mechanical_engineering"},
    "energy": {"environment", "electrical_engineering", "mechanical_engineering"},
    "environment": {"energy", "agriculture", "water", "public_health", "urban_planning"},
    "agriculture": {"environment", "biology", "water"},
    "economics": {"finance", "management", "international_relations", "data_science"},
    "finance": {"economics", "management"},
    "management": {"economics", "finance", "marketing", "logistics"},
    "marketing": {"management", "design"},
    "law": {"international_relations"},
    "international_relations": {"law", "economics", "social_sciences"},
    "public_health": {"medicine", "biology", "environment"},
    "medicine": {"public_health", "biology"},
    "biology": {"medicine", "chemistry", "agriculture", "public_health"},
    "chemistry": {"biology", "physics"},
    "physics": {"mathematics", "chemistry", "electrical_engineering"},
    "mathematics": {"data_science", "physics", "artificial_intelligence"},
    "urban_planning": {"civil_engineering", "environment"},
    "water": {"environment", "civil_engineering"},
    "logistics": {"management"},
}


def concepts_for(term: str) -> set[str]:
    """Concepts associés à une expression libre du profil (ex. « Informatique » -> computer_science)."""
    norm = normalize_text(term)
    found = {c for c, terms in _NORMALIZED.items() if norm in terms}
    if not found:
        for concept, terms in _NORMALIZED.items():
            if any(len(t) > 3 and (t in norm or norm in t) for t in terms):
                found.add(concept)
    return found


def concept_terms(concept: str, include_ambiguous: bool = True) -> list[str]:
    terms = _NORMALIZED.get(concept, [])
    return terms if include_ambiguous else [t for t in terms if t not in AMBIGUOUS]


LANGUAGE_NAMES_FR: dict[str, str] = {
    "fr": "français",
    "en": "anglais",
    "de": "allemand",
    "es": "espagnol",
    "it": "italien",
    "pt": "portugais",
    "nl": "néerlandais",
    "ar": "arabe",
    "zh": "chinois",
    "ja": "japonais",
    "ru": "russe",
    "wo": "wolof",
    "sw": "swahili",
    "ko": "coréen",
    "tr": "turc",
    "pl": "polonais",
    "sv": "suédois",
    "hi": "hindi",
}
