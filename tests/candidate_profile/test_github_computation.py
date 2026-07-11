from datetime import datetime, timedelta, timezone

from candidate_profile.github_computation import (
    compute_account_age_years,
    compute_top_languages,
)


def test_compute_account_age_years_from_valid_created_at():
    ten_years_ago = (datetime.now(timezone.utc) - timedelta(days=365 * 10)).isoformat().replace(
        "+00:00", "Z"
    )
    age = compute_account_age_years({"created_at": ten_years_ago})
    assert age is not None
    assert 9.8 < age < 10.2


def test_compute_account_age_years_missing_field_returns_none():
    assert compute_account_age_years({}) is None


def test_compute_account_age_years_malformed_date_returns_none():
    assert compute_account_age_years({"created_at": "not-a-date"}) is None


def test_compute_top_languages_ranks_by_frequency():
    repos = [
        {"language": "Python"},
        {"language": "Python"},
        {"language": "Go"},
        {"language": "Go"},
        {"language": "Go"},
        {"language": "Rust"},
    ]
    result = compute_top_languages(repos)
    assert result == ["Go", "Python", "Rust"]


def test_compute_top_languages_ignores_null_language():
    repos = [{"language": "Python"}, {"language": None}, {}]
    result = compute_top_languages(repos)
    assert result == ["Python"]


def test_compute_top_languages_respects_limit():
    repos = [{"language": lang} for lang in ["A", "B", "C", "D", "E", "F"]]
    result = compute_top_languages(repos, limit=3)
    assert len(result) == 3


def test_compute_top_languages_empty_repo_list_returns_empty():
    assert compute_top_languages([]) == []
