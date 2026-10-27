from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select

from app.core.timeutil import utcnow
from app.db.locks import LockNotAcquired, job_lock
from app.models import Application, Favorite, NotificationLog, Opportunity, Task
from app.services import matching
from app.workers.notifications import service as notif
from app.workers.notifications.email import EmailMessage, ResendEmailClient, set_email_client
from tests.factories import in_days, make_opportunity, make_profile, make_source


def _track(db, user, opp):
    app = Application(user_id=user.id, opportunity_id=opp.id, status="preparing")
    db.add(app)
    db.commit()
    return app


def test_dispatch_is_deduplicated(db, user, outbox):
    first = notif.dispatch(db, user, kind="test", dedup_key="k1", subject="s", html="<p>x</p>", text="x")
    second = notif.dispatch(db, user, kind="test", dedup_key="k1", subject="s", html="<p>x</p>", text="x")
    assert first.status == "simulated" and second.status == "duplicate"
    assert len(outbox.outbox) == 1
    log = db.scalar(select(NotificationLog))
    assert log.provider == "simulation" and log.sent_at is not None


def test_recipient_must_be_authorized(db, user, outbox):
    prefs = notif.get_prefs(db, user)
    prefs.email = "inconnu@ailleurs.example"
    db.commit()
    assert notif.dispatch(db, user, kind="test", dedup_key="k", subject="s", html="", text="").status == "skipped"
    assert outbox.outbox == []


def test_preferences_api_rejects_unauthorized_recipient(client, auth):
    prefs = client.get("/api/v1/notifications/preferences", headers=auth).json()
    assert prefs["email_mode"] == "simulation"
    body = {
        **{k: prefs[k] for k in ("enabled", "digest_frequency", "min_score", "max_items")},
        "email": "pirate@evil.example",
    }
    assert client.put("/api/v1/notifications/preferences", headers=auth, json=body).status_code == 422
    body["email"] = "moi@example.com"
    body["deadline_reminder_days"] = [1, 7, 7, 14]
    resp = client.put("/api/v1/notifications/preferences", headers=auth, json=body)
    assert resp.status_code == 200 and resp.json()["deadline_reminder_days"] == [14, 7, 1]


def test_deadline_reminders_thresholds_and_dedup(db, user, outbox):
    opp = make_opportunity(db, make_source(db), deadline_at=in_days(6.5), deadline_status="confirmed")
    _track(db, user, opp)
    sent = notif.send_deadline_reminders(db, user)
    assert [o.status for o in sent] == ["simulated"]
    assert "J-7" in outbox.outbox[0].subject
    # Relance du job : aucun doublon
    assert [o.status for o in notif.send_deadline_reminders(db, user)] == ["duplicate"]
    assert len(outbox.outbox) == 1
    # Deux jours plus tard : seuil J-3 (rattrapage si le job a manqué un jour)
    later = notif.send_deadline_reminders(db, user, now=utcnow() + timedelta(days=4))
    assert [o.status for o in later] == ["simulated"]
    assert "J-3" in outbox.outbox[-1].subject


def test_no_reminder_for_unknown_deadline_and_flag_unverified(db, user, outbox):
    src = make_source(db)
    unknown = make_opportunity(db, src, title="Sans date")
    unverified = make_opportunity(
        db, src, title="Date agrégateur", deadline_at=in_days(2.5), deadline_status="unverified"
    )
    _track(db, user, unknown)
    _track(db, user, unverified)
    notif.send_deadline_reminders(db, user)
    assert len(outbox.outbox) == 1
    msg = outbox.outbox[0]
    assert "non vérifiée" in msg.subject
    assert "NON vérifiée" in msg.text or "PAS vérifiée" in msg.text


def test_favorites_get_reminders_too(db, user, outbox):
    opp = make_opportunity(db, make_source(db), deadline_at=in_days(0.6), deadline_status="confirmed")
    db.add(Favorite(user_id=user.id, opportunity_id=opp.id))
    db.commit()
    assert [o.status for o in notif.send_deadline_reminders(db, user)] == ["simulated"]


