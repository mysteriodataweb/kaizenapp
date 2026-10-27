"""Extraction prudente d'informations depuis un CV PDF.

Seules des informations *littéralement présentes* dans le texte sont proposées, chacune
avec l'extrait qui la justifie. Rien n'est enregistré sans confirmation de l'utilisateur.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import AppError
from app.core.text import contains_phrase, normalize_text

SKILL_VOCABULARY = [
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "C",
    "C++",
    "C#",
    "Go",
    "Rust",
    "PHP",
    "Ruby",
    "Kotlin",
    "Swift",
    "R",
    "MATLAB",
    "Scala",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "SQLite",
    "Oracle",
    "HTML",
    "CSS",
    "React",
    "Next.js",
    "Vue.js",
    "Angular",
    "Node.js",
    "Express",
    "Django",
    "Flask",
    "FastAPI",
    "Spring",
    "Laravel",
    ".NET",
    "Tailwind",
    "Bootstrap",
    "GraphQL",
    "REST",
    "Git",
    "GitHub",
    "GitLab",
    "Docker",
    "Kubernetes",
    "Linux",
    "Bash",
    "AWS",
    "Azure",
    "GCP",
    "Terraform",
    "CI/CD",
    "Pandas",
    "NumPy",
    "Scikit-learn",
    "TensorFlow",
    "PyTorch",
    "Keras",
    "Spark",
    "Hadoop",
    "Airflow",
    "dbt",
    "Power BI",
    "Tableau",
    "Excel",
    "Looker",
    "Machine Learning",
    "Deep Learning",
    "NLP",
    "Computer Vision",
    "Data Analysis",
    "Data Visualization",
    "Statistics",
    "Statistiques",
    "Econometrics",
    "Économétrie",
    "Figma",
    "UX",
    "UI",
    "Photoshop",
    "Illustrator",
    "AutoCAD",
    "SolidWorks",
    "ArcGIS",
    "QGIS",
    "SPSS",
    "Stata",
    "SAP",
    "Salesforce",
    "Jira",
    "Agile",
    "Scrum",
    "Gestion de projet",
    "Project Management",
    "Comptabilité",
    "Accounting",
    "Finance",
    "Marketing digital",
    "SEO",
    "Communication",
    "Leadership",
    "Arduino",
    "Raspberry Pi",
    "IoT",
    "VHDL",
    "Simulink",
    "LaTeX",
    "Cybersécurité",
    "Cybersecurity",
]

LANGUAGE_PATTERNS = {
    "fr": ["français", "francais", "french", "französisch"],
    "en": ["anglais", "english", "englisch"],
    "de": ["allemand", "german", "deutsch"],
    "es": ["espagnol", "spanish", "español", "espanol"],
    "it": ["italien", "italian", "italiano"],
    "pt": ["portugais", "portuguese", "português"],
    "ar": ["arabe", "arabic"],
    "zh": ["chinois", "chinese", "mandarin"],
    "wo": ["wolof"],
    "nl": ["néerlandais", "dutch"],
    "ru": ["russe", "russian"],
    "ja": ["japonais", "japanese"],
}

_LEVEL_WORDS = {
    "native": ["natif", "native", "maternelle", "mother tongue", "langue maternelle", "bilingue", "bilingual"],
    "C1": ["courant", "fluent", "avancé", "advanced"],
    "B1": ["intermédiaire", "intermediate"],
    "A2": ["notions", "basic", "débutant", "beginner", "elementary"],
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+|00)\d[\d .\-()]{7,18}\d|\b0\d(?:[ .-]?\d{2}){4}\b")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/|github\.com/)[A-Za-z0-9_\-/]+", re.I)
CEFR_RE = re.compile(r"\b(A1|A2|B1|B2|C1|C2)\b")


def _snippet(text: str, start: int, end: int, pad: int = 40) -> str:
    return " ".join(text[max(0, start - pad) : end + pad].split())


def extract_text(data: bytes, max_pages: int = 10) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AppError(
                "PDF protégé par mot de passe : extraction impossible.", code="pdf_encrypted", status_code=422
            )
        pages = reader.pages[:max_pages]
        return "\n".join((p.extract_text() or "") for p in pages), len(reader.pages)
    except PdfReadError as exc:
        raise AppError("PDF illisible.", code="pdf_unreadable", status_code=422) from exc


def extract_suggestions(text: str) -> tuple[dict[str, object], dict[str, str], list[str]]:
    suggestions: dict[str, object] = {}
    evidence: dict[str, str] = {}
    warnings: list[str] = []
    if len(text.strip()) < 50:
        warnings.append("Très peu de texte extrait : le PDF est peut-être une image scannée (pas d'OCR).")
        return suggestions, evidence, warnings

    if m := EMAIL_RE.search(text):
        suggestions["contact_email"] = m.group(0)
        evidence["contact_email"] = _snippet(text, m.start(), m.end())
    if m := PHONE_RE.search(text):
        suggestions["phone"] = " ".join(m.group(0).split())
        evidence["phone"] = _snippet(text, m.start(), m.end())
    links = sorted({u.rstrip("/") for u in URL_RE.findall(text)})
    if links:
        suggestions["links"] = links

    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:3]
    for line in first_lines:
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'\-]+", w) for w in words):
            suggestions["full_name"] = " ".join(w.capitalize() if w.isupper() else w for w in words)
            evidence["full_name"] = line
            warnings.append("Nom déduit de la première ligne du CV : vérifiez-le.")
            break

    norm = normalize_text(text)
    skills = [s for s in SKILL_VOCABULARY if len(s) > 1 and contains_phrase(norm, s)]
    if skills:
        suggestions["skills"] = skills
        evidence["skills"] = "Termes trouvés tels quels dans le CV."

    languages = []
    lower = text.lower()
    for code, names in LANGUAGE_PATTERNS.items():
        for name in names:
            idx = lower.find(name)
            if idx == -1:
                continue
            window = text[idx : idx + 60]
            level = None
            if m := CEFR_RE.search(window):
                level = m.group(1)
            else:
                wl = window.lower()
                for lvl, words in _LEVEL_WORDS.items():
                    if any(w in wl for w in words):
                        level = lvl
                        break
            languages.append({"code": code, "level": level})
            evidence[f"language_{code}"] = _snippet(text, idx, idx + len(name))
            break
    if languages:
        suggestions["languages"] = languages
        if any(lang["level"] is None for lang in languages):
            warnings.append("Certains niveaux de langue ne figurent pas dans le CV : complétez-les vous-même.")

    level_patterns = [
        ("doctorate", r"\b(doctorat|ph\.?\s?d|doctorate)\b"),
        ("master", r"\b(master|msc|m\.sc|mba|ingénieur|engineering degree)\b"),
        ("bachelor", r"\b(licence|bachelor|bsc|b\.sc|undergraduate)\b"),
    ]
    for level, pattern in level_patterns:
        if m := re.search(pattern, text, re.I):
            suggestions["study_level_mentioned"] = level
            evidence["study_level_mentioned"] = _snippet(text, m.start(), m.end())
            warnings.append(
                "Un diplôme est mentionné ; le CV ne dit pas toujours s'il est obtenu ou en cours : confirmez votre niveau."
            )
            break
    return suggestions, evidence, warnings
