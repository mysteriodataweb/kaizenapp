from __future__ import annotations

import io

from tests.conftest import login, make_user
from tests.factories import make_opportunity, make_profile, make_source


def minimal_pdf(lines: list[str]) -> bytes:
    """PDF texte minimal valide (police Helvetica standard), généré pour les tests."""
    content = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


PDF = minimal_pdf(
    [
        "Awa Diop",
        "awa.diop@example.com +221 77 123 45 67",
        "Licence en informatique",
        "Competences : Python, SQL, Docker",
        "Langues : Anglais B2, Wolof natif",
    ]
)


def upload(client, auth, data=PDF, name="cv.pdf", mime="application/pdf", **form):
    return client.post(
        "/api/v1/documents", headers=auth, files={"file": (name, data, mime)}, data={"doc_type": "cv", **form}
    )


def test_upload_download_version_delete(client, auth):
    resp = upload(client, auth, title="CV 2026")
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["mime_type"] == "application/pdf" and doc["version"] == 1
    link = client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth).json()
    assert link["mode"] == "proxy"
    content = client.get(f"/api/v1/documents/{doc['id']}/content", headers=auth)
    assert content.status_code == 200 and content.content == PDF
    assert "attachment" in content.headers["content-disposition"]
    v2 = upload(client, auth, replaces=doc["id"]).json()
    assert v2["version"] == 2 and v2["group_id"] == doc["group_id"]
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/documents/{doc['id']}/content", headers=auth).status_code == 404


def test_upload_rejects_bad_files(client, auth, settings):
    assert (
        upload(
            client, auth, data=b"MZ\x90\x00binary\x00exe", name="virus.exe", mime="application/octet-stream"
        ).status_code
        == 415
    )
    assert (
        upload(client, auth, data=b"plain text", name="cv.pdf", mime="application/pdf").status_code == 415
    )  # type annoncé mensonger
    big = b"%PDF-1.4\n" + b"0" * (settings.max_upload_mb * 1024 * 1024 + 10)
    assert upload(client, auth, data=big).status_code == 413
    assert upload(client, auth, data=b"").status_code == 422


def test_documents_are_private(client, auth, db):
    doc = upload(client, auth).json()
    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    assert client.get(f"/api/v1/documents/{doc['id']}/content", headers=other).status_code == 404
    assert client.get("/api/v1/documents", headers=other).json() == []


def test_document_linking_requires_same_owner(client, auth, db, user):
    opp = make_opportunity(db, make_source(db), required_documents=["CV", "Lettre de motivation"])
    app_id = client.post("/api/v1/applications", headers=auth, json={"opportunity_id": str(opp.id)}).json()["id"]
    doc = upload(client, auth).json()
    linked = client.post(
        f"/api/v1/applications/{app_id}/documents", headers=auth, json={"document_id": doc["id"], "role": "CV"}
    )
    assert linked.status_code == 200
    assert [d["id"] for d in linked.json()["documents"]] == [doc["id"]]
    assert any("document" in r for r in linked.json()["urgency"]["reasons"])  # lettre encore manquante

    make_user(db, "autre@example.com")
    other = login(client, "autre@example.com")
    other_doc = upload(client, other).json()
    assert (
        client.post(
            f"/api/v1/applications/{app_id}/documents", headers=auth, json={"document_id": other_doc["id"]}
        ).status_code
        == 404
    )
    other_app = client.post("/api/v1/applications", headers=other, json={"opportunity_id": str(opp.id)}).json()["id"]
    assert (
        client.post(
            f"/api/v1/applications/{other_app}/documents", headers=other, json={"document_id": doc["id"]}
        ).status_code
        == 404
    )


def test_db_constraint_blocks_cross_owner_link(db, user):
    import uuid

    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.models import ApplicationDocument, Document
    from app.schemas.application import ApplicationCreate
    from app.services.applications import create_application

    other = make_user(db, "x@example.com")
    opp = make_opportunity(db, make_source(db))
    app_out = create_application(db, user, ApplicationCreate(opportunity_id=opp.id))
    doc = Document(
        user_id=other.id,
        group_id=uuid.uuid4(),
        doc_type="cv",
        title="t",
        original_filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        storage_key="k",
    )
    db.add(doc)
    db.commit()
    db.add(ApplicationDocument(application_id=app_out.id, document_id=doc.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_storage_disabled_is_graceful(client, auth, monkeypatch):
    from app.services import documents
    from app.services.storage import DisabledStorage

    monkeypatch.setattr(documents, "get_storage", lambda: DisabledStorage())
    resp = upload(client, auth)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "storage_disabled"


def test_cv_extraction_suggests_without_saving(client, auth):
    resp = client.post("/api/v1/profile/cv-extract", headers=auth, files={"file": ("cv.pdf", PDF, "application/pdf")})
    assert resp.status_code == 200, resp.text
    sugg = resp.json()["suggestions"]
    assert sugg["contact_email"] == "awa.diop@example.com"
    assert {"Python", "SQL", "Docker"} <= set(sugg["skills"])
    langs = {lang["code"]: lang["level"] for lang in sugg["languages"]}
    assert langs["en"] == "B2" and langs["wo"] == "native"
    assert sugg["full_name"] == "Awa Diop"
    assert resp.json()["evidence"]["contact_email"]
    # Rien n'a été enregistré dans le profil
    assert client.get("/api/v1/profile", headers=auth).json()["skills"] == []


def test_cv_extraction_requires_pdf(client, auth):
    resp = client.post("/api/v1/profile/cv-extract", headers=auth, files={"file": ("cv.txt", b"hello", "text/plain")})
    assert resp.status_code == 415


def test_assistant_disabled_without_key(client, auth, db, user):
    opp = make_opportunity(db, make_source(db))
    resp = client.post(
        "/api/v1/assist/generate", headers=auth, json={"kind": "cover_letter", "opportunity_id": str(opp.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False and body["draft"] is None
    assert "nom complet" in body["missing_information"]
    assert client.get("/api/v1/assist/status", headers=auth).json() == {"enabled": False}


def test_assistant_uses_only_profile_facts(client, auth, db, user, monkeypatch):
    from app.services import ai

    captured = {}

    class FakeProvider:
        name = "fake"

        def generate(self, system, prompt):
            captured["system"], captured["prompt"] = system, prompt
            return "Brouillon [À COMPLÉTER : projet pertinent]"

    monkeypatch.setattr(ai, "get_provider", lambda: FakeProvider())
    make_profile(db, user, experiences=[{"title": "Stage", "organization": "ACME"}])
    opp = make_opportunity(db, make_source(db))
    body = client.post(
        "/api/v1/assist/generate", headers=auth, json={"kind": "cover_letter", "opportunity_id": str(opp.id)}
    ).json()
    assert body["enabled"] is True and body["draft"].startswith("Brouillon")
    assert "N'invente jamais" in captured["system"]
    assert "Awa Diop" in captured["prompt"] and "Consortium Test" in captured["prompt"]
    assert body["missing_information"] == []