def test_task_reminders(db, user, outbox):
    db.add(Task(user_id=user.id, title="Envoyer le relevé", due_at=in_days(-1)))
    db.add(Task(user_id=user.id, title="Plus tard", due_at=in_days(10)))
    db.commit()
    out = notif.send_task_reminders(db, user)
    assert len(out) == 1 and "retard" in outbox.outbox[0].subject


def test_new_match_alert_once(db, user, outbox):
    make_profile(db, user)
    make_opportunity(db, make_source(db))
    matching.recompute_for_user(db, user)
    db.commit()
    assert notif.send_new_matches(db, user).status == "simulated"
    assert notif.send_new_matches(db, user).status == "skipped"  # déjà notifiée
    email = outbox.outbox[0]
    assert "Source officielle" in email.html and "https://example.org/programme/" in email.html
    assert "pas une probabilité" in email.text


def test_change_alert_for_tracked_opportunity(db, user, outbox):
    src = make_source(db)
    opp = make_opportunity(
        db, src, official_url="https://example.org/p/1", deadline_at=in_days(30), deadline_status="confirmed"
    )
    _track(db, user, opp)
    make_opportunity(
        db, src, official_url="https://example.org/p/1", deadline_at=in_days(20), deadline_status="confirmed"
    )
    out = notif.send_change_alerts(db, user)
    assert [o.status for o in out] == ["simulated"]
    assert "date limite" in outbox.outbox[0].text
    assert [o.status for o in notif.send_change_alerts(db, user)] == ["duplicate"]


def test_digest_period_rules(db, user):
    prefs = notif.get_prefs(db, user)
    prefs.digest_frequency, prefs.digest_weekday, prefs.digest_hour = "weekly", 0, 8
    monday_9 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)  # 9 h à Paris
    assert notif.digest_period(prefs, "Europe/Paris", monday_9) == "weekly:2026-W45"
    assert notif.digest_period(prefs, "Europe/Paris", monday_9 - timedelta(hours=2)) is None
    assert notif.digest_period(prefs, "Europe/Paris", monday_9 + timedelta(days=1)) is None
    prefs.digest_frequency = "daily"
    assert notif.digest_period(prefs, "Europe/Paris", monday_9) == "daily:2026-11-02"
    prefs.digest_frequency = "never"
    assert notif.digest_period(prefs, "Europe/Paris", monday_9) is None


def test_digest_sent_once_per_period(db, user, outbox):
    assert notif.send_digest(db, user, force_period="weekly:2026-W45").status == "simulated"
    assert notif.send_digest(db, user, force_period="weekly:2026-W45").status == "duplicate"


def test_failed_send_is_retried_then_capped(db, user):
    class Failing:
        provider = "resend"
        calls = 0

        def send(self, message):
            Failing.calls += 1
            from app.workers.notifications.email import EmailResult

            return EmailResult("failed", "resend", error="HTTP 503", retryable=True)

    set_email_client(Failing())
    for _ in range(5):
        notif.dispatch(db, user, kind="test", dedup_key="retry", subject="s", html="", text="")
    assert Failing.calls == notif.MAX_ATTEMPTS
    log = db.scalar(select(NotificationLog))
    assert log.status == "failed" and log.attempts == notif.MAX_ATTEMPTS


def test_resend_client_success_retry_and_idempotency():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"id": "msg_123"})

    client = ResendEmailClient(
        "re_test_key", "OI <alertes@example.com>", transport=httpx.MockTransport(handler), sleep=lambda _: None
    )
    result = client.send(
        EmailMessage(to="moi@example.com", subject="s", html="<p>h</p>", text="t", idempotency_key="u:k")
    )
    assert result.status == "sent" and result.message_id == "msg_123"
    assert len(seen) == 2
    assert seen[0].headers["Idempotency-Key"] == seen[1].headers["Idempotency-Key"]
    assert seen[0].headers["Authorization"] == "Bearer re_test_key"


