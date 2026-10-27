from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.models import IngestionRun, Opportunity, OpportunitySource
from app.workers.connectors.base import extract_deadline, is_internship_title
from app.workers.connectors.geo import detect_countries
from app.workers.connectors.http import PoliteClient
from app.workers.ingestion import dry_run_source, run_source
from tests.factories import make_source

FIX = Path(__file__).parent / "fixtures"


def load(name: str):
    text = (FIX / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


def mock_http(routes: dict[str, object], robots: str | None = None) -> PoliteClient:
    """Client HTTP hors ligne : aucune dépendance à un site distant instable."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=robots) if robots is not None else httpx.Response(404)
        for prefix, payload in routes.items():
            if url.startswith(prefix):
                if isinstance(payload, httpx.Response):
                    return payload
                if isinstance(payload, (dict, list)):
                    return httpx.Response(200, json=payload)
                ctype = "application/rss+xml" if str(payload).lstrip().startswith("<?xml") else "text/html"
                return httpx.Response(200, text=str(payload), headers={"content-type": ctype})
        return httpx.Response(404)

    return PoliteClient(min_delay=0, transport=httpx.MockTransport(handler), sleep=lambda _: None)


GH = "https://boards-api.greenhouse.io/v1/boards/exemple/jobs"


def test_greenhouse_collect_filters_internships(db):
    src = make_source(db)
    run = run_source(db, src, http=mock_http({GH: load("greenhouse_jobs.json")}))
    assert run.status == "success", run.details
    opps = db.scalars(select(Opportunity).order_by(Opportunity.title)).all()
    assert [o.title for o in opps] == ["Data Science Internship", "Software Engineering Intern (6 months)"]
    intern = opps[1]
    assert intern.type == "internship"
    assert intern.organization == "Exemple SA"
    assert intern.countries == ["FR"]
    assert intern.verification_status == "verified"
    assert intern.deadline_status == "unknown" and intern.deadline_at is None
    assert "gh_src" not in intern.canonical_url  # paramètres de suivi retirés
    assert "Python" in intern.description and "<" not in intern.description
    assert db.scalar(select(func.count()).select_from(OpportunitySource)) == 2
    assert src.verification_status == "verified"


def test_rerun_is_idempotent(db):
    src = make_source(db)
    http = mock_http({GH: load("greenhouse_jobs.json")})
    run_source(db, src, http=http)
    second = run_source(db, src, http=http)
    assert second.items_created == 0 and second.items_updated == 0 and second.items_unchanged == 2
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 2
    assert db.scalar(select(func.count()).select_from(OpportunitySource)) == 2


def test_content_change_detected_as_significant(db):
    src = make_source(db)
    data = load("greenhouse_jobs.json")
    run_source(db, src, http=mock_http({GH: data}))
    changed = copy.deepcopy(data)
    changed["jobs"][0]["title"] = "Software Engineering Intern (4 months)"
    run = run_source(db, src, http=mock_http({GH: changed}))
    assert run.items_updated == 1
    opp = db.scalar(select(Opportunity).where(Opportunity.external_id == "exemple:1001"))
    assert opp.title.endswith("(4 months)")
    assert "title" in opp.significant_change_fields
    assert opp.significant_change_at is not None


def test_disappeared_postings_are_closed_not_deleted(db):
    src = make_source(db)
    data = load("greenhouse_jobs.json")
    run_source(db, src, http=mock_http({GH: data}))
    fewer = copy.deepcopy(data)
    fewer["jobs"] = [j for j in fewer["jobs"] if j["id"] != 1003]
    run = run_source(db, src, http=mock_http({GH: fewer}))
    assert run.details.get("closed") == 1
    closed = db.scalar(select(Opportunity).where(Opportunity.external_id == "exemple:1003"))
    assert closed.status == "closed"
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 2


def test_source_error_is_logged_and_counted(db):
    src = make_source(db)
    run = run_source(db, src, http=mock_http({GH: httpx.Response(500)}))
    assert run.status == "failed"
    assert run.errors_count >= 1
    assert src.consecutive_failures == 1
    assert "boards" in (run.details["fatal"] or "").lower() or "échoué" in run.details["fatal"]
    assert any("exemple" in e["item"] for e in run.details["errors"])


def test_unexpected_format_logged_without_crash(db):
    src = make_source(db)
    run = run_source(db, src, http=mock_http({GH: {"unexpected": True}}))
    assert run.status == "failed"
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_one_failing_source_does_not_stop_others(db):
    from app.jobs.collect_opportunities import collect

    ok = make_source(db, key="a-ok")
    bad = make_source(db, key="b-bad", connector="rss", config={"feeds": []})
    import app.workers.ingestion as ingestion

    original = ingestion.PoliteClient
    ingestion.PoliteClient = lambda **_: mock_http({GH: load("greenhouse_jobs.json")})  # type: ignore[assignment]
    try:
        result = collect(db)
    finally:
        ingestion.PoliteClient = original  # type: ignore[assignment]
    assert result["sources"][bad.key]["status"] == "failed"
    assert result["sources"][ok.key]["status"] == "success"
    assert db.scalar(select(func.count()).select_from(IngestionRun)) == 2


def test_cross_source_duplicate_is_linked_not_duplicated(db):
    first = make_source(db, key="officiel")
    run_source(db, first, http=mock_http({GH: load("greenhouse_jobs.json")}))
    # Une seconde source (agrégateur) publie la même annonce sous une autre URL.
    other = make_source(
        db,
        key="agregateur",
        connector="rss",
        config={"feeds": [{"url": "https://agg.example.com/feed", "type": "internship", "organization": "Exemple SA"}]},
    )
    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>Agg</title>
    <item><title>Data Science Internship</title><link>https://agg.example.com/jobs/77</link>
    <description>Machine learning internship</description></item></channel></rss>"""
    run = run_source(db, other, http=mock_http({"https://agg.example.com/feed": rss}))
    assert run.status == "success", run.details
    # Localisation différente (Berlin vs non précisée) : PAS de fusion automatique.
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 3


def test_same_title_org_deadline_location_from_other_source_is_merged(db):
    from tests.factories import make_opportunity

    a = make_source(db, key="src-a")
    b = make_source(db, key="src-b")
    first = make_opportunity(db, a, official_url="https://a.example.org/x", location="Lyon")
    second = make_opportunity(db, b, official_url="https://b.example.org/y", location="Lyon", is_official=False)
    assert first.id == second.id
    sources = db.scalars(select(OpportunitySource).where(OpportunitySource.opportunity_id == first.id)).all()
    assert {s.source_url for s in sources} == {"https://a.example.org/x", "https://b.example.org/y"}


def test_validation_errors_skip_item(db):
    src = make_source(db)
    data = load("greenhouse_jobs.json")
    data["jobs"][0]["absolute_url"] = "javascript:alert(1)"
    run = run_source(db, src, http=mock_http({GH: data}))
    assert run.items_skipped == 1
    assert run.status == "partial"
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 1


def test_lever_connector(db):
    src = make_source(
        db, key="lever", connector="lever", config={"sites": [{"site": "exemple", "organization": "Exemple"}]}
    )
    run = run_source(db, src, http=mock_http({"https://api.lever.co/v0/postings/exemple": load("lever_postings.json")}))
    assert run.status == "success", run.details
    opp = db.scalar(select(Opportunity))
    assert opp.title == "Marketing Intern"
    assert opp.countries == ["PT"]
    assert opp.funding_type == "full" and "1200" in opp.stipend


def test_arbeitnow_is_unverified_aggregator(db):
    src = make_source(db, key="arbeitnow", connector="arbeitnow", config={"max_pages": 1})
    run = run_source(db, src, http=mock_http({"https://www.arbeitnow.com/api/job-board-api": load("arbeitnow.json")}))
    assert run.status == "success", run.details
    opp = db.scalar(select(Opportunity))
    assert opp.title.startswith("Praktikum")
    assert opp.verification_status == "unverified"
    assert opp.countries == ["DE"]


def test_erasmus_mundus_parsing_and_robots(db):
    src = make_source(db, key="emjm", connector="erasmus_mundus", config={"max_pages": 1})
    url = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
    run = run_source(db, src, http=mock_http({url: load("erasmus_catalogue.html")}))
    assert run.status == "success", run.details
    titles = sorted(db.scalars(select(Opportunity.title)).all())
    assert len(titles) == 2 and all("Master" in t for t in titles)
    opp = db.scalar(select(Opportunity).where(Opportunity.title.like("%Data Science%")))
    assert opp.type == "masters_scholarship"
    assert opp.official_url.startswith("https://www.example-emjm-datascience.eu")
    assert opp.deadline_status == "unknown"


def test_robots_disallow_stops_collection(db):
    src = make_source(db, key="emjm", connector="erasmus_mundus", config={"max_pages": 1})
    url = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
    run = run_source(
        db, src, http=mock_http({url: load("erasmus_catalogue.html")}, robots="User-agent: *\nDisallow: /")
    )
    assert run.status == "failed"
    assert "robots.txt" in run.details["fatal"]


def test_changed_page_format_is_reported(db):
    src = make_source(db, key="emjm", connector="erasmus_mundus", config={"max_pages": 1})
    url = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
    run = run_source(db, src, http=mock_http({url: "<html><body><p>Nouveau design</p></body></html>"}))
    assert run.status == "failed"
    assert "non reconnu" in run.details["fatal"]


def test_rss_connector_extracts_unverified_deadline(db):
    src = make_source(
        db,
        key="rss",
        connector="rss",
        config={
            "feeds": [
                {
                    "url": "https://www.univ-exemple.fr/feed",
                    "type": "auto",
                    "organization": "Université Exemple",
                    "official": True,
                    "countries": ["FR"],
                }
            ]
        },
    )
    run = run_source(db, src, http=mock_http({"https://www.univ-exemple.fr/feed": load("feed.xml")}))
    assert run.status == "success", run.details
    opps = db.scalars(select(Opportunity)).all()
    assert len(opps) == 1  # la conférence est ignorée
    assert opps[0].deadline_status == "unverified"
    assert opps[0].deadline_at.date().isoformat() == "2027-01-15"


def test_captcha_is_never_bypassed(db):
    src = make_source(db, key="emjm", connector="erasmus_mundus", config={"max_pages": 1})
    url = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
    run = run_source(db, src, http=mock_http({url: "<html><div class='g-recaptcha'>captcha</div></html>"}))
    assert run.status == "failed"
    assert "CAPTCHA" in run.details["fatal"]


def test_dry_run_writes_nothing(db):
    src = make_source(db)
    result = dry_run_source(src, http=mock_http({GH: load("greenhouse_jobs.json")}))
    assert result["ok"] and result["items_found"] == 2
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 0


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineering Intern", True),
        ("Stage — Data analyst", True),
        ("Praktikum Marketing", True),
        ("International Sales Manager", False),
        ("Internal Auditor", False),
        ("Backstage technician", False),
    ],
)
def test_internship_detection(title, expected):
    assert is_internship_title(title) is expected


def test_geo_and_deadline_helpers():
    assert detect_countries("Paris, France") == ["FR"]
    assert detect_countries("Remote - CA") == []
    assert detect_countries("München") == ["DE"]
    assert extract_deadline("Application deadline: March 3, 2027").date().isoformat() == "2027-03-03"
    assert extract_deadline("Date limite : 01/02/2027").date().isoformat() == "2027-02-01"
    assert extract_deadline("Aucune date") is None
