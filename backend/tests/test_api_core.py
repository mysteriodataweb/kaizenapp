from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Match
from app.services import matching
from tests.conftest import login, make_user
from tests.factories import in_days, make_opportunity, make_profile, make_source


# ------------------------------------------------------------------ profil
def test_profile_roundtrip_and_validation(client, auth):
    resp = client.get("/api/v1/profile", headers=auth)
    assert resp.status_code == 200
    version = resp.json()["version"]
    body = {
        "full_name": "Awa Diop",
        "nationalities": ["sn"],
        "study_level": "bachelor",
        "field_of_study": "Informatique",
        "skills": ["Python", "python", " SQL "],
        "languages": [{"code": "FR", "level": "natif"}, {"code": "en", "level": "b2"}],
        "experiences": [{"title": "Stage développeur", "organization": "ACME", "start": "2025-06", "end": "2025-08"}],
        "target_countries": ["DE"],
        "funding_preference": "full_only",
        "program_types": ["masters_scholarship"],
    }
    resp = client.put("/api/v1/profile", headers=auth, json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["nationalities"] == ["SN"]
    assert data["skills"] == ["Python", "SQL"]  # doublons supprimés
    assert data["languages"][0] == {"code": "fr", "level": "native"}
    assert data["version"] == version + 1
    assert 0 < data["completeness"] <= 100


def test_profile_rejects_invalid_values(client, auth):
    bad = [
        {"nationalities": ["FRA"]},
        {"languages": [{"code": "fr", "level": "excellent"}]},
        {"internship_duration_min_months": 6, "internship_duration_max_months": 2},
        {"study_level": "phd"},
        {"experiences": [{"title": "X", "start": "2025-13"}]},
    ]
    for payload in bad:
        assert client.put("/api/v1/profile", headers=auth, json=payload).status_code == 422, payload


# ------------------------------------------------------------------ catalogue
def _seed_catalogue(db, user):
    src = make_source(db)
    a = make_opportunity(
        db,
        src,
        title="Joint Master in Data Science",
        countries=["DE"],
        funding_type="full",
        deadline_at=in_days(10),
        deadline_status="confirmed",
    )
    b = make_opportunity(
        db,
        src,
        type="internship",
        title="Stage Marketing digital",
        organization="Exemple SA",
        countries=["FR"],
        funding_type="none",
        description="SEO et réseaux sociaux.",
    )
    c = make_opportunity(
        db, src, title="Master in Law", countries=["US"], funding_type="partial", eligible_nationalities=["US"]
    )
    closed = make_opportunity(db, src, title="Master expiré", deadline_at=in_days(-5), deadline_status="confirmed")
    make_profile(db, user)
    matching.recompute_for_user(db, user)
    db.commit()
    return a, b, c, closed


def test_catalogue_filters_sort_pagination(client, auth, db, user):
    a, b, c, closed = _seed_catalogue(db, user)
    get = lambda q="": client.get(f"/api/v1/opportunities?{q}", headers=auth).json()  # noqa: E731
    everything = get()
    assert everything["total"] == 3  # l'annonce échue est masquée par défaut
    assert get("include_closed=true")["total"] == 4
    assert [i["id"] for i in get("type=internship")["items"]] == [str(b.id)]
    assert [i["id"] for i in get("country=DE")["items"]] == [str(a.id)]
    assert {i["id"] for i in get("funding=full_or_partial")["items"]} == {str(a.id), str(c.id)}
    assert [i["id"] for i in get("deadline_within_days=30")["items"]] == [str(a.id)]
    assert [i["id"] for i in get("q=marketing")["items"]] == [str(b.id)]
    assert [i["id"] for i in get("eligibility=ineligible")["items"]] == [str(c.id)]
    page = get("page_size=2&page=2&sort=title")
    assert page["page"] == 2 and len(page["items"]) == 1
    scores = [i["match"]["score"] for i in get("sort=-score")["items"]]
    assert scores == sorted(scores, reverse=True)
    assert client.get("/api/v1/opportunities?page_size=1000", headers=auth).status_code == 422


def test_detail_has_provenance_and_explanation(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    resp = client.get(f"/api/v1/opportunities/{a.id}", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["official_url"].startswith("https://")
    assert data["sources"] and data["sources"][0]["source_url"]
    assert data["match_detail"]["disclaimer"]
    assert {c["key"] for c in data["match_detail"]["criteria"]} == {
        "academic",
        "skills",
        "funding",
        "preferences",
        "languages",
    }
    assert client.get(f"/api/v1/opportunities/{uuid.uuid4()}", headers=auth).status_code == 404


def test_favorites(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    assert client.post(f"/api/v1/opportunities/{a.id}/favorite", headers=auth).json()["is_favorite"] is True
    assert client.post(f"/api/v1/opportunities/{a.id}/favorite", headers=auth).status_code == 200  # idempotent
    assert [i["id"] for i in client.get("/api/v1/opportunities?favorites_only=true", headers=auth).json()["items"]] == [
        str(a.id)
    ]
    client.delete(f"/api/v1/opportunities/{a.id}/favorite", headers=auth)
    assert client.get("/api/v1/opportunities?favorites_only=true", headers=auth).json()["total"] == 0


def test_matches_endpoint_and_recompute_on_profile_change(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    data = client.get("/api/v1/matches", headers=auth).json()
    assert data["total"] == 3
    assert "to_complete" in data["items"][0]
    before = db.scalar(select(Match.score).where(Match.opportunity_id == a.id))
    client.put(
        "/api/v1/profile",
        headers=auth,
        json={
            "field_of_study": "Droit",
            "target_countries": ["CA"],
            "funding_preference": "full_only",
            "study_level": "bachelor",
        },
    )
    db.expire_all()
    after = db.scalar(select(Match.score).where(Match.opportunity_id == a.id))
    assert after < before  # recalcul déclenché après modification du profil


# ------------------------------------------------------------------ candidatures
def test_application_lifecycle(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    resp = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id)})
    assert resp.status_code == 201, resp.text
    app_id = resp.json()["id"]
    assert resp.json()["deadline_at"] is not None  # copie de la date confirmée
    assert resp.json()["urgency"]["reasons"]

    dup = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id)})
    assert dup.status_code == 409 and dup.json()["error"]["details"]["application_id"] == app_id

    # Validation humaine obligatoire pour « envoyée »
    refused = client.patch(f"/api/v1/applications/{app_id}", headers=auth, json={"status": "submitted"})
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "submission_confirmation_required"
    ok = client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth,
        json={"status": "submitted", "confirm_submission": True, "notes": "Envoyée via le portail"},
    )
    assert ok.status_code == 200
    assert ok.json()["submitted_at"] and ok.json()["submission_confirmed_at"]
    events = client.get(f"/api/v1/applications/{app_id}/events", headers=auth).json()
    types = [e["event_type"] for e in events]
    assert "created" in types and "status_changed" in types and "fields_updated" in types
    assert client.patch(f"/api/v1/applications/{app_id}", headers=auth, json={"status": "selection"}).status_code == 200


