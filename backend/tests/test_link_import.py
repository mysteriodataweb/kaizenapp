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


def test_import_never_overwrites_existing_offer(client, db, auth):
    url = "https://careers.acme.example/jobs/42"
    first = client.post("/api/v1/opportunities/import", headers=auth, json=_payload(url)).json()
    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    second = client.post(
        "/api/v1/opportunities/import",
        headers=other,
        json=_payload(url + "/", title="Titre modifié par quelqu'un d'autre", follow=True),
    ).json()
    assert second["created"] is False and second["opportunity_id"] == first["opportunity_id"]
    assert second["application_id"]
    assert db.get(Opportunity, first["opportunity_id"]).title == "Stage Data Analyst (6 mois)"
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 1


def test_imported_offer_is_shared_and_scored_for_other_members(client, db, auth):
    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    client.put("/api/v1/profile", headers=other, json={"full_name": "Autre", "languages": []})
    out = client.post(
        "/api/v1/opportunities/import", headers=auth, json=_payload("https://careers.acme.example/jobs/44")
    ).json()
    listing = client.get("/api/v1/opportunities", headers=other).json()
    assert [o["id"] for o in listing["items"]] == [out["opportunity_id"]]
    other_id = client.get("/api/v1/auth/me", headers=other).json()["id"]
    assert db.scalar(
        select(func.count())
        .select_from(Match)
        .where(Match.user_id == other_id, Match.opportunity_id == out["opportunity_id"])
    )


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


def test_manual_source_is_not_a_collection_source(client, db, auth):
    make_user(db, "admin@example.com", admin=True)
    admin = login(client, "admin@example.com")
    client.post("/api/v1/opportunities/import", headers=auth, json=_payload("https://example.com/offre"))
    manual = db.scalar(select(Source).where(Source.key == "manual-links"))
    assert manual is not None and manual.enabled is False
    keys = [s["key"] for s in client.get("/api/v1/admin/sources", headers=admin).json()]
    assert "manual-links" not in keys
    assert client.post(f"/api/v1/admin/sources/{manual.id}/test", headers=admin).status_code == 404
    dashboard = client.get("/api/v1/dashboard", headers=auth).json()
    assert all(s["key"] != "manual-links" for s in dashboard["sources"])
