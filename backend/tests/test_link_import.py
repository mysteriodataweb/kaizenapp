"""Ajout d'offres par lien : lecture sûre (SSRF, robots.txt, CAPTCHA, connexion), extraction sans invention,
brouillon non enregistré, enregistrement dédoublonné, provenance, matching et suivi."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Application, Match, Opportunity, Source
from app.services import link_import as service
from app.workers.link_import import SafeFetcher
from tests.conftest import login, make_user

PUBLIC_IP = "93.184.216.34"
PRIVATE_HOSTS = {"intranet.example": "10.0.0.5", "localhost": "127.0.0.1"}

JOB_PAGE = """<html><head><title>Stage data | ACME</title>
<script type="application/ld+json">{json}</script></head>
<body><main><h1>Stage Data Analyst</h1><p>Rejoignez notre équipe data à Paris.</p></main></body></html>"""
POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Stage Data Analyst (6 mois)",
    "employmentType": "INTERN",
    "hiringOrganization": {"@type": "Organization", "name": "ACME Analytics"},
    "jobLocation": {"@type": "Place", "address": {"addressLocality": "Paris", "addressCountry": "FR"}},
    "validThrough": "2027-03-15T23:59:00+01:00",
    "description": "<p>Analyse de données &amp; tableaux de bord.</p>",
    "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR", "value": {"value": 1200, "unitText": "MONTH"}},
}
SCHOLARSHIP_PAGE = """<html><head><meta property="og:title" content="Bourse d'excellence pour un master 2027">
<meta property="og:site_name" content="Université Exemple"></head>
<body><nav>Menu</nav><main><p>Programme de bourses pour étudiants internationaux.</p>
<p>Date limite : 15 mars 2027 à minuit.</p></main><footer>Contact</footer></body></html>"""


@pytest.fixture
def web(monkeypatch) -> Callable[..., list[str]]:
    """Web simulé : routes {url: réponse}, résolution DNS contrôlée, journal des URL demandées."""
    requested: list[str] = []
    routes: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url in routes:
            return routes[url]
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        return httpx.Response(404, text="introuvable")

    def resolver(host: str, port: int) -> list[str]:
        return [PRIVATE_HOSTS.get(host, PUBLIC_IP)]

    monkeypatch.setattr(
        service, "make_fetcher", lambda: SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolver)
    )

    def setup(new_routes: dict[str, httpx.Response] | None = None) -> list[str]:
        routes.update(new_routes or {})
        return requested

    return setup


def html(body: str, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8", **headers})


def preview(client, headers, url: str):
    return client.post("/api/v1/opportunities/import/preview", headers=headers, json={"url": url})


def test_preview_extracts_job_posting_without_saving(client, db, auth, web):
    url = "https://careers.acme.example/jobs/42"
    web({url: html(JOB_PAGE.replace("{json}", json.dumps(POSTING)))})
    resp = preview(client, auth, url)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    draft = body["draft"]
    assert body["fetched"] is True and body["method"] == "json-ld"
    assert draft["type"] == "internship"
    assert draft["title"] == "Stage Data Analyst (6 mois)"
    assert draft["organization"] == "ACME Analytics"
    assert draft["location"] == "Paris" and draft["countries"] == ["FR"]
    assert draft["deadline_date"] == "2027-03-15"
    assert draft["stipend"] == "1200 EUR MONTH"
    assert "Analyse de données & tableaux de bord." in draft["description"]
    assert any("vérifiez" in n for n in body["notes"])
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_preview_generic_page_keeps_unknowns_empty(client, auth, web):
    url = "https://www.univ.example/bourses/excellence"
    web({url: html(SCHOLARSHIP_PAGE)})
    body = preview(client, auth, url).json()
    draft = body["draft"]
    assert body["method"] == "html"
    assert draft["type"] == "masters_scholarship"
    assert draft["title"] == "Bourse d'excellence pour un master 2027"
    assert draft["organization"] == "Université Exemple"
    assert draft["deadline_date"] == "2027-03-15"
    assert "Menu" not in draft["description"] and "Contact" not in draft["description"]
    # Rien d'inventé : pays, lieu et financement restent inconnus
    assert draft["countries"] == [] and draft["location"] is None and draft["stipend"] is None


def test_preview_flags_missing_fields(client, auth, web):
    url = "https://example.org/page"
    web({url: html("<html><body><main><p>Une page sans titre ni date.</p></main></body></html>")})
    body = preview(client, auth, url).json()
    assert body["draft"]["type"] is None and body["draft"]["organization"] is None
    assert any(n.startswith("À compléter") for n in body["notes"])
    assert any("Aucune date limite" in n for n in body["notes"])


def test_robots_txt_is_respected(client, auth, web):
    url = "https://jobs.example.com/offre/1"
    requested = web(
        {
            "https://jobs.example.com/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /offre/"),
            url: html("<html>ne doit pas être lu</html>"),
        }
    )
    body = preview(client, auth, url).json()
    assert body["fetched"] is False
    assert "robots.txt" in body["notes"][0]
    assert body["draft"]["official_url"] == url
    assert url not in requested


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (html("refusé", status=403), "refuse la lecture automatique"),
        (html("<html><head><title>Vérification</title></head><body>captcha</body></html>"), "CAPTCHA"),
        (html("<html><title>Just a moment...</title><body></body></html>"), "CAPTCHA"),
        (html("absent", status=404), "introuvable"),
        (httpx.Response(200, content=b"\x00", headers={"content-type": "application/zip"}), "non pris en charge"),
    ],
)
def test_blocked_or_unreadable_pages_fall_back_to_manual_form(client, auth, web, response, expected):
    url = "https://site.example/offre"
    web({url: response})
    body = preview(client, auth, url).json()
    assert body["fetched"] is False
    assert expected in body["notes"][0]


def test_login_wall_is_not_bypassed(client, auth, web):
    url = "https://social.example/jobs/view/1"
    web(
        {
            url: httpx.Response(302, headers={"location": "https://social.example/authwall?trk=x"}),
            "https://social.example/authwall?trk=x": html("<html><body><form>Connexion</form></body></html>"),
        }
    )
    body = preview(client, auth, url).json()
    assert body["fetched"] is False and "connexion" in body["notes"][0]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/secret",
        "http://intranet.example/rh",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "https://user:motdepasse@example.com/offre",
        "https://example.com:8443/offre",
    ],
)
def test_ssrf_targets_are_refused(client, auth, web, url):
    requested = web()
    resp = preview(client, auth, url)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_link"
    assert requested == []


def test_redirect_to_private_address_is_refused(client, auth, web):
    url = "https://short.example/r/1"
    requested = web({url: httpx.Response(301, headers={"location": "http://10.0.0.7/interne"})})
    resp = preview(client, auth, url)
    assert resp.status_code == 422
    assert not any("10.0.0.7" in r for r in requested)


def test_greenhouse_link_uses_public_api(client, auth, web):
    url = "https://boards.greenhouse.io/acme/jobs/123456"
    api = "https://boards-api.greenhouse.io/v1/boards/acme/jobs/123456"
    job = {
        "id": 123456,
        "title": "Software Engineering Intern",
        "company_name": "ACME",
        "absolute_url": url,
        "location": {"name": "Berlin, Germany"},
        "content": "&lt;p&gt;Build things.&lt;/p&gt;",
        "departments": [{"name": "Engineering"}],
    }
    requested = web({api: httpx.Response(200, json=job)})
    body = preview(client, auth, url).json()
    draft = body["draft"]
    assert body["method"] == "greenhouse-api"
    assert draft["title"] == "Software Engineering Intern" and draft["organization"] == "ACME"
    assert draft["type"] == "internship" and draft["countries"] == ["DE"]
    assert draft["description"] == "Build things." and draft["fields"] == ["Engineering"]
    assert requested == [api]


def test_lever_link_uses_public_api(client, auth, web):
    posting_id = "0b6a1f2e-1234-4abc-9def-0123456789ab"
    url = f"https://jobs.lever.co/acme/{posting_id}"
    api = f"https://api.lever.co/v0/postings/acme/{posting_id}"
    post = {
        "text": "Marketing Intern",
        "hostedUrl": url,
        "categories": {"location": "Paris", "commitment": "Internship", "team": "Marketing"},
        "descriptionPlain": "Campagnes et contenus.",
        "workplaceType": "onsite",
        "country": "FR",
    }
    web({api: httpx.Response(200, json=post)})
    body = preview(client, auth, url).json()
    draft = body["draft"]
    assert body["method"] == "lever-api"
    assert draft["title"] == "Marketing Intern" and draft["organization"] is None
    assert draft["countries"] == ["FR"] and draft["remote"] is False
    assert any("organisme" in n for n in body["notes"])


def _pdf(text: str) -> bytes:
    content = f"BT /F1 14 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_call_for_applications(client, auth, web):
    url = "https://fondation.example/appel-bourses-master.pdf"
    pdf = _pdf("Scholarship programme Master 2027 - deadline 1 March 2027")
    web({url: httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})})
    body = preview(client, auth, url).json()
    draft = body["draft"]
    assert body["method"] == "pdf"
    assert draft["type"] == "masters_scholarship"
    assert draft["deadline_date"] == "2027-03-01"


def test_preview_detects_existing_offer_without_fetching(client, db, auth, web):
    url = "https://careers.acme.example/jobs/42"
    web({url: html(JOB_PAGE.replace("{json}", json.dumps(POSTING)))})
    created = client.post("/api/v1/opportunities/import", headers=auth, json=_payload(url)).json()
    requested = web()
    requested.clear()
    body = preview(client, auth, url + "?utm_source=newsletter").json()
    assert body["existing_opportunity_id"] == created["opportunity_id"]
    assert body["notes"] == ["Cette offre est déjà enregistrée."]
    assert requested == []


def _payload(url: str, **extra):
    return {
        "official_url": url,
        "type": "internship",
        "title": "Stage Data Analyst (6 mois)",
        "organization": "ACME Analytics",
        "location": "Paris",
        "countries": ["FR"],
        "deadline_date": "2027-03-15",
        "description": "Analyse de données.",
        **extra,
    }


def test_import_creates_offer_with_provenance_match_and_follow(client, db, user, auth):
    client.put("/api/v1/profile", headers=auth, json={"full_name": "Moi", "languages": []})
    url = "https://careers.acme.example/jobs/42"
    resp = client.post("/api/v1/opportunities/import", headers=auth, json=_payload(url, follow=True))
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["created"] is True and out["application_id"]

    opp = db.get(Opportunity, out["opportunity_id"])
    assert opp.verification_status == "unverified"  # relu par l'utilisateur ≠ confirmé par la source
    assert opp.owner_user_id == user.id  # offre personnelle
    assert opp.deadline_status == "unverified"
    # Fin de journée dans le fuseau de l'utilisateur (Europe/Paris, UTC+1 en mars)
    assert opp.deadline_at == datetime(2027, 3, 15, 22, 59, 59, tzinfo=UTC)

    detail = client.get(f"/api/v1/opportunities/{opp.id}", headers=auth).json()
    assert detail["sources"][0]["source_key"] == "manual-links"
    assert detail["sources"][0]["source_url"] == url
    assert detail["match"] is not None
    application = db.get(Application, out["application_id"])
    assert application.status == "to_explore" and application.user_id == user.id


def test_import_confirmed_deadline(client, db, auth):
    url = "https://careers.acme.example/jobs/43"
    out = client.post("/api/v1/opportunities/import", headers=auth, json=_payload(url, deadline_confirmed=True)).json()
    assert db.get(Opportunity, out["opportunity_id"]).deadline_status == "confirmed"


def test_import_validates_input(client, auth):
    bad = client.post(
        "/api/v1/opportunities/import",
        headers=auth,
        json=_payload("javascript:alert(1)"),
    )
    assert bad.status_code == 422
    private = client.post("/api/v1/opportunities/import", headers=auth, json=_payload("http://192.168.1.10/offre"))
    assert private.status_code == 422
    no_type = _payload("https://example.com/offre")
    no_type.pop("type")
    assert client.post("/api/v1/opportunities/import", headers=auth, json=no_type).status_code == 422


def test_import_requires_authentication(client):
    assert preview(client, {}, "https://example.com/offre").status_code == 401
    resp = client.post("/api/v1/opportunities/import", json=_payload("https://example.com/offre"))
    assert resp.status_code == 401


def test_rate_limits(client, auth, web, monkeypatch):
    monkeypatch.setattr(service, "PREVIEWS_PER_HOUR", 2)
    monkeypatch.setattr(service, "IMPORTS_PER_DAY", 1)
    web()
    for _ in range(2):
        assert preview(client, auth, "https://example.com/a").status_code == 200
    assert preview(client, auth, "https://example.com/a").status_code == 429
    ok = client.post("/api/v1/opportunities/import", headers=auth, json=_payload("https://example.com/x"))
    assert ok.status_code == 200
    again = client.post("/api/v1/opportunities/import", headers=auth, json=_payload("https://example.com/y"))
    assert again.status_code == 429


# ------------------------------------------------------------------ LinkedIn, texte collé, IA
LINKEDIN = "https://fr.linkedin.com/jobs/view/stagiaire-data-analyst-at-soci%C3%A9t%C3%A9-g%C3%A9n%C3%A9rale-4012345678?refId=x&trackingId=y"
OFFER_TEXT = """Stagiaire Data Analyst (H/F)
Société Générale · Paris, Île-de-France, France · il y a 2 jours
Stage · Débutant
Missions : tableaux de bord, analyses SQL.
Profil : étudiant(e) en Master 1 ou 2 en statistiques.
Documents : CV et lettre de motivation.
Date limite de candidature : 15 mars 2027
Durée : 6 mois"""


class FakeProvider:
    name = "fake"

    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def generate(self, system, prompt):
        raise AssertionError("non utilisé")

    def generate_json(self, system, prompt, schema):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.payload


def _ai_payload(**extra):
    base = {
        "title": "Stagiaire Data Analyst (H/F)",
        "organization": "Société Générale",
        "location": "Paris, Île-de-France, France",
        "countries": ["FR"],
        "remote": "unknown",
        "type": "internship",
        "deadline": "2027-03-15",
        "deadline_quote": "Date limite de candidature : 15 mars 2027",
        "duration_months": 6,
        "stipend": "",
        "required_documents": ["CV", "lettre de motivation"],
        "eligibility_criteria": ["Profil : étudiant(e) en Master 1 ou 2 en statistiques."],
        "fields": [],
    }
    return {**base, **extra}


def test_linkedin_link_is_never_fetched(client, auth, web):
    requested = web()
    body = preview(client, auth, LINKEDIN).json()
    draft = body["draft"]
    assert requested == []  # aucune requête vers LinkedIn
    assert body["method"] == "linkedin-url" and body["fetched"] is False
    assert draft["official_url"] == "https://www.linkedin.com/jobs/view/4012345678"
    assert draft["title"] == "Stagiaire data analyst"
    assert draft["organization"] == "Société Générale"
    assert draft["type"] == "internship"
    assert any("LinkedIn" in n for n in body["notes"])
    assert any("collez le texte" in n for n in body["notes"])


def test_linkedin_variants_point_to_the_same_offer(client, auth, web):
    web()
    created = client.post(
        "/api/v1/opportunities/import",
        headers=auth,
        json=_payload("https://www.linkedin.com/jobs/view/4012345678/?trackingId=abc"),
    ).json()
    for variant in (
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678",
        "https://www.linkedin.com/comm/jobs/view/4012345678/?refId=1",
    ):
        body = preview(client, auth, variant).json()
        assert body["existing_opportunity_id"] == created["opportunity_id"]


def test_pasted_text_with_ai_keeps_only_values_found_in_text(client, auth, web, monkeypatch):
    web()
    fake = FakeProvider(
        _ai_payload(
            stipend="1 500 € par mois",  # absent du texte : écarté
            fields=["Data", "Finance de marché"],  # « Finance de marché » absent : écarté
        )
    )
    monkeypatch.setattr(service.ai, "get_provider", lambda: fake)
    resp = client.post("/api/v1/opportunities/import/preview", headers=auth, json={"url": LINKEDIN, "text": OFFER_TEXT})
    body = resp.json()
    draft = body["draft"]
    assert body["ai_used"] is True and body["method"] == "linkedin-url+texte"
    assert "<texte_offre>" in fake.calls[0] and "Société Générale" in fake.calls[0]
    assert draft["title"] == "Stagiaire Data Analyst (H/F)"
    assert draft["organization"] == "Société Générale"
    assert draft["location"] == "Paris, Île-de-France, France" and draft["countries"] == ["FR"]
    assert draft["deadline_date"] == "2027-03-15" and draft["duration_months"] == 6
    assert draft["required_documents"] == ["CV", "lettre de motivation"]
    assert "Master 1 ou 2" in draft["eligibility_criteria"]
    assert draft["stipend"] is None and draft["fields"] == ["Data"]
    assert draft["description"].startswith("Stagiaire Data Analyst")


def test_ai_values_absent_from_text_are_discarded(client, auth, web, monkeypatch):
    web()
    fake = FakeProvider(
        _ai_payload(
            organization="BNP Paribas",
            location="Lyon",
            deadline="2027-04-30",
            deadline_quote="Clôture le 30 avril 2027",
            duration_months=12,
        )
    )
    monkeypatch.setattr(service.ai, "get_provider", lambda: fake)
    draft = client.post(
        "/api/v1/opportunities/import/preview", headers=auth, json={"url": LINKEDIN, "text": OFFER_TEXT}
    ).json()["draft"]
    # L'entreprise vient alors de l'adresse du lien ; rien d'inventé n'est conservé
    assert draft["organization"] == "Société Générale"
    assert draft["location"] is None and draft["countries"] == []
    assert draft["deadline_date"] is None and draft["duration_months"] is None


def test_pasted_text_without_ai_uses_simple_rules(client, auth, web, monkeypatch):
    web()
    monkeypatch.setattr(service.ai, "get_provider", lambda: None)
    body = client.post(
        "/api/v1/opportunities/import/preview", headers=auth, json={"url": LINKEDIN, "text": OFFER_TEXT}
    ).json()
    assert body["ai_used"] is False
    assert body["draft"]["deadline_date"] == "2027-03-15"
    assert body["draft"]["description"].startswith("Stagiaire Data Analyst")
    assert any("assistant IA" in n for n in body["notes"])


def test_ai_failure_falls_back_to_rules(client, auth, web, monkeypatch):
    from app.core.errors import ServiceUnavailable

    web()
    fake = FakeProvider(error=ServiceUnavailable("Clé du fournisseur IA invalide.", code="ai_auth"))
    monkeypatch.setattr(service.ai, "get_provider", lambda: fake)
    body = client.post(
        "/api/v1/opportunities/import/preview", headers=auth, json={"url": LINKEDIN, "text": OFFER_TEXT}
    ).json()
    assert body["ai_used"] is False and body["draft"]["deadline_date"] == "2027-03-15"
    assert any("Analyse IA indisponible" in n for n in body["notes"])


# ------------------------------------------------------------------ offres privées
def test_personal_offers_are_invisible_to_other_users(client, db, auth):
    out = client.post(
        "/api/v1/opportunities/import",
        headers=auth,
        json=_payload("https://careers.acme.example/jobs/77", organization="Organisme Secret"),
    ).json()
    oid = out["opportunity_id"]
    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    client.put("/api/v1/profile", headers=other, json={"full_name": "Autre", "languages": []})

    assert client.get("/api/v1/opportunities", headers=other).json()["total"] == 0
    assert client.get(f"/api/v1/opportunities/{oid}", headers=other).status_code == 404
    assert client.post(f"/api/v1/opportunities/{oid}/favorite", headers=other).status_code == 404
    assert client.post("/api/v1/applications", headers=other, json={"opportunity_id": oid}).status_code == 404
    assert "Organisme Secret" not in client.get("/api/v1/opportunities/facets", headers=other).json()["organizations"]
    assert client.get("/api/v1/dashboard", headers=other).json()["opportunities_total"] == 0
    client.post("/api/v1/matches/recompute", headers=other)
    other_id = client.get("/api/v1/auth/me", headers=other).json()["id"]
    assert not db.scalar(select(func.count()).select_from(Match).where(Match.user_id == other_id))

    mine = client.get("/api/v1/opportunities", headers=auth).json()
    assert mine["total"] == 1 and mine["items"][0]["is_private"] is True

    # Le même lien enregistré par quelqu'un d'autre devient SA propre offre, sans toucher à la première
    second = client.post(
        "/api/v1/opportunities/import",
        headers=other,
        json=_payload("https://careers.acme.example/jobs/77", title="Autre intitulé"),
    ).json()
    assert second["created"] is True and second["opportunity_id"] != oid
    assert db.get(Opportunity, oid).title == "Stage Data Analyst (6 mois)"


def test_collection_never_touches_personal_offers(client, db, auth):
    from app.workers.connectors.base import NormalizedOpportunity
    from app.workers.connectors.registry import seed_sources
    from app.workers.ingestion import upsert_opportunity

    url = "https://boards.greenhouse.io/acme/jobs/1"
    mine = client.post("/api/v1/opportunities/import", headers=auth, json=_payload(url)).json()
    seed_sources(db)
    source = db.scalar(select(Source).where(Source.key == "greenhouse-internships"))
    item = NormalizedOpportunity(
        type="internship",
        title="Stage Data Analyst (6 mois)",
        organization="ACME Analytics",
        official_url=url,
        source_url=url,
        is_official=True,
    )
    result = upsert_opportunity(db, source, item)
    db.commit()
    assert result.action == "created" and str(result.opportunity_id) != mine["opportunity_id"]
    assert db.get(Opportunity, mine["opportunity_id"]).owner_user_id is not None


# ------------------------------------------------------------------ ajout rapide, modification, suppression
def test_quick_save_many_links(client, db, auth):
    urls = [
        "https://www.linkedin.com/jobs/view/stage-marketing-at-acme-4000000001",
        "https://www.linkedin.com/jobs/view/4000000002/?trackingId=1",
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4000000002",  # même offre
        "https://www.linkedin.com/feed/",
        "http://127.0.0.1/interne",
        "https://www.welcometothejungle.com/fr/companies/acme/jobs/stage-data",
    ]
    resp = client.post("/api/v1/opportunities/import/quick", headers=auth, json={"urls": urls})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert (out["created"], out["already_saved"], out["errors"]) == (3, 1, 2)
    titles = [i["title"] for i in out["items"] if i["created"]]
    assert titles == ["Stage marketing", "Offre LinkedIn n° 4000000002", "Offre à compléter — welcometothejungle.com"]
    first = db.get(Opportunity, out["items"][0]["opportunity_id"])
    assert first.organization == "Acme" and first.owner_user_id is not None
    apps = client.get("/api/v1/applications", headers=auth).json()
    assert len(apps) == 3 and {a["status"] for a in apps} == {"to_explore"}

    again = client.post("/api/v1/opportunities/import/quick", headers=auth, json={"urls": urls[:2]}).json()
    assert (again["created"], again["already_saved"]) == (0, 2)
    assert len(client.get("/api/v1/applications", headers=auth).json()) == 3


def test_quick_save_respects_daily_limit(client, auth, monkeypatch):
    monkeypatch.setattr(service, "IMPORTS_PER_DAY", 2)
    urls = [f"https://www.linkedin.com/jobs/view/40000000{i}" for i in range(10, 13)]
    assert client.post("/api/v1/opportunities/import/quick", headers=auth, json={"urls": urls}).status_code == 429


def test_owner_can_edit_and_delete_personal_offer(client, db, auth):
    out = client.post(
        "/api/v1/opportunities/import/quick",
        headers=auth,
        json={"urls": ["https://www.linkedin.com/jobs/view/4000000099"]},
    ).json()
    oid = out["items"][0]["opportunity_id"]
    edited = _payload(
        "https://www.linkedin.com/jobs/view/4000000099",
        title="Stage Data Analyst",
        organization="ACME",
        deadline_date="2027-05-01",
        deadline_confirmed=True,
    )
    resp = client.put(f"/api/v1/opportunities/{oid}", headers=auth, json=edited)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["title"] == "Stage Data Analyst" and detail["organization"] == "ACME"
    assert detail["deadline_status"] == "confirmed" and detail["is_private"] is True

    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    assert client.put(f"/api/v1/opportunities/{oid}", headers=other, json=edited).status_code == 404
    assert client.delete(f"/api/v1/opportunities/{oid}", headers=other).status_code == 404

    assert client.delete(f"/api/v1/opportunities/{oid}", headers=auth).status_code == 204
    assert db.get(Opportunity, oid) is None
    assert client.get("/api/v1/applications", headers=auth).json() == []


def test_edit_refuses_public_offers_and_duplicate_links(client, db, auth):
    from app.workers.connectors.base import NormalizedOpportunity
    from app.workers.connectors.registry import seed_sources
    from app.workers.ingestion import upsert_opportunity

    seed_sources(db)
    source = db.scalar(select(Source).where(Source.key == "greenhouse-internships"))
    public = upsert_opportunity(
        db,
        source,
        NormalizedOpportunity(
            type="internship",
            title="Stage public",
            organization="ACME",
            official_url="https://boards.greenhouse.io/acme/jobs/5",
            source_url="https://boards.greenhouse.io/acme/jobs/5",
        ),
    )
    db.commit()
    resp = client.put(
        f"/api/v1/opportunities/{public.opportunity_id}", headers=auth, json=_payload("https://x.example/a")
    )
    assert resp.status_code == 403
    assert client.delete(f"/api/v1/opportunities/{public.opportunity_id}", headers=auth).status_code == 403

    a = client.post("/api/v1/opportunities/import", headers=auth, json=_payload("https://x.example/a")).json()
    client.post("/api/v1/opportunities/import", headers=auth, json=_payload("https://x.example/b"))
    clash = client.put(
        f"/api/v1/opportunities/{a['opportunity_id']}", headers=auth, json=_payload("https://x.example/b")
    )
    assert clash.status_code == 409


def test_account_deletion_with_personal_offers(client, db):
    make_user(db, "admin@example.com", admin=True)
    make_user(db, "membre@example.com")
    member = login(client, "membre@example.com")
    client.post("/api/v1/opportunities/import", headers=member, json=_payload("https://x.example/perso"))
    resp = client.post("/api/v1/auth/delete-account", headers=member, json={"password": "Mot-de-passe-solide-2026"})
    assert resp.status_code == 200, resp.text
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 0
