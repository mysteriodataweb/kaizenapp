from __future__ import annotations

from app.services.priority import compute_urgency
from app.workers.matching.engine import OpportunityData, ProfileData, compute_match
from tests.factories import in_days

W = {"academic": 30, "skills": 25, "funding": 20, "preferences": 15, "languages": 10}


def profile(**kw):
    base = dict(
        nationalities=["SN"],
        study_level="bachelor",
        field_of_study="Informatique",
        skills=["Python", "SQL"],
        languages=[{"code": "fr", "level": "native"}, {"code": "en", "level": "B2"}],
        target_countries=["DE"],
        funding_preference="full_only",
        program_types=["masters_scholarship"],
    )
    base.update(kw)
    return ProfileData(**base)


def opp(**kw):
    base = dict(
        type="masters_scholarship",
        title="Joint Master in Data Science",
        description="Python and statistics",
        countries=["DE"],
        funding_type="full",
    )
    base.update(kw)
    return OpportunityData(**base)


def test_unknown_when_no_published_criteria():
    r = compute_match(profile(), opp(), W)
    assert r.eligibility == "unknown"
    assert any("critères" in n for n in r.explanation["eligibility"]["notes"])


def test_eligible_only_when_published_criteria_satisfied():
    r = compute_match(
        profile(), opp(eligible_nationalities=["SN", "CI"], required_languages=[{"code": "en", "level": "B2"}]), W
    )
    assert r.eligibility == "eligible"


def test_ineligible_only_on_explicit_incompatibility():
    r = compute_match(profile(), opp(eligible_nationalities=["US"]), W)
    assert r.eligibility == "ineligible"
    assert any("Nationalit" in s for s in r.explanation["unsatisfied"])


def test_missing_profile_info_gives_unknown_not_ineligible():
    r = compute_match(profile(nationalities=[]), opp(eligible_nationalities=["US"]), W)
    assert r.eligibility == "unknown"
    assert "nationalities" in r.missing_profile_fields


def test_language_level_too_low_is_ineligible_but_absent_is_unknown():
    low = compute_match(
        profile(languages=[{"code": "de", "level": "A2"}]), opp(required_languages=[{"code": "de", "level": "B2"}]), W
    )
    assert low.eligibility == "ineligible"
    absent = compute_match(profile(), opp(required_languages=[{"code": "de", "level": "B2"}]), W)
    assert absent.eligibility == "unknown"
    assert "languages" in absent.missing_profile_fields


def test_score_bounds_and_disclaimer():
    for p in (profile(), ProfileData()):
        for o in (opp(), opp(type="internship", title="Stagiaire", funding_type="none")):
            r = compute_match(p, o, W)
            assert 0 <= r.score <= 100
            assert 0 <= r.confidence <= 1
            assert "pas une probabilité" in r.explanation["disclaimer"]


def test_empty_profile_has_zero_confidence_and_lists_missing_fields():
    r = compute_match(ProfileData(), opp(), W)
    assert r.confidence == 0
    assert {"study_level", "field_of_study", "skills", "funding_preference"} <= set(r.missing_profile_fields)


def test_not_applicable_criteria_are_removed_from_weights():
    r = compute_match(profile(target_countries=[], program_types=[]), opp(), W)
    crit = {c["key"]: c for c in r.explanation["criteria"]}
    assert crit["languages"]["status"] == "not_applicable"  # aucune exigence publiée
    assert crit["preferences"]["status"] == "not_applicable"
    assert crit["languages"]["effective_weight"] == 0
    applicable = [c for c in crit.values() if c["status"] != "not_applicable"]
    assert round(sum(c["effective_weight"] for c in applicable)) == 100


def test_good_fit_scores_higher_than_poor_fit():
    good = compute_match(profile(), opp(), W)
    poor = compute_match(
        profile(field_of_study="Droit", skills=["Plaidoirie"], target_countries=["CA"]), opp(funding_type="partial"), W
    )
    assert good.score > poor.score
    assert good.score >= 70


def test_bilingual_field_matching():
    r = compute_match(profile(field_of_study="Génie civil"), opp(title="MSc Civil Engineering", description=""), W)
    academic = next(c for c in r.explanation["criteria"] if c["key"] == "academic")
    assert academic["value"] > 0.9


def test_urgency_is_explainable():
    u = compute_urgency(
        deadline_at=in_days(2),
        deadline_status="confirmed",
        eligibility="eligible",
        score=80,
        missing_documents=2,
        estimated_prep_hours=12,
        next_action_at=None,
        tz="Europe/Paris",
    )
    assert u.level == "critique"
    assert any("Échéance" in r for r in u.reasons)
    assert any("document" in r for r in u.reasons)
    unknown = compute_urgency(
        deadline_at=None,
        deadline_status="unknown",
        eligibility="unknown",
        score=None,
        missing_documents=0,
        estimated_prep_hours=None,
        next_action_at=None,
        tz="UTC",
    )
    assert unknown.days_left is None
    assert any("inconnue" in r for r in unknown.reasons)
    past = compute_urgency(
        deadline_at=in_days(-3),
        deadline_status="confirmed",
        eligibility=None,
        score=None,
        missing_documents=0,
        estimated_prep_hours=None,
        next_action_at=None,
        tz="UTC",
    )
    assert past.level == "expiree"