def test_resend_client_non_retryable_error():
    client = ResendEmailClient(
        "re_x",
        "a@example.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(422, json={"message": "Invalid from"})),
        sleep=lambda _: None,
    )
    result = client.send(EmailMessage(to="moi@example.com", subject="s", html="", text="", idempotency_key="k"))
    assert result.status == "failed" and result.retryable is False and "Invalid from" in result.error


def test_test_email_requires_confirmation(client, auth, outbox):
    assert client.post("/api/v1/notifications/test", headers=auth, json={"confirm": False}).status_code == 422
    resp = client.post("/api/v1/notifications/test", headers=auth, json={"confirm": True})
    assert resp.status_code == 200 and resp.json()["status"] == "simulated"


def test_preview_does_not_send(client, auth, outbox):
    for kind in ("digest", "new_matches", "deadline"):
        resp = client.get(f"/api/v1/notifications/preview?kind={kind}", headers=auth)
        assert resp.status_code == 200 and "<html" in resp.json()["html"]
    assert outbox.outbox == []


# ------------------------------------------------------------------ jobs
def test_job_lock_prevents_overlap(db):
    from app.db.session import get_sessionmaker

    other = get_sessionmaker()()
    try:
        with job_lock(db, "demo", timedelta(minutes=5)):
            try:
                with job_lock(other, "demo"):
                    raise AssertionError("le verrou aurait dû être refusé")
            except LockNotAcquired:
                pass
        with job_lock(other, "demo"):
            pass
    finally:
        other.close()


def test_expired_lock_can_be_taken_over(db):
    from app.db.locks import try_acquire

    assert try_acquire(db, "stale", timedelta(seconds=-1)) is not None
    assert try_acquire(db, "stale", timedelta(minutes=5)) is not None


def test_run_job_exit_codes():
    from app.jobs._runner import run_job

    assert run_job("ok_job", lambda db: {"done": True}) == 0
    assert run_job("bad_job", lambda db: 1 / 0) == 1


def test_cleanup_closes_past_confirmed_deadlines(db):
    from app.jobs.cleanup_logs import run

    src = make_source(db)
    past = make_opportunity(db, src, title="Échue", deadline_at=in_days(-3), deadline_status="confirmed")
    unverified = make_opportunity(db, src, title="Non vérifiée", deadline_at=in_days(-3), deadline_status="unverified")
    result = run(db)
    assert result["closed_past_deadline"] == 1
    db.expire_all()
    assert db.get(Opportunity, past.id).status == "closed"
    assert db.get(Opportunity, unverified.id).status == "open"


def test_admin_collect_protected_by_cooldown(client, auth, db):
    from app.models import IngestionRun

    db.add(IngestionRun(job_name="collect", triggered_by="admin", status="success"))
    db.commit()
    assert client.post("/api/v1/admin/collect", headers=auth).status_code == 429
    assert db.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_admin_source_management(client, auth, db):
    from app.workers.connectors.registry import seed_sources

    assert seed_sources(db) == 5
    assert seed_sources(db) == 0  # idempotent, n'écrase rien
    sources = client.get("/api/v1/admin/sources", headers=auth).json()
    assert all(s["enabled"] is False for s in sources)  # désactivées tant que non testées
    sid = sources[0]["id"]
    resp = client.patch(f"/api/v1/admin/sources/{sid}", headers=auth, json={"enabled": True, "rate_limit_seconds": 3})
    assert resp.json()["enabled"] is True
    assert (
        client.patch(f"/api/v1/admin/sources/{sid}", headers=auth, json={"rate_limit_seconds": 0.1}).status_code == 422
    )


def test_daily_job_runs_all_steps(db, user):
    from app.jobs.daily import run

    result = run(db)
    assert set(result) == {"collect", "recompute", "deadlines", "digest", "cleanup"}


def test_job_modules_are_importable_cli_entrypoints():
    import importlib

    for name in (
        "collect_opportunities",
        "recompute_matches",
        "send_digest",
        "check_deadlines",
        "cleanup_logs",
        "daily",
    ):
        module = importlib.import_module(f"app.jobs.{name}")
        assert module.__doc__ and "python -m app.jobs" in module.__doc__ or name == "recompute_matches"