def test_new_application_cannot_start_as_submitted(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    resp = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id), "status": "submitted"})
    assert resp.status_code == 422


def test_tasks(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    app_id = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id)}).json()["id"]
    late = client.post(
        f"/api/v1/applications/{app_id}/tasks",
        headers=auth,
        json={"title": "Demander une lettre de recommandation", "due_at": in_days(-1).isoformat()},
    )
    assert late.status_code == 201 and late.json()["overdue"] is True
    client.post("/api/v1/tasks", headers=auth, json={"title": "Relire le CV", "due_at": in_days(3).isoformat()})
    assert len(client.get("/api/v1/tasks", headers=auth).json()) == 2
    assert len(client.get("/api/v1/tasks?overdue=true", headers=auth).json()) == 1
    done = client.patch(f"/api/v1/tasks/{late.json()['id']}", headers=auth, json={"status": "done"})
    assert done.json()["completed_at"] and done.json()["overdue"] is False
    assert len(client.get("/api/v1/tasks", headers=auth).json()) == 1
    assert client.get(f"/api/v1/applications/{app_id}", headers=auth).json()["open_tasks"] == 0


def test_users_are_isolated(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    app_id = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id)}).json()["id"]
    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    assert client.get(f"/api/v1/applications/{app_id}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/applications/{app_id}", headers=other, json={"notes": "x"}).status_code == 404
    assert client.get("/api/v1/applications", headers=other).json() == []
    # Un user_id fourni dans le corps n'est jamais pris en compte.
    resp = client.post(
        "/api/v1/applications", headers=other, json={"opportunity_id": str(a.id), "user_id": str(user.id)}
    )
    assert resp.status_code == 201
    assert len(client.get("/api/v1/applications", headers=auth).json()) == 1


def test_dashboard_and_calendar(client, auth, db, user):
    a, *_ = _seed_catalogue(db, user)
    client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(a.id)})
    client.post("/api/v1/tasks", headers=auth, json={"title": "En retard", "due_at": in_days(-2).isoformat()})
    dash = client.get("/api/v1/dashboard", headers=auth).json()
    assert dash["opportunities_total"] == 3
    assert dash["applications_in_progress"] == 1
    assert dash["deadlines_30_days"] == 1 and dash["deadlines_7_days"] == 0
    assert len(dash["overdue_tasks"]) == 1
    assert dash["ineligible"] == 1
    events = client.get("/api/v1/calendar", headers=auth).json()
    kinds = {e["kind"] for e in events}
    assert {"deadline", "task"} <= kinds
    assert (
        client.get("/api/v1/calendar?start=2026-01-01T00:00:00Z&end=2025-01-01T00:00:00Z", headers=auth).status_code
        == 422
    )
