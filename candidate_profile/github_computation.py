from collections import Counter
from datetime import datetime, timezone


def compute_account_age_years(profile: dict) -> float | None:
    created_at = profile.get("created_at")
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    age = datetime.now(timezone.utc) - created
    return round(age.days / 365.25, 2)


def compute_top_languages(repos: list[dict], limit: int = 5) -> list[str]:
    languages = [repo["language"] for repo in repos if repo.get("language")]
    ranked = Counter(languages).most_common(limit)
    return [language for language, _count in ranked]
